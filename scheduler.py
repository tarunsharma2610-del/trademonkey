"""
The 24/7 brain. Three jobs:

1. pre_market_job   - runs once before market open: Perplexity research brief + a
                       full scan of the universe, cached for reference (no trades yet).
2. market_hours_job - runs every SCAN_INTERVAL_SECONDS while the market is open:
                       checks open positions for exits, then scans for new entries
                       on every ACTIVE portfolio, respecting each one's own strategy.
3. eod_job          - runs once after close: force-closes intraday-only trades,
                       computes the daily report, generates the newsletter draft,
                       and raises an EOD event the frontend polls for (the "popup").

Run this with: python scheduler.py  (as a long-lived process/systemd service on
your Oracle Cloud box - this is what needs the static IP, not the Flask UI process).
"""
import json
from datetime import datetime, date, time as dtime

from apscheduler.schedulers.background import BackgroundScheduler

import config
import settings_store
from models import db, Portfolio, ScanResult, DailyReport, AuditLog, WatchlistItem
from upstox_client import UpstoxClient
from perplexity_client import PerplexityClient
from instrument_master import instrument_master
import scanner
import strategy_engine
import trade_executor
import alerts_engine

_upstox = UpstoxClient()
_perplexity = PerplexityClient()

# In-memory event the frontend polls via /api/events (cleared once fetched)
_pending_events = []


def push_event(kind, payload):
    _pending_events.append({"kind": kind, "payload": payload, "ts": datetime.utcnow().isoformat()})


def pop_events():
    global _pending_events
    events, _pending_events = _pending_events, []
    return events


def _instrument_key_resolver(symbol, segment="NSE"):
    """NSE/BSE equities resolve directly via ISIN (see instrument_master.py).
    MCX resolves via the cached instrument master (refreshed daily, since
    contracts roll monthly) - returns None until that cache has been populated,
    in which case the scanner will simply skip that symbol."""
    return instrument_master.resolve(symbol, segment)


def _universe_for(strategy_params):
    universe = strategy_params.get("universe", "NIFTY500")
    if universe == "MCX_COMMODITIES":
        return scanner.MCX_COMMODITIES
    if universe == "WATCHLIST":
        return [w.symbol for w in WatchlistItem.query.all()]
    return scanner.NIFTY500  # full 501-stock universe for the pre-market scan


