"""Unit tests for unified Forex and Crypto symbol parsing and instrument creation."""

from market_analyzer.models.profile import AssetClass, VolumeKind
from market_analyzer.pipeline.symbols import create_custom_instrument, parse_custom_symbol


def test_parse_custom_symbol_forex():
    """Verify Forex pairs parse with AssetClass.FX."""
    forex_cases = [
        ("EUR/USD", "EUR/USD", "EURUSD"),
        ("GBPUSD", "GBP/USD", "GBPUSD"),
        ("USD/JPY", "USD/JPY", "USDJPY"),
        ("aud/cad", "AUD/CAD", "AUDCAD"),
    ]
    for raw, exp_prov, exp_clean in forex_cases:
        is_valid, asset_class, prov, clean, err = parse_custom_symbol(raw)
        assert is_valid is True, f"Failed on {raw}: {err}"
        assert asset_class == AssetClass.FX
        assert prov == exp_prov
        assert clean == exp_clean
        assert err == ""


def test_parse_custom_symbol_crypto():
    """Verify Crypto pairs parse with AssetClass.CRYPTO."""
    crypto_cases = [
        ("BTC/USD", "BTC/USD", "BTCUSD"),
        ("ETH/USDT", "ETH/USDT", "ETHUSDT"),
        ("SOL/USD", "SOL/USD", "SOLUSD"),
        ("BTCUSD", "BTC/USD", "BTCUSD"),
        ("ETHUSDT", "ETH/USDT", "ETHUSDT"),
        ("DOGEUSD", "DOGE/USD", "DOGEUSD"),
        ("BTC", "BTC/USD", "BTCUSD"),
        ("SOL", "SOL/USD", "SOLUSD"),
    ]
    for raw, exp_prov, exp_clean in crypto_cases:
        is_valid, asset_class, prov, clean, err = parse_custom_symbol(raw)
        assert is_valid is True, f"Failed on {raw}: {err}"
        assert asset_class == AssetClass.CRYPTO
        assert prov == exp_prov
        assert clean == exp_clean
        assert err == ""


def test_parse_custom_symbol_invalid():
    """Verify equities, indices, and malformed symbols are rejected with clear errors."""
    invalid = ["AAPL", "TSLA", "SPY", "QQQ", "", "   ", "BTC/BTC", "USD/USD"]
    for raw in invalid:
        is_valid, asset_class, prov, clean, err = parse_custom_symbol(raw)
        assert is_valid is False, f"Expected {raw} to be rejected"
        assert asset_class is None
        assert err != ""


def test_create_custom_instrument():
    """Verify instrument creation produces correct configurations for FX and Crypto."""
    fx_inst = create_custom_instrument("EUR/USD")
    assert fx_inst is not None
    assert fx_inst.symbol == "EURUSD"
    assert fx_inst.provider_symbol == "EUR/USD"
    assert fx_inst.asset_class == AssetClass.FX
    assert fx_inst.session == "fx_metals"
    assert fx_inst.volume_kind == VolumeKind.TICK

    crypto_inst = create_custom_instrument("SOL/USD")
    assert crypto_inst is not None
    assert crypto_inst.symbol == "SOLUSD"
    assert crypto_inst.provider_symbol == "SOL/USD"
    assert crypto_inst.asset_class == AssetClass.CRYPTO
    assert crypto_inst.session == "crypto_24_7"
    assert crypto_inst.volume_kind == VolumeKind.VENUE
    assert crypto_inst.exchange == "BINANCE"

    # Invalid symbol returns None
    assert create_custom_instrument("AAPL") is None
