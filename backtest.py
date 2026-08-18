"""
Backtesting: replays historical candles bar-by-bar for a chosen strategy +
universe + date range, using the exact same scoring/entry/exit logic as live
trading (scanner.py + strategy_engine.py) so results are representative of what
the live bot would have done.
"""
from datetime import datetime

import scanner
import strategy_engine


def run_backtest(upstox_client, symbols, instrument_key_resolver, strategy_params,
                  from_date, to_date, starting_balance=100000, min_window=25):
    """Returns a dict with trade log + summary stats. Walks each symbol's candle
    series independently with a single simulated position per symbol at a time
    (a simplification vs. true portfolio-level position limits, called out in
    the results so it's not mistaken for a live-identical simulation)."""
    cash = starting_balance
    trade_log = []
    equity_curve = []

    for symbol in symbols:
        instrument_key = instrument_key_resolver(symbol)
        if not instrument_key:
            continue
        candles = upstox_client.get_historical_candles(
            instrument_key, strategy_params.get("timeframe", "30minute"), from_date, to_date
        )
        if len(candles) < min_window:
            continue

        open_position = None
        for i in range(min_window, len(candles)):
            window = candles[: i + 1]
            score, breakdown = scanner.score_symbol(window, strategy_params.get("factors", {}))

            if open_position:
                ltp = window[-1]["close"]
                reason = strategy_engine.evaluate_exit(open_position, ltp, strategy_params)
                if reason:
                    direction = 1 if open_position.side == "BUY" else -1
                    pnl = (ltp - open_position.entry_price) * open_position.quantity * direction
                    cash += pnl
                    trade_log.append({
                        "symbol": symbol, "entry_price": open_position.entry_price,
                        "exit_price": ltp, "pnl": round(pnl, 2), "reason": reason,
                        "entry_index": open_position.entry_index, "exit_index": i,
                    })
                    open_position = None
            elif score >= strategy_params.get("entry_score_threshold", 70):
                entry_price = window[-1]["close"]
                stop_loss, stop_distance = strategy_engine.compute_stop_loss(entry_price, "BUY", window, strategy_params)
                target = strategy_engine.compute_target(entry_price, "BUY", stop_distance, window, strategy_params)
                qty = strategy_engine.position_size(cash, entry_price, stop_distance, strategy_params.get("risk_per_trade_pct", 2.0))
                if qty > 0:
                    open_position = _FakeTrade(symbol, "BUY", qty, entry_price, stop_loss, target, i)

            equity_curve.append(cash)

    wins = [t for t in trade_log if t["pnl"] > 0]
    losses = [t for t in trade_log if t["pnl"] <= 0]
    gross = sum(t["pnl"] for t in trade_log)

    return {
        "starting_balance": starting_balance,
        "ending_balance": round(starting_balance + gross, 2),
        "gross_pnl": round(gross, 2),
        "return_pct": round(gross / starting_balance * 100, 2) if starting_balance else 0,
        "trades": len(trade_log),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(trade_log) * 100, 1) if trade_log else 0,
        "trade_log": trade_log,
        "note": "Simplified: one simultaneous position per symbol, no cross-symbol "
                "capital contention modeled. Good for validating strategy logic, not "
                "a precise capital-constrained live replica.",
    }


class _FakeTrade:
    """Mirrors the subset of Trade's attributes strategy_engine.evaluate_exit needs,
    without touching the database during a backtest run."""
    def __init__(self, symbol, side, quantity, entry_price, stop_loss, target, entry_index):
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.target = target
        self.trailing_stop_price = None
        self.entry_index = entry_index