def _premarket_shortlist(strategy_id, top_n=40):
    """During market hours we re-scan only the strategy's pre-market shortlist
    (not the full 500 stocks every minute) - this is what keeps the live loop
    within Upstox's rate limits. Falls back to the full universe if no
    pre-market scan has run yet today (e.g. first run, or mid-day restart)."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (ScanResult.query
            .filter(ScanResult.strategy_id == strategy_id,
                    ScanResult.action_taken == "PRE_MARKET_WATCH",
                    ScanResult.run_at >= today_start)
            .order_by(ScanResult.score.desc())
            .limit(top_n)
            .all())
    return [r.symbol for r in rows] if rows else None


def is_market_open(now=None):
    now = now or datetime.now()
    if now.weekday() not in config.TRADING_WEEKDAYS:
        return False
    t = now.time()
    return config.MARKET_OPEN <= t <= config.MARKET_CLOSE


def pre_market_job():
    with _app_context():
        brief = _perplexity.pre_market_brief()
        db.session.add(AuditLog(category="SYSTEM", message="Pre-market research brief generated"))
        db.session.commit()

        for portfolio in Portfolio.query.filter_by(is_active=True).all():
            params = portfolio.strategy.params
            universe = _universe_for(params)
            resolver = lambda s, _seg=portfolio.segment: _instrument_key_resolver(s, _seg)
            results = scanner.run_scan(_upstox, universe, resolver, params)
            for r in results[:20]:
                db.session.add(ScanResult(
                    strategy_id=portfolio.strategy_id, symbol=r["symbol"], score=r["score"],
                    factor_breakdown_json=json.dumps(r["breakdown"]), action_taken="PRE_MARKET_WATCH",
                ))
            db.session.commit()

        push_event("PRE_MARKET_BRIEF", {"brief": brief})


def _global_risk_ok():
    portfolios = Portfolio.query.all()
    if not portfolios:
        return True
    limits = settings_store.get_risk_limits()
    total_start = sum(p.starting_balance for p in portfolios)
    total_realized = sum(p.realized_pnl for p in portfolios)
    if total_start == 0:
        return True
    loss_pct = -(total_realized / total_start) * 100
    open_positions = sum(1 for p in portfolios for t in p.trades if t.status == "OPEN")
    if loss_pct >= limits["max_daily_loss_pct"]:
        return False
    if open_positions >= limits["max_open_positions_total"]:
        return False
    return True


def market_hours_job():
    with _app_context():
        if not is_market_open():
            return

        risk_ok = _global_risk_ok()
        active_portfolios = Portfolio.query.filter_by(is_active=True).all()

        # Build the LTP lookup from each portfolio's pre-market shortlist (not the
        # full 500-stock universe) - this is what keeps live polling within
        # Upstox's rate limits during the 60-second market_hours_job cycle.
        # Watchlist symbols and any symbol with an active alert are always
        # included too, regardless of whether a strategy scan currently tracks them.
        all_symbols = set()
        symbol_segment = {}
        for p in active_portfolios:
            universe = _premarket_shortlist(p.strategy_id) or _universe_for(p.strategy.params)
            for s in universe:
                all_symbols.add(s)
                symbol_segment[s] = p.segment

        for w in WatchlistItem.query.all():
            all_symbols.add(w.symbol)
            symbol_segment.setdefault(w.symbol, w.segment)

        from models import Alert
        for a in Alert.query.filter_by(active=True).all():
            all_symbols.add(a.symbol)
            symbol_segment.setdefault(a.symbol, "NSE")

        keys = [_instrument_key_resolver(s, symbol_segment[s]) for s in all_symbols]
        keys = [k for k in keys if k]
        ltp_lookup = _upstox.get_ltp(keys) if keys else {}
        ltp_by_symbol = {s: ltp_lookup.get(_instrument_key_resolver(s, symbol_segment[s])) for s in all_symbols}

        for portfolio in active_portfolios:
            closed = trade_executor.check_open_trades(portfolio, ltp_by_symbol)
            for c in closed:
                push_event("TRADE_CLOSED", {"portfolio": portfolio.name, "symbol": c.symbol, "pnl": c.pnl,
                                             "reason": c.exit_reason})

            params = portfolio.strategy.params
            universe = _premarket_shortlist(portfolio.strategy_id) or _universe_for(params)
            resolver = lambda s: _instrument_key_resolver(s, portfolio.segment)
            results = scanner.run_scan(_upstox, universe, resolver, params)
            open_count = len([t for t in portfolio.trades if t.status == "OPEN"])
            scores_by_symbol = {r["symbol"]: r["score"] for r in results}

            for r in results:
                plan, action = strategy_engine.evaluate_entry(r, portfolio, params, open_count, risk_ok)
                db.session.add(ScanResult(
                    strategy_id=portfolio.strategy_id, symbol=r["symbol"], score=r["score"],
                    factor_breakdown_json=json.dumps(r["breakdown"]), action_taken=action,
                ))
                if plan:
                    trade = trade_executor.open_trade(portfolio, plan, params)
                    open_count += 1
                    push_event("TRADE_OPENED", {"portfolio": portfolio.name, "symbol": trade.symbol,
                                                 "entry": trade.entry_price, "sl": trade.stop_loss,
                                                 "target": trade.target})
            db.session.commit()

            # Square off intraday-only strategies before close
            if params.get("intraday_only"):
                sq_time = dtime.fromisoformat(params.get("square_off_time", "15:15"))
                if datetime.now().time() >= sq_time:
                    trade_executor.square_off_all(portfolio, ltp_by_symbol, reason="SQUARE_OFF")

            alerts_engine.check_alerts(ltp_by_symbol, scores_by_symbol, push_event)


def eod_job():
    with _app_context():
        today = date.today()
        for portfolio in Portfolio.query.all():
            todays_trades = [t for t in portfolio.trades if t.exit_time and t.exit_time.date() == today]
            wins = len([t for t in todays_trades if (t.pnl or 0) > 0])
            losses = len([t for t in todays_trades if (t.pnl or 0) <= 0])
            gross = sum(t.pnl or 0 for t in todays_trades)
            summary = (
                f"{portfolio.name}: {len(todays_trades)} trades closed today, "
                f"{wins} wins / {losses} losses, net P&L ₹{gross:+.2f}"
            )
            db.session.add(DailyReport(
                report_date=today, portfolio_id=portfolio.id, trades_taken=len(todays_trades),
                wins=wins, losses=losses, gross_pnl=gross, summary_text=summary,
            ))
        db.session.commit()

        summaries = [r.summary_text for r in DailyReport.query.filter_by(report_date=today).all()]
        push_event("EOD_SUMMARY", {"date": today.isoformat(), "summaries": summaries})


_flask_app = None  # set by app.py via init_scheduler()


def _app_context():
    return _flask_app.app_context()


def init_scheduler(flask_app):
    global _flask_app
    _flask_app = flask_app

    sched = BackgroundScheduler(timezone="Asia/Kolkata")
    sched.add_job(pre_market_job, "cron",
                  hour=config.PRE_MARKET_JOB_TIME.hour, minute=config.PRE_MARKET_JOB_TIME.minute,
                  day_of_week="mon-fri")
    sched.add_job(market_hours_job, "interval", seconds=config.SCAN_INTERVAL_SECONDS)
    sched.add_job(eod_job, "cron",
                  hour=config.EOD_JOB_TIME.hour, minute=config.EOD_JOB_TIME.minute,
                  day_of_week="mon-fri")
    sched.start()
    return sched
