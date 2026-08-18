"""
Trade executor: the only module allowed to mutate Portfolio.cash_balance and
create/close Trade rows. Keeping this centralized avoids the kind of bug where
a UI action (like a reset) accidentally corrupts trade history.
"""
import json
from datetime import datetime

from models import db, Trade, AuditLog
import strategy_engine


def _log(category, message):
    db.session.add(AuditLog(category=category, message=message))


def open_trade(portfolio, entry_plan, strategy_params):
    cost = entry_plan["entry_price"] * entry_plan["quantity"]
    if cost > portfolio.cash_balance:
        raise ValueError("Insufficient cash balance for this trade")

    trade = Trade(
        portfolio_id=portfolio.id,
        symbol=entry_plan["symbol"],
        instrument_key=entry_plan["instrument_key"],
        side=entry_plan["side"],
        quantity=entry_plan["quantity"],
        entry_price=entry_plan["entry_price"],
        stop_loss=entry_plan["stop_loss"],
        target=entry_plan["target"],
        score=entry_plan["score"],
        strategy_snapshot_json=json.dumps(strategy_params),
        status="OPEN",
        entry_time=datetime.utcnow(),
    )
    portfolio.cash_balance -= cost
    db.session.add(trade)
    _log("TRADE", f"[{portfolio.name}] Opened {trade.side} {trade.quantity} {trade.symbol} @ {trade.entry_price} "
                  f"(SL {trade.stop_loss}, Target {trade.target}, score {trade.score})")
    db.session.commit()
    return trade


def close_trade(trade, exit_price, exit_reason):
    portfolio = trade.portfolio
    direction = 1 if trade.side == "BUY" else -1
    pnl = (exit_price - trade.entry_price) * trade.quantity * direction

    trade.exit_price = exit_price
    trade.exit_time = datetime.utcnow()
    trade.exit_reason = exit_reason
    trade.status = "CLOSED"
    trade.pnl = round(pnl, 2)

    portfolio.cash_balance += trade.entry_price * trade.quantity + pnl
    portfolio.realized_pnl += trade.pnl

    _log("TRADE", f"[{portfolio.name}] Closed {trade.symbol} @ {exit_price} reason={exit_reason} "
                  f"P&L={trade.pnl:+.2f}")
    db.session.commit()
    return trade


def check_open_trades(portfolio, ltp_lookup):
    """Runs on every scan cycle: checks each open trade in this portfolio against
    the latest LTPs, closes any that hit target/SL/trailing-stop."""
    closed = []
    for trade in portfolio.trades:
        if trade.status != "OPEN":
            continue
        ltp = ltp_lookup.get(trade.symbol)
        if ltp is None:
            continue
        params = json.loads(trade.strategy_snapshot_json) if trade.strategy_snapshot_json else {}
        reason = strategy_engine.evaluate_exit(trade, ltp, params)
        db.session.add(trade)  # persist any trailing_stop_price update even if not closing
        if reason:
            closed.append(close_trade(trade, ltp, reason))
    db.session.commit()
    return closed


def square_off_all(portfolio, ltp_lookup, reason="SQUARE_OFF"):
    """Force-closes every open trade in a portfolio (used for intraday_only
    strategies at square_off_time, or a manual 'flatten all' action)."""
    closed = []
    for trade in portfolio.trades:
        if trade.status != "OPEN":
            continue
        ltp = ltp_lookup.get(trade.symbol, trade.entry_price)
        closed.append(close_trade(trade, ltp, reason))
    return closed
