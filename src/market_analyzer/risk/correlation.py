"""Correlation matrix computation from provider daily candles."""

from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd

from market_analyzer.providers.base import MarketDataProvider, ProviderError


async def fetch_correlation_matrix(
    provider: MarketDataProvider,
    symbols: list[str],
    lookback_days: int = 60,
) -> pd.DataFrame:
    """
    Fetch daily candles for symbols and compute Pearson correlation matrix.
    
    Returns DataFrame with symbols as index/columns, NaN diagonal = 1.0.
    """
    if not symbols:
        return pd.DataFrame()
    
    # Fetch daily candles for all symbols in parallel
    semaphore = asyncio.Semaphore(4)
    
    async def fetch_daily(symbol: str) -> tuple[str, pd.Series | None]:
        async with semaphore:
            try:
                candles = await provider.get_candles(symbol, "1d", lookback_days)
                if len(candles) < 2:
                    return symbol, None
                # Build returns series
                closes = [float(c.close) for c in candles]
                returns = pd.Series(closes).pct_change().dropna()
                return symbol, returns
            except (ProviderError, TimeoutError, Exception):
                return symbol, None
    
    results = await asyncio.gather(*[fetch_daily(s) for s in symbols])
    
    # Build returns DataFrame
    returns_data = {}
    for symbol, returns in results:
        if returns is not None and len(returns) > 10:
            returns_data[symbol] = returns
    
    if len(returns_data) < 2:
        # Not enough data for correlation
        return pd.DataFrame(index=symbols, columns=symbols, dtype=float)
    
    returns_df = pd.DataFrame(returns_data)
    # Align all series to same dates (inner join)
    returns_df = returns_df.dropna(how="all")
    
    if returns_df.empty or len(returns_df.columns) < 2:
        return pd.DataFrame(index=symbols, columns=symbols, dtype=float)
    
    # Compute correlation matrix
    corr_matrix = returns_df.corr(method="pearson")
    
    # Ensure all requested symbols present (fill missing with NaN)
    corr_matrix = corr_matrix.reindex(index=symbols, columns=symbols)
    np.fill_diagonal(corr_matrix.values, 1.0)
    
    return corr_matrix


def correlation_penalty(
    symbol: str,
    corr_matrix: pd.DataFrame,
    open_positions: dict[str, float],
    threshold: float = 0.75,
) -> float:
    """
    Compute correlation penalty for a symbol given open positions.
    
    Returns multiplier in (0, 1]. 1.0 = no penalty.
    """
    if corr_matrix.empty or symbol not in corr_matrix.index:
        return 1.0
    
    if not open_positions:
        return 1.0
    
    # Find max correlation with any open position
    max_corr = 0.0
    for open_sym in open_positions:
        if open_sym in corr_matrix.columns:
            corr_val = corr_matrix.loc[symbol, open_sym]
            if pd.notna(corr_val):
                max_corr = max(max_corr, abs(corr_val))
    
    if max_corr <= threshold:
        return 1.0
    
    # Linear penalty from threshold to 1.0
    # At threshold -> 1.0, at 1.0 -> 0.5
    penalty = 1.0 - 0.5 * (max_corr - threshold) / (1.0 - threshold)
    return max(penalty, 0.5)


def correlation_warnings(
    corr_matrix: pd.DataFrame,
    approved_positions: list,
    threshold: float = 0.75,
) -> list[str]:
    """Generate warnings for highly correlated approved positions."""
    warnings = []
    if corr_matrix.empty:
        return warnings
    
    approved_symbols = [p.symbol for p in approved_positions]
    for i, sym1 in enumerate(approved_symbols):
        for sym2 in approved_symbols[i+1:]:
            if sym1 in corr_matrix.index and sym2 in corr_matrix.columns:
                corr_val = corr_matrix.loc[sym1, sym2]
                if pd.notna(corr_val) and abs(corr_val) >= threshold:
                    warnings.append(
                        f"High correlation ({corr_val:.2f}) between {sym1} and {sym2} "
                        f"exceeds threshold {threshold:.2f}"
                    )
    return warnings