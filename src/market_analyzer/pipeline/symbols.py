"""Universal symbol validation and dynamic instrument construction.

Supports user-entered search symbols representing:
- Forex currency pairs (e.g. EUR/USD, GBP/USD, USD/JPY)
- Crypto pairs (e.g. BTC/USD, ETH/USD, SOL/USD, BTCUSDT)
- Stock/ETF tickers (e.g. AAPL, MSFT, QQQ, SPY, QQQUSDT, SPYUSDT)
- Commodity/Metal spot (e.g. XAUUSD, XAGUSD, COPPER)
- Index/CFD symbols (e.g. NAS100, US500, US30)
- Futures symbols (e.g. ES, NQ, YM, CL, GC)
"""

from __future__ import annotations

from market_analyzer.models.profile import AssetClass, Instrument, VolumeKind

# Supported major, minor, and exotic fiat currency codes
VALID_FOREX_CURRENCIES = frozenset({
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD",
    "SEK", "NOK", "DKK", "SGD", "HKD", "ZAR", "MXN", "TRY",
    "CNH", "PLN", "HUF", "CZK", "ILS", "THB", "KRW", "INR",
    "BRL", "CLP", "COP", "IDR", "MYR", "PHI", "TWD", "SAR",
    "AED",
})

# Supported crypto base assets
VALID_CRYPTO_CURRENCIES = frozenset({
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "AVAX", "DOT",
    "MATIC", "POL", "LINK", "LTC", "BCH", "UNI", "NEAR", "SUI", "APT",
    "ATOM", "SHIB", "PEPE", "XLM", "TRX", "TON", "FIL", "ICP", "ETC",
    "XMR", "HBAR", "RENDER", "ARB", "OP", "INJ", "KAS", "FET", "TAO",
    "STX", "AAVE", "MKR", "CRV", "FTM", "ALGO", "SAND", "MANA", "AXS",
    "VET", "EGLD", "FLOW", "XTZ", "THETA", "CHZ", "GALA", "ENJ", "1INCH",
    "SNX", "COMP", "LDO", "DYDX",
})

# Common crypto quote currencies
VALID_CRYPTO_QUOTES = frozenset({
    "USD", "USDT", "USDC", "EUR", "GBP", "JPY", "BTC", "ETH",
})

# Common ETF/Index symbols (Yahoo Finance / biquote format)
VALID_ETF_SYMBOLS = frozenset({
    # Major index ETFs
    "SPY", "SPYUSDT", "QQQ", "QQQUSDT", "DIA", "DIAUSDT", "IWM", "IWMUSDT",
    "VTI", "VTIUSDT", "VOO", "VOOUSDT", "VEA", "VEAUSDT", "VWO", "VWOUSDT",
    # Sector ETFs
    "XLF", "XLK", "XLE", "XLV", "XLI", "XLP", "XLY", "XLU", "XLB", "XLRE",
    "SMH", "SOXX", "ARKK", "ARKQ", "ARKW", "ARKG", "ARKF",
    # Commodity ETFs
    "GLD", "GLDUSDT", "SLV", "SLVUSDT", "USO", "USOUSDT", "UNG", "UNGUSDT",
    # International
    "EWJ", "EWJUSDT", "EWZ", "EWZUSDT", "EEM", "EEMUSDT", "EFA", "EFAUSDT",
    "FXI", "FXIUSDT", "KWEB", "KWEBUSDT",
    # Bond ETFs
    "TLT", "TLTUSDT", "IEF", "IEFUSDT", "SHY", "SHYUSDT", "LQD", "LQDUSDT",
    "HYG", "HYGUSDT", "JNK", "JNKUSDT",
    # Crypto-related ETFs
    "BITO", "BITOUSDT", "MSTR", "MSTRUSDT", "COIN", "COINUSDT", "RIOT", "RIOTUSDT",
    "MARA", "MARAUSDT", "HUT", "HUTUSDT",
    # Leveraged/Inverse
    "TQQQ", "TQQQUSDT", "SQQQ", "SQQQUSDT", "UPRO", "UPROUSDT", "SPXL", "SPXLUSDT",
    "SPXS", "SPXSUSDT", "TMF", "TMFUSDT", "TMV", "TMVUSDT",
})

