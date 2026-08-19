"""
Tests for the market-data layer (Phase 2: enforce real market data only).

Covers the fail-closed contract:
- No Upstox token  -> explicit MarketDataConfigError, never fake prices.
- No demo/mock/random data helpers exist in the production client.
- Response parsing for LTP / OHLC quotes / historical candles.
- Heatmap uses real OHLC quotes (no demo previous-close placeholder).
"""
import pytest

import config
from upstox_client import UpstoxClient, MarketDataConfigError


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


LTP_RESP = {
    "data": {
        "NSE_EQ|INE002A01018": {
            "instrument_token": "NSE_EQ|INE002A01018",
            "last_price": 2456.30,
        }
    }
}

OHLC_RESP = {
    "data": {
        "NSE_EQ|INE002A01018": {
            "instrument_token": "NSE_EQ|INE002A01018",
            "last_price": 2456.30,
            "ohlc": {"open": 2440.0, "high": 2460.0, "low": 2435.0, "close": 2430.1},
        }
    }
}

CANDLE_RESP = {
    "data": {
        "candles": [
            ["2024-06-03T09:15:00+05:30", 100.0, 102.0, 99.0, 101.0, 5000, 0],
            ["2024-06-03T09:45:00+05:30", 101.0, 103.0, 100.5, 102.5, 6000, 0],
        ]
    }
}


@pytest.fixture
def no_token_client():
    return UpstoxClient(access_token="")


@pytest.fixture
def token_client():
    return UpstoxClient(access_token="test-token")


def test_no_demo_helpers_exist(no_token_client):
    for attr in ("_demo_price", "_demo_candles", "_start_demo_feed", "demo_mode"):
        assert not hasattr(no_token_client, attr), f"demo helper {attr} must be removed"


def test_get_ltp_fails_closed_without_token(no_token_client):
    with pytest.raises(MarketDataConfigError):
        no_token_client.get_ltp(["NSE_EQ|INE002A01018"])


def test_get_quote_fails_closed_without_token(no_token_client):
    with pytest.raises(MarketDataConfigError):
        no_token_client.get_quote(["NSE_EQ|INE002A01018"])


def test_historical_fails_closed_without_token(no_token_client):
    with pytest.raises(MarketDataConfigError):
        no_token_client.get_historical_candles(
            "NSE_EQ|INE002A01018", "30minute", "2024-06-01", "2024-06-03"
        )


def test_start_feed_fails_closed_without_token(no_token_client):
    with pytest.raises(MarketDataConfigError):
        no_token_client.start_feed(["NSE_EQ|INE002A01018"], lambda k, v: None)


def test_config_error_message_is_explicit(no_token_client):
    with pytest.raises(MarketDataConfigError, match="UPSTOX_ACCESS_TOKEN"):
        no_token_client.get_ltp(["NSE_EQ|INE002A01018"])


def test_get_ltp_parses_response(token_client, monkeypatch):
    monkeypatch.setattr(token_client._session, "get", lambda *a, **k: _FakeResp(LTP_RESP))
    out = token_client.get_ltp(["NSE_EQ|INE002A01018"])
    assert out == {"NSE_EQ|INE002A01018": 2456.30}


def test_get_quote_parses_prev_close(token_client, monkeypatch):
    monkeypatch.setattr(token_client._session, "get", lambda *a, **k: _FakeResp(OHLC_RESP))
    out = token_client.get_quote(["NSE_EQ|INE002A01018"])
    q = out["NSE_EQ|INE002A01018"]
    assert q["last_price"] == 2456.30
    assert q["prev_close"] == 2430.1


def test_historical_parses_candles(token_client, monkeypatch):
    monkeypatch.setattr(token_client._session, "get", lambda *a, **k: _FakeResp(CANDLE_RESP))
    out = token_client.get_historical_candles(
        "NSE_EQ|INE002A01018", "30minute", "2024-06-01", "2024-06-03"
    )
    assert len(out) == 2
    assert out[0]["close"] == 101.0
    assert out[1]["open"] == 101.0
    assert out[1]["volume"] == 6000


def test_heatmap_uses_real_ohlc_quotes(monkeypatch):
    import heatmap
    from instrument_master import instrument_master

    instrument_master._nifty500 = [
        {"symbol": "RELIANCE", "isin": "INE002A01018", "sector": "Energy"},
        {"symbol": "TCS", "isin": "INE467B01029", "sector": "IT"},
    ]
    instrument_master._equity_by_symbol = {r["symbol"]: r for r in instrument_master._nifty500}

    class _FakeUpstox:
        def get_quote(self, keys):
            return {
                "NSE_EQ|INE002A01018": {"last_price": 100.0, "prev_close": 90.0},
                "NSE_EQ|INE467B01029": {"last_price": 200.0, "prev_close": 200.0},
            }

    rows = heatmap.compute_heatmap(upstox_client=_FakeUpstox(), sample_per_sector=10)
    sectors = {r["sector"]: r["change_pct"] for r in rows}
    assert sectors["Energy"] == round((100.0 - 90.0) / 90.0 * 100, 2)
    assert "IT" in sectors


def test_config_no_demo_mode():
    assert not hasattr(config, "DEMO_MODE")
