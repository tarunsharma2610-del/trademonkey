"""
Strategy engine: the decision layer between the scanner and the trade executor.

Responsibilities:
- Decide whether a scanned symbol qualifies for entry (score threshold, max positions, risk limits)
- Compute position size from risk_per_trade_pct
- Compute stop-loss and target automatically (ATR / percent / risk-reward based - fully configurable per strategy)
- Evaluate open positions on every tick/candle for target hit, stop-loss hit, or trailing-stop update
"""
from statistics import mean


def atr(candles, period=14):
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(-period, 0):
        h, l, prev_close = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)
    return mean(trs)


def compute_stop_loss(entry_price, side, candles, params):
    method = params.get("stop_loss_method", "percent")
    direction = 1 if side == "BUY" else -1

    if method == "atr":
        a = atr(candles) or entry_price * 0.01
        distance = a * params.get("stop_loss_atr_multiple", 1.5)
    elif method == "swing_low":
        lows = [c["low"] for c in candles[-10:]]
        swing = min(lows) if side == "BUY" else max(c["high"] for c in candles[-10:])
        distance = abs(entry_price - swing)
    else:  # percent
        distance = entry_price * (params.get("stop_loss_percent", 2.0) / 100)

    return round(entry_price - direction * distance, 2), round(distance, 2)


def compute_target(entry_price, side, stop_distance, candles, params):
    method = params.get("target_method", "risk_reward")
    direction = 1 if side == "BUY" else -1

    if method == "atr":
        a = atr(candles) or entry_price * 0.01
        distance = a * params.get("risk_reward_ratio", 2.0)
    elif method == "percent":
        distance = entry_price * (params.get("target_percent", 4.0) / 100)
    else:  # risk_reward - target distance is an R-multiple of the stop distance
        distance = stop_distance * params.get("risk_reward_ratio", 2.0)

    return round(entry_price + direction * distance, 2)


def position_size(portfolio_cash_balance, entry_price, stop_distance, risk_per_trade_pct):
    """Risk-based position sizing: risk_amount / per-share risk = quantity."""
    if stop_distance <= 0:
        return 0
    risk_amount = portfolio_cash_balance * (risk_per_trade_pct / 100)
    qty = int(risk_amount / stop_distance)
    # never let a single position eat more cash than is available
    max_affordable = int(portfolio_cash_balance / entry_price) if entry_price else 0
    return max(0, min(qty, max_affordable))


def evaluate_entry(scan_result, portfolio, strategy_params, open_position_count, global_risk_ok):
    """Returns an entry plan dict, or None if this symbol should be skipped."""
    if scan_result["score"] < strategy_params.get("entry_score_threshold", 70):
        return None, "SKIPPED_LOW_SCORE"
    if open_position_count >= strategy_params.get("max_positions", 8):
        return None, "SKIPPED_MAX_POSITIONS"
    if not global_risk_ok:
        return None, "SKIPPED_RISK_LIMIT"

    entry_price = scan_result["last_close"]
    side = "BUY"  # long-only for equity swing by default; short logic can be added for F&O/intraday strategies
    stop_loss, stop_distance = compute_stop_loss(entry_price, side, scan_result["candles"], strategy_params)
    target = compute_target(entry_price, side, stop_distance, scan_result["candles"], strategy_params)
    qty = position_size(portfolio.cash_balance, entry_price, stop_distance, strategy_params.get("risk_per_trade_pct", 2.0))

    if qty <= 0:
        return None, "SKIPPED_INSUFFICIENT_CAPITAL"

    return {
        "symbol": scan_result["symbol"],
        "instrument_key": scan_result["instrument_key"],
        "side": side,
        "quantity": qty,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "target": target,
        "score": scan_result["score"],
    }, "ENTERED"


def evaluate_exit(trade, ltp, strategy_params):
    """Checks one open trade against its target/SL/trailing-stop given the latest price.
    Returns exit_reason string, or None if the trade should stay open. Mutates
    trade.trailing_stop_price in place when trailing should be updated (caller persists it)."""
    direction = 1 if trade.side == "BUY" else -1
    profit_pct = (ltp - trade.entry_price) / trade.entry_price * 100 * direction

    # Target hit
    if (trade.side == "BUY" and ltp >= trade.target) or (trade.side == "SELL" and ltp <= trade.target):
        return "TARGET"

    # Trailing stop management
    if strategy_params.get("trailing_stop"):
        activation = strategy_params.get("trailing_stop_activation_pct", 1.0)
        trail_pct = strategy_params.get("trailing_stop_trail_pct", 0.75)
        if profit_pct >= activation:
            new_trail = ltp * (1 - trail_pct / 100 * direction)
            if trade.trailing_stop_price is None:
                trade.trailing_stop_price = new_trail
            else:
                # only ever tighten the trailing stop in the trade's favor
                if trade.side == "BUY":
                    trade.trailing_stop_price = max(trade.trailing_stop_price, new_trail)
                else:
                    trade.trailing_stop_price = min(trade.trailing_stop_price, new_trail)

    # Trailing stop hit
    if trade.trailing_stop_price is not None:
        if (trade.side == "BUY" and ltp <= trade.trailing_stop_price) or \
           (trade.side == "SELL" and ltp >= trade.trailing_stop_price):
            return "TRAILING_SL"

    # Hard stop-loss hit
    if (trade.side == "BUY" and ltp <= trade.stop_loss) or (trade.side == "SELL" and ltp >= trade.stop_loss):
        return "STOPLOSS"

    return None