# Common stock symbols (major US large-cap)
VALID_STOCK_SYMBOLS = frozenset({
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA", "BRK",
    "AVGO", "JPM", "JNJ", "V", "WMT", "UNH", "MA", "PG", "HD", "LLY",
    "CVX", "MRK", "ABBV", "PEP", "KO", "COST", "TMO", "ACN", "DIS", "ABT",
    "CRM", "ADBE", "NFLX", "INTC", "AMD", "CSCO", "ORCL", "IBM", "QCOM",
    "TXN", "AMAT", "HON", "LOW", "AMGN", "UNP", "INTU", "SBUX", "GILD",
    "MDT", "ISRG", "BKNG", "PYPL", "ADP", "VRTX", "REGN", "MU", "PANW",
    "SNOW", "CRWD", "PLTR", "ROKU", "ZM", "SQ", "SHOP", "TWLO", "OKTA",
    "DDOG", "NET", "ZS", "ESTC", "MDB", "ASAN", "TEAM", "WDAY", "NOW",
})

# Commodity/Metal spot symbols (MT5 / biquote format)
VALID_COMMODITY_SYMBOLS = frozenset({
    "XAUUSD", "XAUUSDT", "XAGUSD", "XAGUSDT",
    "XPTUSD", "XPTUSDT", "XPDUSD", "XPDUSDT",
    "COPPER", "COPPERUSDT", "CL", "CLUSDT", "NG", "NGUSDT",
    "HEATOIL", "HEATOILUSDT", "RBOB", "RBOBUSDT",
    "CORN", "CORNUSDT", "SOY", "SOYUSDT", "WHEAT", "WHEATUSDT",
    "SUGAR", "SUGARUSDT", "COCOA", "COCOAUSDT", "COFFEE", "COFFEEUSDT",
    "COTTON", "COTTONUSDT",
})

# Index/CFD symbols (common CFD broker format)
VALID_INDEX_SYMBOLS = frozenset({
    "NAS100", "US100", "USTEC", "NASDAQ",
    "US500", "US30", "US2000", "SPX500", "SPX", "DJI", "DJIA",
    "UK100", "GER40", "FRA40", "EU50", "ES35", "NL25",
    "JP225", "HK50", "CN50", "AUS200", "SING30",
    "VIX", "VXX", "UVXY", "SVXY",
})

# Futures symbols (CME, ICE, etc. root symbols)
VALID_FUTURES_SYMBOLS = frozenset({
    # Equity index futures
    "ES", "NQ", "YM", "RTY", "MES", "MNQ", "MYM", "M2K",
    # Commodity futures
    "CL", "NG", "GC", "SI", "HG", "PL", "PA",
    "ZC", "ZS", "ZW", "ZM", "ZL", "KE",
    "CC", "KC", "CT", "SB", "OJ",
    # Currency futures
    "6E", "6B", "6J", "6A", "6C", "6S", "6N",
    # Rate futures
    "ZB", "ZN", "ZF", "ZT", "GE",
    # Crypto futures
    "BTC", "ETH", "MBT", "MET",
})

# Common quote currencies for stocks/ETFs
VALID_STOCK_QUOTES = frozenset({"USD", "USDT"})

# Valid exchange suffixes for disambiguation
VALID_EXCHANGES = frozenset({"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS", "CBOE", "OTC"})


