"""Forex symbol validation and dynamic instrument construction.

Ensures user-entered custom search symbols strictly represent legitimate
fiat forex currency pairs (e.g. EUR/USD, GBP/USD, USD/JPY).
"""

from __future__ import annotations

from market_analyzer.models.profile import AssetClass, Instrument, VolumeKind

# Supported major, minor, and exotic fiat currency codes
VALID_FOREX_CURRENCIES = frozenset({
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD",
    "SEK", "NOK", "DKK", "SGD", "HKD", "ZAR", "MXN", "TRY",
    "CNH", "PLN", "HUF", "CZK", "ILS", "THB", "KRW", "INR",
    "BRL", "CLP", "COP", "IDR", "MYR", "PHP", "TWD", "SAR",
    "AED",
})


def parse_forex_symbol(raw_symbol: str) -> tuple[bool, str, str, str]:
    """Validate and parse a raw symbol string into forex components.

    Returns:
        (is_valid, provider_symbol, clean_symbol, error_message)
        e.g., (True, "EUR/USD", "EURUSD", "")
        or (False, "", "", "Reason why not forex")
    """
    if not raw_symbol or not raw_symbol.strip():
        return False, "", "", "Symbol cannot be empty."

    s = raw_symbol.strip().upper()

    if "/" in s:
        parts = s.split("/")
        if len(parts) != 2:
            return False, "", "", f"Invalid format '{s}'. Expected pair format BASE/QUOTE (e.g. EUR/USD)."
        base, quote = parts[0].strip(), parts[1].strip()
    elif len(s) == 6:
        base, quote = s[:3], s[3:]
    else:
        return False, "", "", (
            f"'{s}' is not a valid Forex pair. Forex symbols must be 6 letters "
            "(e.g. EURUSD) or formatted as BASE/QUOTE (e.g. EUR/USD)."
        )

    if base not in VALID_FOREX_CURRENCIES:
        return False, "", "", f"'{base}' in '{s}' is not a recognized Forex fiat currency."

    if quote not in VALID_FOREX_CURRENCIES:
        return False, "", "", f"'{quote}' in '{s}' is not a recognized Forex fiat currency."

    if base == quote:
        return False, "", "", f"Base currency and quote currency cannot be the same ({base}/{quote})."

    provider_symbol = f"{base}/{quote}"
    clean_symbol = f"{base}{quote}"
    return True, provider_symbol, clean_symbol, ""


def create_forex_instrument(raw_symbol: str) -> Instrument | None:
    """Create an Instrument definition for a validated forex pair."""
    is_valid, provider_sym, clean_sym, _ = parse_forex_symbol(raw_symbol)
    if not is_valid:
        return None

    base = clean_sym[:3]
    quote = clean_sym[3:]

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
