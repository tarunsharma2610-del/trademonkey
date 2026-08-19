"""
Historical data engine.

Replaces the old hardcoded 2024 date range with:
- Dynamic date ranges derived from the required candle count + timeframe.
- Candle validation (timestamp ordering, duplicates, OHLC consistency, volume).
- Incremental caching keyed by (instrument_key, timeframe) so the full history
  is not re-downloaded every cycle.
- Stale-data detection: if the latest candle does not cover the requested end
  date, the data is flagged stale so callers do not trade on it.

This module never invents candles. It only requests real data from the provider.
"""
import math
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# Upstox historical-candle interval names -> minutes per candle
TIMEFRAME_MINUTES = {
    "1minute": 1,
    "5minute": 5,
    "15minute": 15,
    "30minute": 30,
    "1hour": 60,
    "60minute": 60,
    "2hour": 120,
    "4hour": 240,
    "day": 1440,
    "1day": 1440,
}

# NSE equity session 09:15-15:30 IST (config.MARKET_OPEN..MARKET_CLOSE)
MARKET_MINUTES_PER_DAY = 375

# Rough calendar-day multiplier over pure market-time estimates (accounts for
# weekends; a real exchange calendar replaces this in the calendar phase).
WEEKEND_BUFFER = 1.25
HOLIDAY_BUFFER_DAYS = 2


class CandleValidationError(ValueError):
    """Raised when historical data is structurally unusable."""


def timeframe_minutes(timeframe):
    return TIMEFRAME_MINUTES.get(timeframe, 30)


def parse_ts(value):
    """Accept Upstox ISO timestamps or epoch floats, always return IST-aware datetime."""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=IST)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(IST)


def historical_date_range(required_candles, timeframe, end_date=None, buffer_days=HOLIDAY_BUFFER_DAYS):
    """Returns (from_date, to_date) ISO date strings spanning enough calendar
    days to yield >= required_candles of the given timeframe ending at
    end_date (default today, IST). Never hardcoded."""
    end = end_date or datetime.now(IST).date()
    interval_min = timeframe_minutes(timeframe)
    if interval_min >= 1440:
        trading_days = required_candles
        calendar_days = int(trading_days * 7 / 5 * WEEKEND_BUFFER) + buffer_days
        from_d = end - timedelta(days=calendar_days)
        return from_d.isoformat(), end.isoformat()

    total_minutes = required_candles * interval_min
    trading_days = max(1, math.ceil(total_minutes / MARKET_MINUTES_PER_DAY))
    calendar_days = int(trading_days * 7 / 5 * WEEKEND_BUFFER) + buffer_days
    from_d = end - timedelta(days=calendar_days)
    return from_d.isoformat(), end.isoformat()


def validate_candles(raw_candles, timeframe="30minute"):
    """Validates a raw candle list. Returns (valid_candles, issues).

    Rejects malformed candles (missing/NaN fields), OHLC inconsistencies,
    negative volume, duplicate/out-of-order timestamps. An empty input yields
    the issue "empty". Never fills in missing values."""
    if not raw_candles:
        return [], ["empty"]
    issues = []
    valid = []
    last_ts = None
    for c in raw_candles:
        try:
            ts = parse_ts(c["ts"])
            o = float(c["open"])
            h = float(c["high"])
            low = float(c["low"])
            close = float(c["close"])
            volume = c.get("volume")
        except (KeyError, TypeError, ValueError):
            issues.append("malformed")
            continue
        if math.isnan(o) or math.isnan(h) or math.isnan(low) or math.isnan(close):
            issues.append("malformed")
            continue
        if h < max(o, close) or low > min(o, close):
            issues.append("ohlc_inconsistent")
            continue
        if volume is not None:
            try:
                if float(volume) < 0:
                    issues.append("negative_volume")
                    continue
            except (TypeError, ValueError):
                issues.append("malformed")
                continue
        if last_ts is not None and ts <= last_ts:
            issues.append("timestamp_not_ordered")
            continue
        last_ts = ts
        valid.append({
            "ts": c["ts"],
            "open": o,
            "high": h,
            "low": low,
            "close": close,
            "volume": volume,
            "oi": c.get("oi"),
        })
    return valid, issues


class HistoricalDataService:
    """Caching wrapper over a market-data provider.

    Cache entries are keyed by (instrument_key, timeframe) and store candles,
    latest timestamp, fetch timestamp, and source. Only missing/incremental
    data is requested when a cache is already fresh enough.
    """

    def __init__(self, provider, now_fn=None):
        self.provider = provider
        self._cache = {}
        self._now = now_fn or (lambda: datetime.now(IST))

    def _merge(self, existing, incoming, timeframe):
        """Concatenate cached history with newly fetched candles, keeping order.
        Re-validation drops any duplicate/overlapping candles."""
        return (existing or []) + (incoming or [])

    def get_candles(self, instrument_key, timeframe, required_candles,
                    end_date=None, allow_cache=True):
        key = (instrument_key, timeframe)
        end_date = end_date or self._now().date()
        from_date, to_date = historical_date_range(required_candles, timeframe, end_date=end_date)

        cached = self._cache.get(key)
        if allow_cache and cached and cached.get("latest_ts"):
            last = parse_ts(cached["latest_ts"])
            if last.date() >= end_date and len(cached["candles"]) >= required_candles:
                candles, issues = validate_candles(cached["candles"], timeframe)
                return self._result(instrument_key, timeframe, candles, issues,
                                    end_date, cached=cached)
            # Incremental: only request the missing tail.
            incremental_from = (last + timedelta(minutes=timeframe_minutes(timeframe))).date().isoformat()
            from_date = max(from_date, incremental_from)

        raw = self.provider.get_historical_candles(instrument_key, timeframe, from_date, to_date)
        candles, issues = validate_candles(raw, timeframe)
        if cached:
            candles = self._merge(cached["candles"], candles, timeframe)
            candles, issues = validate_candles(candles, timeframe)

        latest_ts = candles[-1]["ts"] if candles else None
        self._cache[key] = {
            "candles": candles,
            "latest_ts": latest_ts,
            "fetched_at": self._now().isoformat(),
            "source": "upstox",
        }
        return self._result(instrument_key, timeframe, candles, issues,
                            end_date, cached=self._cache[key])

    def _result(self, instrument_key, timeframe, candles, issues, end_date, cached):
        latest_ts = cached.get("latest_ts") if cached else (candles[-1]["ts"] if candles else None)
        is_stale = self._is_stale(latest_ts, end_date)
        return {
            "instrument_key": instrument_key,
            "timeframe": timeframe,
            "candles": candles,
            "count": len(candles),
            "issues": issues,
            "valid": bool(candles) and not issues and not is_stale,
            "latest_ts": latest_ts,
            "is_stale": is_stale,
            "source": cached.get("source", "upstox") if cached else "upstox",
            "fetched_at": cached.get("fetched_at") if cached else None,
        }

    def _is_stale(self, latest_ts, end_date, tolerance_days=1):
        """Data is stale if it does not cover the requested end date."""
        if not latest_ts:
            return True
        try:
            last = parse_ts(latest_ts)
        except (TypeError, ValueError):
            return True
        return last.date() < end_date - timedelta(days=tolerance_days)

    def cache_stats(self):
        return {k: {"count": len(v["candles"]), "latest_ts": v["latest_ts"]}
                for k, v in self._cache.items()}