def parse_custom_symbol(raw_symbol: str) -> tuple[bool, AssetClass | None, str, str, str]:
    """Validate and parse a raw symbol string into components.

    Supports:
    - Forex: EUR/USD, EURUSD, GBP/JPY
    - Crypto: BTC/USD, ETHUSDT, SOLUSDC, DOGEUSD
    - Stocks/ETFs: AAPL, MSFT, QQQ, SPY, QQQUSDT, SPYUSDT
    - Commodities: XAUUSD, XAGUSD, COPPER
    - Indices/CFD: NAS100, US500, US30
    - Futures: ES, NQ, GC, CL

    Returns:
        (is_valid, asset_class, provider_symbol, clean_symbol, error_message)
        e.g., (True, AssetClass.FX, "EUR/USD", "EURUSD", "")
              (True, AssetClass.CRYPTO, "BTC/USD", "BTCUSD", "")
              (True, AssetClass.EQUITY, "AAPL", "AAPL", "")
              (True, AssetClass.INDEX, "QQQUSDT", "QQQUSDT", "")
              (False, None, "", "", "Error message")
    """
    if not raw_symbol or not raw_symbol.strip():
        return False, None, "", "", "Symbol cannot be empty."

    s = raw_symbol.strip().upper()

    # 1. Slash formatted pairs: BASE/QUOTE (e.g. EUR/USD, BTC/USD, ETH/USDT)
    if "/" in s:
        parts = s.split("/")
        if len(parts) != 2:
            return False, None, "", "", f"Invalid format '{s}'. Expected pair format BASE/QUOTE (e.g. EUR/USD, BTC/USD)."
        base, quote = parts[0].strip(), parts[1].strip()

        if base == quote:
            return False, None, "", "", f"Base and quote currency cannot be the same ({base}/{quote})."

        # Check Forex pair
        if base in VALID_FOREX_CURRENCIES and quote in VALID_FOREX_CURRENCIES:
            return True, AssetClass.FX, f"{base}/{quote}", f"{base}{quote}", ""

        # Check Crypto pair
        if base in VALID_CRYPTO_CURRENCIES and quote in (VALID_CRYPTO_QUOTES | VALID_FOREX_CURRENCIES):
            return True, AssetClass.CRYPTO, f"{base}/{quote}", f"{base}{quote}", ""

        # Check Commodity/Metal (e.g., XAU/USD, XAG/USD)
        if base in {"XAU", "XAG", "XPT", "XPD", "COPPER"} and quote in VALID_FOREX_CURRENCIES:
            return True, AssetClass.COMMODITY, f"{base}/{quote}", f"{base}{quote}", ""

        return False, None, "", "", (
            f"'{s}' is not a recognized pair. "
            f"Base '{base}' or Quote '{quote}' is not supported."
        )

    # 2. Standalone single crypto ticker (e.g. "BTC", "ETH", "SOL")
    if s in VALID_CRYPTO_CURRENCIES:
        return True, AssetClass.CRYPTO, f"{s}/USD", f"{s}USD", ""

    # 3. Direct symbol match for ETFs, Stocks, Indices, Commodities, Futures
    # Check ETF symbols first (most specific for biquote)
    if s in VALID_ETF_SYMBOLS:
        # Determine if it's an index ETF or sector/stock ETF
        if s in {"SPY", "SPYUSDT", "QQQ", "QQQUSDT", "DIA", "DIAUSDT", "IWM", "IWMUSDT"}:
            return True, AssetClass.INDEX, s, s, ""
        return True, AssetClass.ETF, s, s, ""

    # Check stock symbols
    if s in VALID_STOCK_SYMBOLS:
        return True, AssetClass.EQUITY, s, s, ""

    # Check commodity symbols
    if s in VALID_COMMODITY_SYMBOLS:
        return True, AssetClass.COMMODITY, s, s, ""

    # Check index/CFD symbols
    if s in VALID_INDEX_SYMBOLS:
        return True, AssetClass.INDEX, s, s, ""

    # Check futures symbols
    if s in VALID_FUTURES_SYMBOLS:
        return True, AssetClass.COMMODITY, s, s, ""  # Futures mapped to commodity for now

    # 4. Stablecoin quote pairs without slash (e.g. "ETHUSDT", "SOLUSDC", "BTCUSDT")
    for stable in ("USDT", "USDC"):
        if s.endswith(stable) and len(s) > len(stable):
            base = s[:-len(stable)]
            if base in VALID_CRYPTO_CURRENCIES:
                return True, AssetClass.CRYPTO, f"{base}/{stable}", f"{base}{stable}", ""
            if base in VALID_STOCK_SYMBOLS or base in VALID_ETF_SYMBOLS:
                return True, AssetClass.EQUITY, f"{base}/{stable}", f"{base}{stable}", ""

    # 5. Standard 6-character symbols (e.g. "EURUSD", "BTCUSD", "GBPUSD")
    if len(s) == 6:
        base, quote = s[:3], s[3:]
        if base == quote:
            return False, None, "", "", f"Base and quote currency cannot be the same ({base}/{quote})."
        if base in VALID_FOREX_CURRENCIES and quote in VALID_FOREX_CURRENCIES:
            return True, AssetClass.FX, f"{base}/{quote}", f"{base}{quote}", ""
        if base in VALID_CRYPTO_CURRENCIES and quote in (VALID_CRYPTO_QUOTES | VALID_FOREX_CURRENCIES):
            return True, AssetClass.CRYPTO, f"{base}/{quote}", f"{base}{quote}", ""
        if base in {"XAU", "XAG", "XPT", "XPD"} and quote in VALID_FOREX_CURRENCIES:
            return True, AssetClass.COMMODITY, f"{base}/{quote}", f"{base}{quote}", ""

    # 6. Variable-length crypto pairs (e.g. "DOGEUSD", "SHIBUSD", "AVAXUSD")
    for q_len in (3, 4):
        if len(s) > q_len:
            base, quote = s[:-q_len], s[-q_len:]
            if base in VALID_CRYPTO_CURRENCIES and quote in (VALID_CRYPTO_QUOTES | VALID_FOREX_CURRENCIES):
                return True, AssetClass.CRYPTO, f"{base}/{quote}", f"{base}{quote}", ""

    # 7. Stock/ETF with exchange suffix (e.g. "AAPL.NASDAQ", "SPY.NYSE")
    if "." in s:
        sym, exch = s.split(".", 1)
        if exch in VALID_EXCHANGES:
            if sym in VALID_STOCK_SYMBOLS:
                return True, AssetClass.EQUITY, sym, sym, ""
            if sym in VALID_ETF_SYMBOLS:
                return True, AssetClass.ETF, sym, sym, ""

    return False, None, "", "", (
        f"'{s}' is not a recognized symbol. "
        "Supported formats: "
        "Forex (EUR/USD, GBPUSD), "
        "Crypto (BTC/USD, ETHUSDT, SOL), "
        "Stocks/ETFs (AAPL, QQQ, SPYUSDT), "
        "Commodities (XAUUSD, COPPER), "
        "Indices (NAS100, US500), "
        "Futures (ES, NQ, GC)."
    )


