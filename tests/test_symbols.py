"""Unit tests for unified symbol parsing and instrument creation.

Supports Forex, Crypto, Stocks, ETFs, Indices, Commodities, Futures.
"""

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


def test_parse_custom_symbol_equity_etf():
    """Verify Stock/ETF symbols parse with correct AssetClass."""
    equity_cases = [
        ("AAPL", AssetClass.EQUITY, "AAPL", "AAPL"),
        ("MSFT", AssetClass.EQUITY, "MSFT", "MSFT"),
        ("SPY", AssetClass.INDEX, "SPY", "SPY"),  # Major index ETFs are INDEX
        ("QQQ", AssetClass.INDEX, "QQQ", "QQQ"),
        ("DIA", AssetClass.INDEX, "DIA", "DIA"),
        ("IWM", AssetClass.INDEX, "IWM", "IWM"),
        ("XLK", AssetClass.ETF, "XLK", "XLK"),
        ("ARKK", AssetClass.ETF, "ARKK", "ARKK"),
        ("SPYUSDT", AssetClass.INDEX, "SPYUSDT", "SPYUSDT"),
        ("QQQUSDT", AssetClass.INDEX, "QQQUSDT", "QQQUSDT"),
    ]
    for raw, exp_class, exp_prov, exp_clean in equity_cases:
        is_valid, asset_class, prov, clean, err = parse_custom_symbol(raw)
        assert is_valid is True, f"Failed on {raw}: {err}"
        assert asset_class == exp_class, f"{raw}: expected {exp_class}, got {asset_class}"
        assert prov == exp_prov
        assert clean == exp_clean
        assert err == ""


def test_parse_custom_symbol_commodity():
    """Verify Commodity/Metal symbols parse correctly."""
    commodity_cases = [
        ("XAUUSD", AssetClass.COMMODITY, "XAUUSD", "XAUUSD"),
        ("XAGUSD", AssetClass.COMMODITY, "XAGUSD", "XAGUSD"),
        ("XAU/USD", AssetClass.COMMODITY, "XAU/USD", "XAUUSD"),
        ("XAG/USD", AssetClass.COMMODITY, "XAG/USD", "XAGUSD"),
        ("COPPER", AssetClass.COMMODITY, "COPPER", "COPPER"),
    ]
    for raw, exp_class, exp_prov, exp_clean in commodity_cases:
        is_valid, asset_class, prov, clean, err = parse_custom_symbol(raw)
        assert is_valid is True, f"Failed on {raw}: {err}"
        assert asset_class == exp_class
        assert prov == exp_prov
        assert clean == exp_clean
        assert err == ""


def test_parse_custom_symbol_index():
    """Verify Index/CFD symbols parse correctly."""
    index_cases = [
        ("NAS100", AssetClass.INDEX, "NAS100", "NAS100"),
        ("US500", AssetClass.INDEX, "US500", "US500"),
        ("US30", AssetClass.INDEX, "US30", "US30"),
        ("USTEC", AssetClass.INDEX, "USTEC", "USTEC"),
        ("SPX500", AssetClass.INDEX, "SPX500", "SPX500"),
        ("DJI", AssetClass.INDEX, "DJI", "DJI"),
    ]
    for raw, exp_class, exp_prov, exp_clean in index_cases:
        is_valid, asset_class, prov, clean, err = parse_custom_symbol(raw)
        assert is_valid is True, f"Failed on {raw}: {err}"
        assert asset_class == exp_class
        assert prov == exp_prov
        assert clean == exp_clean
        assert err == ""


