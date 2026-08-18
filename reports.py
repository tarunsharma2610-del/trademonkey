"""
Report aggregation for the Reports tab: daily/weekly/monthly rollups per
portfolio and combined, built from closed Trade rows (source of truth) rather
than the DailyReport cache, so historical reports stay accurate even if you
change strategies later.
"""
from datetime import date, timedelta
from models import Trade, Portfolio


def _closed_trades_between(portfolio_id, start, end):
    trades = Trade.query.filter(
        Trade.portfolio_id == portfolio_id,
        Trade.status == "CLOSED",
        Trade.exit_time >= start,
        Trade.exit_time <= end,
    ).all()
    return trades


def _summarize(trades):
    wins = [t for t in trades if (t.pnl or 0) > 0]
    losses = [t for t in trades if (t.pnl or 0) <= 0]
    gross = sum(t.pnl or 0 for t in trades)
    win_rate = (len(wins) / len(trades) * 100) if trades else 0
    avg_win = (sum(t.pnl for t in wins) / len(wins)) if wins else 0
    avg_loss = (sum(t.pnl for t in losses) / len(losses)) if losses else 0
    best = max(trades, key=lambda t: t.pnl or 0) if trades else None
    worst = min(trades, key=lambda t: t.pnl or 0) if trades else None
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(win_rate, 1),
        "gross_pnl": round(gross, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "best_trade": {"symbol": best.symbol, "pnl": best.pnl} if best else None,
        "worst_trade": {"symbol": worst.symbol, "pnl": worst.pnl} if worst else None,
    }


def report_for_period(portfolio_id, period="daily"):
    today = date.today()
    if period == "daily":
        start = today
    elif period == "weekly":
        start = today - timedelta(days=today.weekday())
    elif period == "monthly":
        start = today.replace(day=1)
    else:
        raise ValueError("period must be daily/weekly/monthly")

    trades = _closed_trades_between(portfolio_id, start, today + timedelta(days=1))
    summary = _summarize(trades)
    summary["period"] = period
    summary["start_date"] = start.isoformat()
    summary["end_date"] = today.isoformat()
    return summary


def combined_report(period="daily"):
    portfolios = Portfolio.query.all()
    return {p.id: {"name": p.name, **report_for_period(p.id, period)} for p in portfolios}