def create_custom_instrument(raw_symbol: str) -> Instrument | None:
    """Create an Instrument definition for a validated symbol."""
    is_valid, asset_class, provider_sym, clean_sym, _ = parse_custom_symbol(raw_symbol)
    if not is_valid or asset_class is None:
        return None

    # Determine exchange, session, volume_kind based on asset class and symbol
    if asset_class == AssetClass.FX:
        base, quote = provider_sym.split("/")
        return Instrument(
            symbol=clean_sym,
            name=f"{base}/{quote} Forex Spot",
            exchange="FX",
            sector="Forex Currency Pair",
            currency=quote,
            asset_class=AssetClass.FX,
            provider_symbol=provider_sym,
            timezone="UTC",
            session="fx_metals",
            volume_kind=VolumeKind.TICK,
        )

    if asset_class == AssetClass.CRYPTO:
        base, quote = provider_sym.split("/")
        return Instrument(
            symbol=clean_sym,
            name=f"{base}/{quote} Crypto Spot",
            exchange="BINANCE",
            sector="Crypto",
            currency=quote,
            asset_class=AssetClass.CRYPTO,
            provider_symbol=provider_sym,
            timezone="UTC",
            session="crypto_24_7",
            volume_kind=VolumeKind.VENUE,
        )

    if asset_class == AssetClass.EQUITY:
        return Instrument(
            symbol=clean_sym,
            name=f"{clean_sym} Stock",
            exchange="NASDAQ",  # Default; could be enhanced
            sector="Stock",
            currency="USD",
            asset_class=AssetClass.EQUITY,
            provider_symbol=provider_sym,
            timezone="America/New_York",
            session="equity_us",
            volume_kind=VolumeKind.CONSOLIDATED,
        )

    if asset_class == AssetClass.ETF:
        # Check if it's an index ETF
        if clean_sym in {"SPY", "SPYUSDT", "QQQ", "QQQUSDT", "DIA", "DIAUSDT", "IWM", "IWMUSDT"}:
            return Instrument(
                symbol=clean_sym,
                name=f"{clean_sym} Index ETF",
                exchange="NASDAQ" if "QQQ" in clean_sym else "NYSE",
                sector="Equity Index ETF",
                currency="USD",
                asset_class=AssetClass.INDEX,
                provider_symbol=provider_sym,
                timezone="America/New_York",
                session="equity_us",
                volume_kind=VolumeKind.CONSOLIDATED,
            )
        return Instrument(
            symbol=clean_sym,
            name=f"{clean_sym} ETF",
            exchange="NASDAQ",
            sector="ETF",
            currency="USD",
            asset_class=AssetClass.ETF,
            provider_symbol=provider_sym,
            timezone="America/New_York",
            session="equity_us",
            volume_kind=VolumeKind.CONSOLIDATED,
        )

    if asset_class == AssetClass.INDEX:
        # Map common index symbols to biquote provider symbols
        index_map = {
            "NAS100": "QQQUSDT",
            "US100": "QQQUSDT",
            "USTEC": "QQQUSDT",
            "NASDAQ": "QQQUSDT",
            "US500": "SPYUSDT",
            "US30": "DIAUSDT",
            "SPX500": "SPYUSDT",
            "SPX": "SPYUSDT",
            "DJI": "DIAUSDT",
            "DJIA": "DIAUSDT",
        }
        provider_sym = index_map.get(clean_sym, clean_sym)
        return Instrument(
            symbol=clean_sym,
            name=f"{clean_sym} Index",
            exchange="INDEX",
            sector="Index/CFD",
            currency="USD",
            asset_class=AssetClass.INDEX,
            provider_symbol=provider_sym,
            timezone="America/New_York",
            session="equity_us",
            volume_kind=VolumeKind.CONSOLIDATED,
        )

    if asset_class == AssetClass.COMMODITY:
        # Check if it's a metal (XAU, XAG, etc.)
        if clean_sym.startswith(("XAU", "XAG", "XPT", "XPD")):
            base, quote = (clean_sym[:4], clean_sym[4:]) if len(clean_sym) > 4 else (clean_sym, "USD")
            return Instrument(
                symbol=clean_sym,
                name=f"{base}/{quote} Spot",
                exchange="COMMODITY",
                sector="Precious Metal",
                currency=quote,
                asset_class=AssetClass.COMMODITY,
                provider_symbol=provider_sym,
                timezone="UTC",
                session="fx_metals",
                volume_kind=VolumeKind.TICK,
            )
        # Futures or other commodities
        return Instrument(
            symbol=clean_sym,
            name=f"{clean_sym} Futures/Spot",
            exchange="CME",
            sector="Commodity Futures",
            currency="USD",
            asset_class=AssetClass.COMMODITY,
            provider_symbol=provider_sym,
            timezone="America/Chicago",
            session="equity_us",
            volume_kind=VolumeKind.CONSOLIDATED,
        )

    return None


