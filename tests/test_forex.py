"""Unit tests for forex symbol validation, parsing, and dynamic instrument creation."""

from market_analyzer.models.profile import AssetClass, VolumeKind
from market_analyzer.pipeline.forex import create_forex_instrument, parse_forex_symbol


def test_valid_forex_symbols():
    """Verify standard forex symbols parse correctly."""
    valid_cases = [
        ("EUR/USD", "EUR/USD", "EURUSD"),
        ("eur/usd", "EUR/USD", "EURUSD"),
        ("EURUSD", "EUR/USD", "EURUSD"),
        ("gbpusd", "GBP/USD", "GBPUSD"),
        ("USD/JPY", "USD/JPY", "USDJPY"),
        ("USDJPY", "USD/JPY", "USDJPY"),
        ("AUD/CAD", "AUD/CAD", "AUDCAD"),
        ("NZD/CHF", "NZD/CHF", "NZDCHF"),
        ("EUR/GBP", "EUR/GBP", "EURGBP"),
    ]

    for raw, expected_prov, expected_clean in valid_cases:
        is_valid, prov, clean, err = parse_forex_symbol(raw)
        assert is_valid is True, f"Expected {raw} to be valid, got error: {err}"
        assert prov == expected_prov
        assert clean == expected_clean
        assert err == ""


def test_invalid_forex_symbols_rejected():
    """Verify non-forex and malformed symbols are rejected."""
    invalid_cases = [
        ("AAPL", "not a valid Forex pair"),
        ("TSLA", "not a valid Forex pair"),
        ("BTCUSD", "not a recognized Forex fiat currency"),
        ("ETHUSD", "not a recognized Forex fiat currency"),
        ("GOLD", "not a valid Forex pair"),
        ("SPY", "not a valid Forex pair"),
        ("EUR/EUR", "cannot be the same"),
        ("USD/USD", "cannot be the same"),
        ("", "cannot be empty"),
        ("   ", "cannot be empty"),
        ("EUR/USD/GBP", "Invalid format"),
    ]

    for raw, expected_reason_fragment in invalid_cases:
        is_valid, prov, clean, err = parse_forex_symbol(raw)
        assert is_valid is False, f"Expected {raw} to be rejected"
        assert prov == ""
        assert clean == ""
        assert expected_reason_fragment.lower() in err.lower()


def test_create_forex_instrument():
    """Verify create_forex_instrument builds a complete Instrument model."""
    inst = create_forex_instrument("GBP/USD")
    assert inst is not None
    assert inst.symbol == "GBPUSD"
    assert inst.provider_symbol == "GBP/USD"
    assert inst.asset_class == AssetClass.FX
    assert inst.currency == "USD"
    assert inst.session == "fx_metals"
    assert inst.volume_kind == VolumeKind.TICK

    # Invalid returns None
    assert create_forex_instrument("AAPL") is None
