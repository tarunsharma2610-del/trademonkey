"""
Tests for the historical-data engine (Phase 3): dynamic date ranges, candle
validation, incremental caching, staleness, and scanner minimum-candle rules.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import scanner
from historical_data import (
    HistoricalDataService,
    historical_date_range,
    parse_ts,
    validate_candles,
    timeframe_minutes,
)

IST = ZoneInfo("Asia/Kolkata")


def make_candles(n, start="2026-06-01T09:15:00+05:30", interval_min=30):
    start_dt = parse_ts(start)
    out = []
    for i in range(n):
        ts = start_dt + timedelta(minutes=interval_min * i)
        o = 100.0 + i
        c = 101.0 + i
        h = max(o, c) + 1.0
        l = min(o, c) - 1.0
        out.append({
            "ts": ts.isoformat(), "open": o, "high": h, "low": l,
            "close": c, "volume": 1000 + i, "oi": 0,
        })
    return out


class _FakeProvider:
    def __init__(self, candles_factory):
        self._factory = candles_factory
        self.calls = []

    def get_historical_candles(self, instrument_key, interval, from_date, to_date):
        self.calls.append((instrument_key, interval, from_date, to_date))
        return self._factory()


# ---------------------------------------------------------------------------
# Dynamic date range
# ---------------------------------------------------------------------------

def test_date_range_is_dynamic_and_never_2024():
    from_d, to_d = historical_date_range(100, "30minute", end_date=datetime(2026, 6, 1).date())
    assert to_d == "2026-06-01"
    assert from_d != "2024-01-01"
    assert from_d < to_d


def test_date_range_covers_required_candles():
    required, interval_min = 100, 30
    from_d, to_d = historical_date_range(required, "30minute", end_date=datetime(2026, 6, 1).date())
    span_days = (parse_ts(f"{to_d}T00:00:00+05:30") - parse_ts(f"{from_d}T00:00:00+05:30")).days
    # 100 * 30min = 3000 market-minutes; ~375 min/day -> ~8 trading days
    assert span_days >= 8


def test_timeframe_minutes():
    assert timeframe_minutes("30minute") == 30
    assert timeframe_minutes("day") == 1440


# ---------------------------------------------------------------------------
# Candle validation
# ---------------------------------------------------------------------------

def test_validate_accepts_good_candles():
    candles = make_candles(25)
    valid, issues = validate_candles(candles, "30minute")
    assert len(valid) == 25
    assert issues == []


def test_validate_rejects_duplicate_timestamps():
    candles = make_candles(5)
    candles.append(dict(candles[-1]))
    valid, issues = validate_candles(candles, "30minute")
    assert "timestamp_not_ordered" in issues
    assert len(valid) < len(candles)


def test_validate_rejects_out_of_order():
    candles = make_candles(5)
    candles[1], candles[3] = candles[3], candles[1]
    valid, issues = validate_candles(candles, "30minute")
    assert "timestamp_not_ordered" in issues


def test_validate_rejects_ohlc_inconsistency():
    candles = make_candles(5)
    candles[2]["high"] = candles[2]["open"] - 5.0
    valid, issues = validate_candles(candles, "30minute")
    assert "ohlc_inconsistent" in issues


def test_validate_rejects_malformed_and_empty():
    candles = make_candles(3)
    candles[1]["close"] = "not-a-number"
    valid, issues = validate_candles(candles, "30minute")
    assert "malformed" in issues

    valid, issues = validate_candles([], "30minute")
    assert issues == ["empty"]


def test_validate_rejects_negative_volume():
    candles = make_candles(3)
    candles[0]["volume"] = -5
    valid, issues = validate_candles(candles, "30minute")
    assert "negative_volume" in issues


# ---------------------------------------------------------------------------
# HistoricalDataService (caching + incremental fetch)
# ---------------------------------------------------------------------------

def test_service_fetches_then_caches_incrementally():
    provider = _FakeProvider(lambda: make_candles(50))
    service = HistoricalDataService(provider, now_fn=lambda: datetime(2026, 6, 2, 5, 0, tzinfo=IST))

    r1 = service.get_candles("NSE_EQ|X", "30minute", 30)
    assert r1["valid"] and r1["count"] == 50
    assert len(provider.calls) == 1

    r2 = service.get_candles("NSE_EQ|X", "30minute", 30)
    assert r2["valid"] and r2["count"] == 50
    assert len(provider.calls) == 1, "second call should be served from cache"


def test_service_requires_real_data_without_fallback():
    provider = _FakeProvider(lambda: [])
    service = HistoricalDataService(provider, now_fn=lambda: datetime(2026, 6, 2, 5, 0, tzinfo=IST))
    r = service.get_candles("NSE_EQ|X", "30minute", 30)
    assert not r["valid"]
    assert r["is_stale"] is True


def test_service_marks_stale_when_latest_does_not_cover_end():
    # Candle series ends well before the requested end date.
    provider = _FakeProvider(lambda: make_candles(30, start="2026-01-05T09:15:00+05:30"))
    service = HistoricalDataService(provider)
    r = service.get_candles("NSE_EQ|X", "30minute", 30, end_date=datetime(2026, 6, 1).date())
    assert r["is_stale"] is True
    assert not r["valid"]


# ---------------------------------------------------------------------------
# Scanner minimum-candle requirements
# ---------------------------------------------------------------------------

def test_required_candles_for_params():
    params = {"factors": {"sma_crossover": 0.5, "rsi": 0.5}}
    assert scanner.required_candles_for_params(params) == 21
    params = {"factors": {"oi_change": 1.0}}
    assert scanner.required_candles_for_params(params) == 5
    assert scanner.required_candles_for_params({"factors": {}}) == scanner.DEFAULT_MIN_CANDLES


def test_scan_gives_no_signal_on_insufficient_candles():
    class _ShortProvider:
        def get_historical_candles(self, instrument_key, interval, from_date, to_date):
            return make_candles(5)

    results = scanner.run_scan(
        _ShortProvider(),
        ["RELIANCE"],
        lambda s: "NSE_EQ|INE002A01018",
        {"timeframe": "30minute", "factors": {"sma_crossover": 1.0}},
    )
    assert len(results) == 1
    assert results[0]["score"] == 0.0
    assert results[0]["error"] == "insufficient_or_invalid_data"
    assert results[0]["data_quality"] is False


def test_scan_scores_with_enough_valid_candles():
    class _GoodProvider:
        def get_historical_candles(self, instrument_key, interval, from_date, to_date):
            return make_candles(40)

    provider = _GoodProvider()
    service = HistoricalDataService(provider, now_fn=lambda: datetime(2026, 6, 2, 5, 0, tzinfo=IST))
    results = scanner.run_scan(
        provider,
        ["RELIANCE"],
        lambda s: "NSE_EQ|INE002A01018",
        {"timeframe": "30minute", "factors": {"sma_crossover": 1.0}},
        historical_service=service,
    )
    assert len(results) == 1
    assert results[0]["data_quality"] is True
    assert results[0]["score"] > 0.0
    assert results[0]["last_close"] is not None
