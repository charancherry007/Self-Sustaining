"""Forex and Crypto symbol validation and dynamic instrument construction.

Supports user-entered search symbols representing legitimate Forex currency pairs
(e.g. EUR/USD, GBP/USD, USD/JPY) and Crypto pairs (e.g. BTC/USD, ETH/USD, SOL/USD, BTCUSDT).
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


def parse_custom_symbol(raw_symbol: str) -> tuple[bool, AssetClass | None, str, str, str]:
    """Validate and parse a raw symbol string into Forex or Crypto components.

    Returns:
        (is_valid, asset_class, provider_symbol, clean_symbol, error_message)
        e.g., (True, AssetClass.FX, "EUR/USD", "EURUSD", "")
              (True, AssetClass.CRYPTO, "BTC/USD", "BTCUSD", "")
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

        return False, None, "", "", (
            f"'{s}' is not a recognized Forex or Crypto pair. "
            f"Base '{base}' or Quote '{quote}' is not supported."
        )

    # 2. Standalone single crypto ticker (e.g. "BTC", "ETH", "SOL")
    if s in VALID_CRYPTO_CURRENCIES:
        return True, AssetClass.CRYPTO, f"{s}/USD", f"{s}USD", ""

    # 3. Stablecoin quote pairs without slash (e.g. "ETHUSDT", "SOLUSDC", "BTCUSDT")
    for stable in ("USDT", "USDC"):
        if s.endswith(stable) and len(s) > len(stable):
            base = s[:-len(stable)]
            if base in VALID_CRYPTO_CURRENCIES:
                return True, AssetClass.CRYPTO, f"{base}/{stable}", f"{base}{stable}", ""

    # 4. Standard 6-character symbols (e.g. "EURUSD", "BTCUSD", "GBPUSD")
    if len(s) == 6:
        base, quote = s[:3], s[3:]
        if base == quote:
            return False, None, "", "", f"Base and quote currency cannot be the same ({base}/{quote})."
        if base in VALID_FOREX_CURRENCIES and quote in VALID_FOREX_CURRENCIES:
            return True, AssetClass.FX, f"{base}/{quote}", f"{base}{quote}", ""
        if base in VALID_CRYPTO_CURRENCIES and quote in (VALID_CRYPTO_QUOTES | VALID_FOREX_CURRENCIES):
            return True, AssetClass.CRYPTO, f"{base}/{quote}", f"{base}{quote}", ""

    # 5. Variable-length crypto pairs (e.g. "DOGEUSD", "SHIBUSD", "AVAXUSD")
    for q_len in (3, 4):
        if len(s) > q_len:
            base, quote = s[:-q_len], s[-q_len:]
            if base in VALID_CRYPTO_CURRENCIES and quote in (VALID_CRYPTO_QUOTES | VALID_FOREX_CURRENCIES):
                return True, AssetClass.CRYPTO, f"{base}/{quote}", f"{base}{quote}", ""

    return False, None, "", "", (
        f"'{s}' is not a recognized Forex or Crypto symbol. "
        "Please enter a valid Forex pair (e.g. EUR/USD, GBP/USD, USD/JPY) "
        "or Crypto pair (e.g. BTC/USD, ETH/USD, SOL/USD, BTCUSDT)."
    )


def create_custom_instrument(raw_symbol: str) -> Instrument | None:
    """Create an Instrument definition for a validated Forex or Crypto symbol."""
    is_valid, asset_class, provider_sym, clean_sym, _ = parse_custom_symbol(raw_symbol)
    if not is_valid or asset_class is None:
        return None

    base, quote = provider_sym.split("/")

    if asset_class == AssetClass.FX:
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
