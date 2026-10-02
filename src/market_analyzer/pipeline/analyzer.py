"""The Market Analyzer orchestrator.

Responsibilities, in order:
  1. Load config, market profile, and curated knowledge
  2. Fetch candles for the universe (fail-closed on stale/invalid data)
  3. Compute indicators
  4. Detect candidate setups
  5. Rank candidates
  6. Classify the market regime from the benchmark
  7. Persist a snapshot, append a case, and return `MarketAnalysis`

It never authenticates and never places orders.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from market_analyzer.ai import AiAnalyst, build_ai_analyst
from market_analyzer.config import AppConfig, load_app_config
from market_analyzer.knowledge.loader import load_directory
from market_analyzer.knowledge.retriever import KnowledgeRetriever
from market_analyzer.knowledge.writer import CaseWriter
from market_analyzer.models.analysis import (
    Candidate,
    MarketAnalysis,
    MarketRegime,
    MultiTimeframeMetrics,
)
from market_analyzer.models.profile import Instrument, MarketProfile
from market_analyzer.models.quote import Candle
from market_analyzer.pipeline.candidates import detect_candidate
from market_analyzer.pipeline.features import add_indicators, to_frame
from market_analyzer.pipeline.multiframe import (
    compute_mtf_indicators,
    detect_candidate_mtf,
    fuse_mtf_signals,
)
from market_analyzer.pipeline.rank import rank_candidates
from market_analyzer.pipeline.symbols import parse_custom_symbol
from market_analyzer.pipeline.validate import (
    build_data_quality_report,
    candle_age_seconds,
    validate_candles,
)
from market_analyzer.providers.base import MarketDataProvider, ProviderError
from market_analyzer.providers.session import get_calendar
from market_analyzer.research.base import NullResearchProvider, WebResearchProvider
from market_analyzer.storage.events import JsonlEventLogger
from market_analyzer.storage.snapshots import SnapshotStore


def build_provider(
    config: AppConfig,
    provider_override: str | None = None,
) -> MarketDataProvider:
    """Instantiate the configured market data provider (Twelve Data, Finnhub, or Fallback)."""
    import os

    from market_analyzer.providers.fallback import FallbackDataProvider
    from market_analyzer.providers.finnhub import FinnhubDataProvider
    from market_analyzer.providers.twelvedata import TwelveDataProvider

    name = (provider_override or config.data.provider).lower()
    td_key = config.data.twelvedata_api_key or os.getenv("TWELVEDATA_API_KEY", "")
    fh_key = config.data.finnhub_api_key or os.getenv("FINNHUB_API_KEY", "")

    if name in ("twelvedata_fallback", "fallback"):
        primary = TwelveDataProvider(
            api_key=td_key,
            throttle_seconds=config.data.throttle_seconds,
        )
        secondary = FinnhubDataProvider(
            api_key=fh_key,
            throttle_seconds=config.data.throttle_seconds,
        )
        return FallbackDataProvider(primary=primary, secondary=secondary)

    if name == "twelvedata":
        return TwelveDataProvider(
            api_key=td_key,
            throttle_seconds=config.data.throttle_seconds,
        )

    if name == "finnhub":
        return FinnhubDataProvider(
            api_key=fh_key,
            throttle_seconds=config.data.throttle_seconds,
        )

    raise ValueError(
        f"Data provider must be 'twelvedata', 'finnhub', or 'twelvedata_fallback', got {name!r}."
    )


def build_research_provider(config: AppConfig) -> WebResearchProvider:
    """Instantiate the research provider named in config.

    Returns a no-op provider when research is disabled, so market analysis never
    depends on web availability. The spawned interpreter defaults to
    ``sys.executable`` rather than a bare "python", so the search MCP server runs
    inside this same virtualenv instead of whatever `python` resolves to on PATH.
    """
    if not config.web_research.enabled:
        return NullResearchProvider()

    from market_analyzer.research.mcp_web import McpWebResearchProvider

    return McpWebResearchProvider(
        command=config.web_research.mcp_command or sys.executable,
        args=list(config.web_research.mcp_args),
    )



class MarketAnalyzer:
    def __init__(
        self,
        config: AppConfig | None = None,
        provider: MarketDataProvider | None = None,
        research: WebResearchProvider | None = None,
        ai: AiAnalyst | None = None,
    ) -> None:
        self.config = config or load_app_config()
        self.provider = provider or build_provider(self.config)
        self.research = research or build_research_provider(self.config)
        self.logger = JsonlEventLogger(
            self.config.resolve(self.config.logging.directory), self.config.logging.level
        )
        self.snapshots = SnapshotStore(
            self.config.resolve(self.config.output.directory),
            self.config.output.retain_runs,
        )
        self.cases = CaseWriter(self.config.resolve(self.config.knowledge.cases_directory))
        self.ai = ai or build_ai_analyst(self.config.ai.enabled)
        self._knowledge: KnowledgeRetriever | None = None
        # Per-run memo: which symbols already consumed an AI call, and what
        # came back. Keeps the free-tier budget bounded and idempotent.
        self._ai_done: set[str] = set()
        self._last_events: dict[str, list] = {}

    async def aclose(self) -> None:
        """Release the research subprocess and AI client, if any were started."""
        for closer in (getattr(self.research, "aclose", None), self.ai.aclose):
            if closer is not None:
                await closer()

    @property
    def knowledge(self) -> KnowledgeRetriever:
        if self._knowledge is None:
            records = load_directory(self.config.resolve(self.config.knowledge.core_directory))
            self._knowledge = KnowledgeRetriever(
                records, approved_only=self.config.knowledge.approved_only
            )
        return self._knowledge

    async def run(
        self,
        profile: MarketProfile,
        limit: int | None = None,
        enrich_news: bool = False,
    ) -> MarketAnalysis:
        run_id = uuid.uuid4().hex[:12]
        self.logger.info(
            "analysis.started",
            run_id=run_id,
            profile=profile.id,
            provider=self.provider.name,
            realtime=self.provider.realtime,
        )

        # Profile and Universe lockdown
        if profile.id != "FOCUSED_SYMBOLS":
            raise ValueError(
                f"Market analyzer only supports 'FOCUSED_SYMBOLS' profile, got {profile.id!r}"
            )
        allowed_symbols = {"NAS100", "US500", "XAUUSD", "XAGUSD", "BTCUSD"}
        unauthorized = []
        for sym in profile.symbols():
            if sym not in allowed_symbols:
                is_valid, _, _, _, _ = parse_custom_symbol(sym)
                if not is_valid:
                    unauthorized.append(sym)
        if unauthorized:
            raise ValueError(
                f"Market analyzer only supports focused symbols ({', '.join(sorted(allowed_symbols))}), "
                f"Forex currency pairs, or Crypto pairs. Unauthorized symbols detected: {', '.join(sorted(unauthorized))}"
            )
        allowed_providers = {"twelvedata", "finnhub", "fallback"}
        if self.provider.name not in allowed_providers and not getattr(self.provider, "name", "").endswith("test_data"):
            raise ValueError(
                f"Market data feed must come from Twelve Data, Finnhub, or Fallback provider, got provider {self.provider.name!r}."
            )

        if self.config.data.require_realtime and not self.provider.realtime:
            raise RuntimeError(
                f"data.require_realtime is true but provider "
                f"{self.provider.name!r} is delayed. Configure a real-time adapter "
                f"or set data.require_realtime=false."
            )

        symbols = profile.symbols()
        interval = profile.timeframes.intraday
        lookback = max(profile.min_history_candles + 20, 60)

        # Multi-timeframe configuration
        mtf_intervals = profile.timeframes.intraday_multi  # e.g., ["4h", "1h", "15m"]
        # Use different lookbacks per TF: coarser TFs need fewer bars
        tf_lookbacks = {
            "4h": min(lookback, 180),       # ~30 days
            "1h": min(lookback * 4, 500),   # ~20 days
            "15m": lookback,                # full lookback
            "5m": lookback,
        }

        # Volume gates are only safe on a feed carrying consolidated volume.
        # Check per-symbol; if any symbol in the run lacks consolidated volume,
        # disable volume gates for the entire run.
        volume_consolidated = True
        for sym in symbols:
            if hasattr(self.provider, "volume_kind_for"):
                kind = self.provider.volume_kind_for(sym)
                if kind in ("tick", "venue", "none", "unknown"):
                    volume_consolidated = False
                    break
        if not volume_consolidated:
            volume_gates = False
            self.logger.warning(
                "data.volume_gates_disabled",
                reason="at least one symbol lacks consolidated volume",
            )
        else:
            # Config no longer has allow_volume_gated_setups; default to False
            # since volume gates are only safe with explicit consolidated feed.
            volume_gates = False

        # Multi-timeframe candles: symbol -> {timeframe -> [Candle, ...]}
        candles_by_symbol_mtf: dict[str, dict[str, list[Candle]]] = {}
        issues: list[str] = []
        failed: set[str] = set()
        stale: set[str] = set()

        semaphore = asyncio.Semaphore(self.config.data.max_concurrent_requests)

        async def fetch_mtf(symbol: str) -> None:
            """Fetch candles for all configured timeframes for a symbol."""
            async with semaphore:
                instrument = profile.instrument(symbol)
                provider_sym = instrument.provider_symbol if instrument else None
                
                mtf_candles: dict[str, list[Candle]] = {}
                for tf in mtf_intervals:
                    lb = tf_lookbacks.get(tf, lookback)
                    try:
                        candles = await self.provider.get_candles(
                            symbol, tf, lb, provider_symbol=provider_sym
                        )
                    except (TimeoutError, ProviderError) as exc:
                        failed.add(symbol)
                        issues.append(f"{symbol} {tf}: fetch failed ({exc})")
                        return
                    
                    # Validate candles for this timeframe
                    session_name = (
                        self.provider.session_for(symbol)
                        if hasattr(self.provider, "session_for")
                        else (instrument.session if instrument else "equity_us")
                    )
                    cal = get_calendar(session_name)
                    now_utc = datetime.now(timezone.utc)
                    session_open = cal.is_open(now_utc)
                    session_close_utc = cal.session_close_utc(now_utc)

                    problems = validate_candles(
                        symbol,
                        candles,
                        self.config.data.stale_after_seconds,
                        interval=tf,
                        session_open=session_open,
                        session_close_utc=session_close_utc,
                    )
                    if problems:
                        issues.extend(problems)
                        if any("stale" in p for p in problems):
                            stale.add(symbol)
                        else:
                            failed.add(symbol)
                        return
                    
                    mtf_candles[tf] = candles
                
                # All timeframes fetched successfully
                candles_by_symbol_mtf[symbol] = mtf_candles

        await asyncio.gather(*(fetch_mtf(symbol) for symbol in symbols))

        if not candles_by_symbol_mtf:
            raise RuntimeError(
                f"no usable market data for profile {profile.id}: {issues[:5]}"
            )

        candidates: list[Candidate] = []
        volumes: dict[str, float] = {}
        ages: dict[str, float | None] = {}

        for symbol, mtf_candles in candles_by_symbol_mtf.items():
            # Compute indicators per timeframe
            mtf_indicators = compute_mtf_indicators(mtf_candles)
            if not mtf_indicators:
                continue
            
            instrument = profile.instrument(symbol)
            if instrument is None:
                continue
            
            # Fuse multi-timeframe signals
            fused, dominant_trend, per_tf_setups = fuse_mtf_signals(
                mtf_indicators, instrument, volume_gates
            )
            
            # Create MTF metrics object
            mtf_metrics_obj = MultiTimeframeMetrics(
                by_timeframe=mtf_indicators,
                fused=fused,
                dominant_trend=dominant_trend,
                entry_timeframe="15m" if "15m" in mtf_candles else mtf_intervals[-1],
                mtf_setup=per_tf_setups,
            )
            
            # Use entry timeframe (15m) for price and volume calculations
            entry_tf = "15m" if "15m" in mtf_candles else mtf_intervals[-1]
            entry_candles = mtf_candles[entry_tf]
            last_price = float(entry_candles[-1].close)
            
            # Calculate age and volume from entry timeframe
            ages[symbol] = candle_age_seconds(entry_candles)
            window = entry_candles[-20:] if len(entry_candles) >= 20 else entry_candles
            volumes[symbol] = sum(c.volume for c in window) / len(window)
            
            # Multi-timeframe candidate detection (entry on 15m, gated by 4h/1h)
            candidate = detect_candidate_mtf(
                instrument,
                mtf_metrics_obj,
                last_price,
                allow_volume_gates=volume_gates,
                source=self.provider.name,
            )
            if candidate:
                candidates.append(candidate)

        if enrich_news and self.config.web_research.enabled:
            candidates = await self._enrich_with_news(candidates)

        ranked = rank_candidates(
            candidates, profile.scoring_weights, volumes, ages, volume_consolidated
        )
        top = ranked[: (limit or profile.max_candidates)]

        regime, regime_rationale = await self._classify_regime(profile)

        knowledge_refs = [
            record.title
            for record in self.knowledge.retrieve(
                market=profile.id, limit=self.config.knowledge.max_context_items
            )
        ]

        # Flatten all timestamps and find the latest
        all_timestamps = [
            c.timestamp
            for mtf_candles in candles_by_symbol_mtf.values()
            for candles in mtf_candles.values()
            for c in candles
        ]
        data_as_of = max(all_timestamps) if all_timestamps else None

        warnings: list[str] = []
        if not self.provider.realtime:
            warnings.append(
                "Data source is DELAYED. Not suitable for live execution decisions."
            )
        # Feed info and volume honesty per symbol
        if hasattr(self.provider, "feed_for"):
            feeds = set(self.provider.feed_for(s) for s in symbols)
            feed_str = ", ".join(sorted(feeds))
        else:
            feed_str = self._feed_name()
        
        # Check if any symbol lacks consolidated volume
        non_consolidated = []
        if hasattr(self.provider, "volume_kind_for"):
            for sym in symbols:
                kind = self.provider.volume_kind_for(sym)
                if kind in ("tick", "venue", "none", "unknown"):
                    non_consolidated.append(f"{sym} ({kind})")
        if non_consolidated:
            warnings.append(
                f"Feed '{feed_str}' does not carry CONSOLIDATED volume for: "
                f"{', '.join(non_consolidated)}. Prices are real-time, but volume "
                "is tick/venue-only, so volume-derived signals "
                "are unreliable."
            )
        if not volume_gates:
            warnings.append(
                "Volume-gated setups are disabled for this run; only "
                "volume-independent setups can qualify."
            )
        # Session state per symbol
        if hasattr(self.provider, "session_for"):
            sessions = {s: self.provider.session_for(s) for s in symbols}
            non_open = [
                f"{sym} ({sess})" 
                for sym, sess in sessions.items()
                if hasattr(self.provider, "_session_state")
                and not self.provider._is_session_open(sess)
            ]
            if non_open:
                warnings.append(
                    f"Market session not OPEN for: {', '.join(non_open)}. "
                    "Bars are from the last session, so this is historical "
                    "context, not a live picture."
                )
        if not self.config.web_research.enabled:
            warnings.append("Web research disabled; news sentiment is neutral.")

        report = build_data_quality_report(
            provider=self.provider.name,
            realtime=self.provider.realtime,
            requested=symbols,
            failed=failed,
            stale=stale,
            issues=issues,
        )

        # AI-driven Market Analysis
        ai_market_result: dict[str, Any] | None = None
        if self.ai.enabled:
            market_payload = {
                "profile": profile.id,
                "regime": regime.value,
                "regime_rationale": regime_rationale,
                "symbols": symbols,
                "candidates": [
                    {
                        "symbol": c.symbol,
                        "setup": c.setup.value,
                        "side": c.side.value,
                        "score": c.score,
                        "last_price": c.last_price,
                        "metrics": c.metrics,
                        # NEW: MTF context
                        "mtf": {
                            "dominant_trend": c.mtf_metrics.dominant_trend if c.mtf_metrics else None,
                            "trend_agreement": c.mtf_metrics.fused.get("tf_trend_agreement") if c.mtf_metrics else None,
                            "rsi_alignment": c.mtf_metrics.fused.get("tf_rsi_alignment") if c.mtf_metrics else None,
                            "volume_confirmation": c.mtf_metrics.fused.get("tf_volume_confirmation") if c.mtf_metrics else None,
                            "per_tf_setups": {tf: s.value for tf, s in c.mtf_setup.items()} if c.mtf_setup else {},
                            "entry_timeframe": c.mtf_metrics.entry_timeframe if c.mtf_metrics else "15m",
                        } if c.mtf_metrics else None,
                    }
                    for c in top
                ],
                "data_quality": {
                    "ok": report.instruments_ok,
                    "failed": report.instruments_failed,
                    "stale": report.instruments_stale,
                },
                "warnings": warnings,
            }
            try:
                ai_market_result = await self.ai.analyze_market(market_payload)
            except Exception as exc:
                self.logger.warning("ai.market_analysis_failed", error=str(exc))
                ai_market_result = None

        ai_summary = (
            ai_market_result.get("market_synthesis")
            if (ai_market_result and ai_market_result.get("market_synthesis"))
            else self._summarise(profile, regime, top)
        )

        analysis = MarketAnalysis(
            run_id=run_id,
            profile_id=profile.id,
            generated_at=datetime.now(timezone.utc),
            data_as_of=data_as_of,
            data_realtime=self.provider.realtime,
            provider=self.provider.name,
            regime=regime,
            regime_rationale=regime_rationale,
            summary=ai_summary,
            candidates=top,
            data_quality=report,
            knowledge_refs=knowledge_refs,
            warnings=warnings,
            ai_analysis=ai_market_result,
        )

        self.snapshots.save(analysis)
        self.cases.append(
            {
                "kind": "analysis_run",
                "run_id": run_id,
                "profile": profile.id,
                "provider": self.provider.name,
                "realtime": self.provider.realtime,
                "regime": regime.value,
                "candidates": [
                    {
                        "symbol": c.symbol,
                        "setup": c.setup.value,
                        "side": c.side.value,
                        "score": c.score,
                        "price": c.last_price,
                    }
                    for c in top
                ],
                "warnings": warnings,
            }
        )
        self.logger.info(
            "analysis.completed",
            run_id=run_id,
            candidates=len(top),
            regime=regime.value,
            failed=len(failed),
            stale=len(stale),
        )
        return analysis

    def _volume_is_consolidated(self) -> bool:
        """Whether this provider's volume figures cover the whole market.

        Providers that know their feed (Twelve Data) answer per-symbol.
        The first symbol with non-consolidated volume makes the whole run
        volume-conservative.
        """
        flag = getattr(self.provider, "volume_is_consolidated", None)
        if flag is None:
            return True
        # TwelveDataProvider.volume_is_consolidated is per-symbol; 
        # we check the focused symbols
        return bool(flag)

    def _feed_name(self) -> str:
        return str(getattr(self.provider, "feed", "") or self.provider.name)

    def _session_state(self) -> str | None:
        state = getattr(self.provider, "session_state", None)
        if state is None:
            return None
        return getattr(state(), "value", str(state()))

    async def _enrich_with_news(self, candidates: list[Candidate]) -> list[Candidate]:
        """Attach a sentiment hint derived from typed news events.

        The model may only classify and describe: it never produces a price or
        a score. Negative coverage downgrades a long candidate to `watch` and
        nothing more. Web content can never authorise a trade on its own.
        """
        if not candidates:
            return candidates

        cap = self.config.ai.max_symbols_per_run
        enriched: list[Candidate] = []
        for candidate in candidates:
            instrument = Instrument(
                symbol=candidate.symbol,
                name=candidate.name,
                sector=candidate.sector,
            )
            if candidate.symbol in self._ai_done:
                enriched.append(candidate)
                continue

            results = await self.research.search(
                query=f"{candidate.name} stock news",
                limit=self.config.web_research.max_results_per_query,
                freshness_hours=self.config.web_research.freshness_hours,
            )
            if not results:
                enriched.append(candidate)
                continue

            events = await self.ai.extract_events(candidate.symbol, results)
            self._ai_done.add(candidate.symbol)
            self._last_events[candidate.symbol] = events

            negative = [
                e
                for e in events
                if e.direction.value == "negative" and e.severity >= 0.5
            ]
            sentiment = 0.3 if negative else (0.6 if events else None)

            rebuilt = detect_candidate(
                instrument,
                candidate.metrics,
                candidate.last_price,
                news_sentiment=sentiment,
                allow_volume_gates=False,  # volume gates disabled by default
                source=self.provider.name,
            )
            if rebuilt is None:
                # Re-detection dropped it (e.g. liquidity guard); keep as-is.
                enriched.append(candidate)
                continue
            # Preserve the computed score by re-attaching it after detection.
            enriched.append(rebuilt.model_copy(update={"score": candidate.score}))
            if len(self._ai_done) >= cap:
                # Budget exhausted: remaining candidates stay un-enriched
                # rather than spending more free-tier calls.
                enriched.extend(candidates[len(enriched) :])
                break
        return enriched

    async def _classify_regime(
        self, profile: MarketProfile
    ) -> tuple[MarketRegime, list[str]]:
        """Classify regime from the benchmark using the daily trend timeframe."""
        if not profile.benchmark:
            return MarketRegime.UNKNOWN, ["no benchmark configured"]

        try:
            candles = await self.provider.get_candles(
                profile.benchmark, profile.timeframes.trend, 120
            )
        except (TimeoutError, ProviderError) as exc:
            return MarketRegime.UNKNOWN, [f"benchmark fetch failed: {exc}"]

        frame = add_indicators(to_frame(candles))
        if frame.empty:
            return MarketRegime.UNKNOWN, ["benchmark returned no usable candles"]

        row = frame.iloc[-1]
        rationale: list[str] = []
        trend = 0.0
        trend += 1 if row["sma_20"] > row["sma_50"] else -1
        trend += 1 if row["close"] > row["sma_20"] else -1

        volatility = float(row["volatility_20"] or 0.0)
        if volatility > 0.45:
            regime = MarketRegime.HIGH_VOLATILITY
            rationale.append(f"annualised volatility {volatility:.0%} is extreme")
        elif trend >= 2:
            regime = MarketRegime.BULLISH
            rationale.append("benchmark close above SMA20 and SMA50")
        elif trend <= -2:
            regime = MarketRegime.BEARISH
            rationale.append("benchmark close below SMA20 and SMA50")
        else:
            regime = MarketRegime.RANGE_BOUND
            rationale.append("benchmark signals are mixed")

        return regime, rationale

    @staticmethod
    def _summarise(
        profile: MarketProfile, regime: MarketRegime, candidates: list[Candidate]
    ) -> str:
        if not candidates:
            return (
                f"{profile.display_name}: regime {regime.value}. "
                "No setup met the entry criteria. NO_TRADE."
            )
        best = candidates[0]
        return (
            f"{profile.display_name}: regime {regime.value}. "
            f"Top candidate {best.symbol} ({best.setup.value}, {best.side.value}) "
            f"score {best.score:.1f}. {len(candidates)} candidate(s) qualified."
        )