async def search_symbols_biquote(query: str, live_only: bool = False, limit: int = 25) -> list[dict]:
    """Search symbols using biquote.io API.

    Returns a list of symbol metadata dicts from biquote.
    Requires a BiquoteProvider instance or direct HTTP call.
    """
    from market_analyzer.providers.biquote import BiquoteProvider
    provider = BiquoteProvider()
    try:
        results = await provider.search_symbols(query, live_only=live_only, limit=limit)
        return results
    except Exception:
        return []
    finally:
        await provider.aclose()


def get_supported_symbol_categories() -> dict[str, list[str]]:
    """Return all supported symbol categories with examples."""
    return {
        "forex": sorted(list(VALID_FOREX_CURRENCIES))[:20] + ["..."],
        "crypto": sorted(list(VALID_CRYPTO_CURRENCIES))[:20] + ["..."],
        "etfs": sorted(list(VALID_ETF_SYMBOLS))[:20] + ["..."],
        "stocks": sorted(list(VALID_STOCK_SYMBOLS))[:20] + ["..."],
        "commodities": sorted(list(VALID_COMMODITY_SYMBOLS)),
        "indices": sorted(list(VALID_INDEX_SYMBOLS)),
        "futures": sorted(list(VALID_FUTURES_SYMBOLS))[:20] + ["..."],
    }