def test_parse_custom_symbol_futures():
    """Verify Futures symbols parse correctly."""
    futures_cases = [
        ("ES", AssetClass.COMMODITY, "ES", "ES"),
        ("NQ", AssetClass.COMMODITY, "NQ", "NQ"),
        ("GC", AssetClass.COMMODITY, "GC", "GC"),
        ("CL", AssetClass.COMMODITY, "CL", "CL"),
        ("6E", AssetClass.COMMODITY, "6E", "6E"),
        ("ZB", AssetClass.COMMODITY, "ZB", "ZB"),
    ]
    for raw, exp_class, exp_prov, exp_clean in futures_cases:
        is_valid, asset_class, prov, clean, err = parse_custom_symbol(raw)
        assert is_valid is True, f"Failed on {raw}: {err}"
        assert asset_class == exp_class
        assert prov == exp_prov
        assert clean == exp_clean
        assert err == ""


def test_parse_custom_symbol_invalid():
    """Verify truly invalid/malformed symbols are rejected with clear errors."""
    invalid = ["", "   ", "BTC/BTC", "USD/USD", "INVALID123", "NOTAREALSYMBOL"]
    for raw in invalid:
        is_valid, asset_class, prov, clean, err = parse_custom_symbol(raw)
        assert is_valid is False, f"Expected {raw} to be rejected"
        assert asset_class is None
        assert err != ""


def test_create_custom_instrument():
    """Verify instrument creation produces correct configurations for all asset classes."""
    # FX
    fx_inst = create_custom_instrument("EUR/USD")
    assert fx_inst is not None
    assert fx_inst.symbol == "EURUSD"
    assert fx_inst.provider_symbol == "EUR/USD"
    assert fx_inst.asset_class == AssetClass.FX
    assert fx_inst.session == "fx_metals"
    assert fx_inst.volume_kind == VolumeKind.TICK

    # Crypto
    crypto_inst = create_custom_instrument("SOL/USD")
    assert crypto_inst is not None
    assert crypto_inst.symbol == "SOLUSD"
    assert crypto_inst.provider_symbol == "SOL/USD"
    assert crypto_inst.asset_class == AssetClass.CRYPTO
    assert crypto_inst.session == "crypto_24_7"
    assert crypto_inst.volume_kind == VolumeKind.VENUE
    assert crypto_inst.exchange == "BINANCE"

    # Stock
    stock_inst = create_custom_instrument("AAPL")
    assert stock_inst is not None
    assert stock_inst.symbol == "AAPL"
    assert stock_inst.provider_symbol == "AAPL"
    assert stock_inst.asset_class == AssetClass.EQUITY
    assert stock_inst.session == "equity_us"
    assert stock_inst.volume_kind == VolumeKind.CONSOLIDATED

    # Index ETF
    index_etf = create_custom_instrument("SPY")
    assert index_etf is not None
    assert index_etf.symbol == "SPY"
    assert index_etf.provider_symbol == "SPY"
    assert index_etf.asset_class == AssetClass.INDEX
    assert index_etf.session == "equity_us"
    assert index_etf.volume_kind == VolumeKind.CONSOLIDATED

    # Sector ETF
    sector_etf = create_custom_instrument("XLK")
    assert sector_etf is not None
    assert sector_etf.asset_class == AssetClass.ETF

    # Commodity
    gold_inst = create_custom_instrument("XAUUSD")
    assert gold_inst is not None
    assert gold_inst.asset_class == AssetClass.COMMODITY
    assert gold_inst.session == "fx_metals"
    assert gold_inst.volume_kind == VolumeKind.TICK

    # Index/CFD
    index_inst = create_custom_instrument("NAS100")
    assert index_inst is not None
    assert index_inst.asset_class == AssetClass.INDEX
    assert index_inst.provider_symbol == "QQQUSDT"  # Maps to biquote ETF proxy
    assert index_inst.volume_kind == VolumeKind.CONSOLIDATED

    # Futures
    futures_inst = create_custom_instrument("ES")
    assert futures_inst is not None
    assert futures_inst.asset_class == AssetClass.COMMODITY  # Futures mapped to commodity

    # Truly invalid symbol returns None
    assert create_custom_instrument("") is None
    assert create_custom_instrument("INVALID123") is None
