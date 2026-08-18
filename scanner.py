"""
Scanner: pulls candles for a universe (Nifty 500 stocks, or MCX commodities),
computes a weighted multi-factor score per strategy config, and returns
ranked candidates for the strategy engine to act on.
"""
import math
from statistics import mean

from instrument_master import instrument_master

# ---------------------------------------------------------------------------
# Universes, sourced from data/nifty500.json (real 501-stock list with sectors,
# downloaded from NSE indices data) and data/mcx_commodities.json.
# ---------------------------------------------------------------------------
NIFTY500 = instrument_master.nifty500_symbols()
MCX_COMMODITIES = instrument_master.mcx_symbols()

# Kept for backwards compatibility with earlier code/tests that referenced a
# small sample explicitly; prefer NIFTY500 for real scans.
DEMO_NIFTY500_SAMPLE = NIFTY500[:10] if NIFTY500 else [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "ITC", "LT", "AXISBANK", "BHARTIARTL"
]


def sma(values, period):
    if len(values) < period:
        return None
    return mean(values[-period:])


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(-period, 0):
        change = closes[i] - closes[i - 1]
        (gains if change > 0 else losses).append(abs(change))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period if losses else 1e-9
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def factor_sma_crossover(candles):
    closes = [c["close"] for c in candles]
    fast, slow = sma(closes, 9), sma(closes, 21)
    if fast is None or slow is None:
        return 50.0
    spread_pct = (fast - slow) / slow * 100
    return max(0, min(100, 50 + spread_pct * 10))


def factor_rsi(candles):
    closes = [c["close"] for c in candles]
    val = rsi(closes)
    # Score peaks around RSI 55-65 (momentum without being overbought)
    if val >= 70:
        return max(0, 100 - (val - 70) * 4)
    if val <= 40:
        return max(0, val)
    return 60 + (val - 55) * 1.5 if val > 55 else 50 + (val - 40) * 0.5


def factor_volume_spike(candles):
    vols = [c["volume"] for c in candles]
    if len(vols) < 10:
        return 50.0
    avg_vol = mean(vols[-20:-1]) if len(vols) >= 20 else mean(vols[:-1])
    latest = vols[-1]
    if avg_vol == 0:
        return 50.0
    ratio = latest / avg_vol
    return max(0, min(100, 40 + (ratio - 1) * 40))


def factor_breakout(candles):
    highs = [c["high"] for c in candles]
    closes = [c["close"] for c in candles]
    if len(highs) < 20:
        return 50.0
    recent_high = max(highs[-20:-1])
    latest_close = closes[-1]
    if latest_close > recent_high:
        return min(100, 70 + (latest_close - recent_high) / recent_high * 1000)
    return max(0, 50 - (recent_high - latest_close) / recent_high * 500)


def factor_oi_change(candles):
    ois = [c.get("oi", 0) for c in candles]
    if len(ois) < 5 or ois[-2] == 0:
        return 50.0
    change_pct = (ois[-1] - ois[-2]) / ois[-2] * 100
    return max(0, min(100, 50 + change_pct * 5))


FACTOR_FUNCTIONS = {
    "sma_crossover": factor_sma_crossover,
    "rsi": factor_rsi,
    "volume_spike": factor_volume_spike,
    "breakout": factor_breakout,
    "oi_change": factor_oi_change,
}


def score_symbol(candles, factor_weights):
    """Returns (total_score 0-100, breakdown dict) for one symbol given >=21 candles."""
    if not candles or len(candles) < 5:
        return 0.0, {}
    breakdown = {}
    total = 0.0
    weight_sum = sum(factor_weights.values()) or 1.0
    for factor, weight in factor_weights.items():
        fn = FACTOR_FUNCTIONS.get(factor)
        if not fn:
            continue
        raw = fn(candles)
        breakdown[factor] = round(raw, 1)
        total += raw * (weight / weight_sum)
    return round(total, 1), breakdown


def run_scan(upstox_client, universe_symbols, instrument_key_resolver, strategy_params):
    """
    universe_symbols: list of ticker strings to scan
    instrument_key_resolver: fn(symbol) -> upstox instrument_key
    strategy_params: dict, see config.DEFAULT_STRATEGY_PARAMS

    Returns list of dicts sorted by score desc:
      {symbol, score, breakdown, candles}
    """
    results = []
    timeframe = strategy_params.get("timeframe", "30minute")
    factor_weights = strategy_params.get("factors", {})

    for symbol in universe_symbols:
        instrument_key = instrument_key_resolver(symbol)
        if not instrument_key:
            continue
        try:
            candles = upstox_client.get_historical_candles(
                instrument_key, timeframe, from_date="2024-01-01", to_date="2024-01-02"
            )
        except Exception:
            continue
        score, breakdown = score_symbol(candles, factor_weights)
        results.append({
            "symbol": symbol,
            "instrument_key": instrument_key,
            "score": score,
            "breakdown": breakdown,
            "last_close": candles[-1]["close"] if candles else None,
            "candles": candles,
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results
