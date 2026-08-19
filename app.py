import json
import logging
import time as time_mod
from datetime import date, datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for

import config
import settings_store
from models import db, Portfolio, Strategy, Trade, AuditLog, NewsletterIssue, WatchlistItem, Alert
import portfolio_manager
import reports
import newsletter as newsletter_mod
import scheduler as sched_mod
from upstox_client import UpstoxClient
from instrument_master import instrument_master
import scanner
import heatmap
import backtest
import calendar_data
from perplexity_client import PerplexityClient

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = config.SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

logger = logging.getLogger("tradebot.app")

_upstox = UpstoxClient()
_perplexity = PerplexityClient()
_econ_events_cache = {"text": None, "ts": 0}


def _market_data_or_empty(keys):
    """Fetch live LTPs, but fail closed: if Upstox credentials are missing or the
    feed errors, return {} (no fake prices ever reach the UI)."""
    if not keys:
        return {}
    try:
        return _upstox.get_ltp(keys)
    except Exception as e:
        logger.warning("Live market data unavailable: %s", e)
        return {}


def _ltp_lookup_for_all():
    symbols = set()
    for p in Portfolio.query.all():
        for t in p.trades:
            if t.status == "OPEN":
                symbols.add(t.symbol)
    if not symbols:
        return {}
    keys = [f"NSE_EQ|{s}" for s in symbols]
    raw = _market_data_or_empty(keys)
    return {s: raw.get(f"NSE_EQ|{s}") for s in symbols}


@app.route("/")
def dashboard():
    ltp_lookup = _ltp_lookup_for_all()
    portfolios = [p.to_dict(ltp_lookup) for p in Portfolio.query.all()]
    recent_trades = Trade.query.order_by(Trade.entry_time.desc()).limit(10).all()
    total_equity = sum(p["equity"] for p in portfolios)
    return render_template(
        "dashboard.html",
        portfolios=portfolios,
        recent_trades=recent_trades,
        total_equity=total_equity,
        active_page="dashboard",
    )


@app.route("/portfolios", methods=["GET", "POST"])
def portfolios_page():
    if request.method == "POST":
        try:
            balance = float(request.form["balance"])
            portfolio_manager.create_portfolio(
                name=request.form["name"],
                segment=request.form["segment"],
                strategy_id=request.form["strategy_id"],
                balance=balance,
            )
        except Exception as e:
            return render_template("portfolios.html", error=str(e),
                                    portfolios=Portfolio.query.all(), strategies=Strategy.query.all(),
                                    balance_presets=config.BALANCE_PRESETS, active_page="portfolios")
        return redirect(url_for("portfolios_page"))

    return render_template(
        "portfolios.html",
        portfolios=Portfolio.query.all(),
        strategies=Strategy.query.all(),
        balance_presets=config.BALANCE_PRESETS,
        active_page="portfolios",
    )


@app.route("/portfolios/<portfolio_id>/strategy", methods=["POST"])
def change_strategy(portfolio_id):
    portfolio_manager.change_portfolio_strategy(portfolio_id, request.form["strategy_id"])
    return redirect(url_for("portfolios_page"))


@app.route("/portfolios/<portfolio_id>/toggle", methods=["POST"])
def toggle_portfolio(portfolio_id):
    p = Portfolio.query.get_or_404(portfolio_id)
    portfolio_manager.set_portfolio_active(portfolio_id, not p.is_active)
    return redirect(url_for("portfolios_page"))


@app.route("/portfolios/<portfolio_id>/reset", methods=["POST"])
def reset_portfolio_route(portfolio_id):
    portfolio_manager.reset_portfolio(portfolio_id)
    return redirect(url_for("portfolios_page"))


@app.route("/strategies", methods=["GET", "POST"])
def strategies_page():
    if request.method == "POST":
        params = dict(config.DEFAULT_STRATEGY_PARAMS)
        params["universe"] = request.form.get("universe", "NIFTY500")
        params["entry_score_threshold"] = float(request.form.get("entry_score_threshold", 70))
        params["max_positions"] = int(request.form.get("max_positions", 8))
        params["risk_per_trade_pct"] = float(request.form.get("risk_per_trade_pct", 2.0))
        params["risk_reward_ratio"] = float(request.form.get("risk_reward_ratio", 2.0))
        params["intraday_only"] = request.form.get("intraday_only") == "on"
        portfolio_manager.create_strategy(request.form["name"], params)
        return redirect(url_for("strategies_page"))

    return render_template("strategies.html", strategies=Strategy.query.all(), active_page="strategies")


@app.route("/trades")
def trades_page():
    all_trades = Trade.query.order_by(Trade.entry_time.desc()).limit(200).all()
    return render_template("trades.html", trades=all_trades, active_page="trades")


@app.route("/reports")
def reports_page():
    period = request.args.get("period", "daily")
    data = reports.combined_report(period)
    return render_template("reports.html", data=data, period=period, active_page="reports")


@app.route("/newsletter")
def newsletter_page():
    issues = NewsletterIssue.query.order_by(NewsletterIssue.issue_date.desc()).limit(20).all()
    return render_template("newsletter.html", issues=issues, active_page="newsletter")


@app.route("/newsletter/generate", methods=["POST"])
def generate_newsletter_route():
    newsletter_mod.generate_daily_newsletter()
    return redirect(url_for("newsletter_page"))


@app.route("/audit-log")
def audit_log_page():
    logs = AuditLog.query.order_by(AuditLog.ts.desc()).limit(300).all()
    return render_template("audit_log.html", logs=logs, active_page="audit")


@app.route("/scanner", methods=["GET", "POST"])
def scanner_page():
    strategies = Strategy.query.all()
    results = None
    selected_strategy_id = request.values.get("strategy_id") or (strategies[0].id if strategies else None)

    if selected_strategy_id:
        strategy = Strategy.query.get(selected_strategy_id)
        if strategy:
            params = strategy.params
            universe = scanner.MCX_COMMODITIES if params.get("universe") == "MCX_COMMODITIES" else scanner.NIFTY500
            segment = "MCX" if params.get("universe") == "MCX_COMMODITIES" else "NSE"
            # Cap the on-demand scan so clicking the page doesn't take forever
            # over the full 501-stock list in one request.
            sample = universe[:60]
            resolver = lambda s: instrument_master.resolve(s, segment)
            results = scanner.run_scan(_upstox, sample, resolver, params)[:25]

    return render_template("scanner.html", strategies=strategies, selected_strategy_id=selected_strategy_id,
                           results=results, active_page="scanner")


@app.route("/sector-heatmap")
def heatmap_page():
    data = heatmap.compute_heatmap(_upstox)
    return render_template("heatmap.html", data=data, active_page="heatmap")


@app.route("/calendar")
def calendar_page():
    today = date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))
    pnl_days = calendar_data.daily_pnl_calendar(year, month)

    # Cache the Perplexity call for an hour so navigating the calendar doesn't
    # re-trigger a web-search-backed API call every page load.
    if time_mod.time() - _econ_events_cache["ts"] > 3600:
        _econ_events_cache["text"] = calendar_data.economic_events_this_week()
        _econ_events_cache["ts"] = time_mod.time()

    return render_template("calendar.html", year=year, month=month, pnl_days=pnl_days,
                            econ_events=_econ_events_cache["text"], active_page="calendar")


@app.route("/watchlist", methods=["GET", "POST"])
def watchlist_page():
    if request.method == "POST":
        db.session.add(WatchlistItem(
            symbol=request.form["symbol"].upper().strip(),
            segment=request.form.get("segment", "NSE"),
            note=request.form.get("note", ""),
        ))
        db.session.commit()
        return redirect(url_for("watchlist_page"))

    items = WatchlistItem.query.order_by(WatchlistItem.added_at.desc()).all()
    keys = [instrument_master.resolve(i.symbol, i.segment) for i in items]
    ltp_lookup = _market_data_or_empty([k for k in keys if k])
    ltp_by_item = {i.id: ltp_lookup.get(instrument_master.resolve(i.symbol, i.segment)) for i in items}
    return render_template("watchlist.html", items=items, ltp_by_item=ltp_by_item, active_page="watchlist")


@app.route("/watchlist/<int:item_id>/delete", methods=["POST"])
def watchlist_delete(item_id):
    item = WatchlistItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for("watchlist_page"))


@app.route("/ai-assistant", methods=["GET", "POST"])
def ai_assistant_page():
    answer = None
    question = None
    if request.method == "POST":
        question = request.form["question"]
        system = ("You are a helpful assistant for a self-directed Indian equity/commodity "
                   "trader using their own paper-trading bot. Use current web search when useful. "
                   "Be concise. Add a brief disclaimer this is educational, not investment advice, "
                   "only if the question asks for a recommendation.")
        answer = _perplexity._chat(system, question, max_tokens=600)
    return render_template("ai_assistant.html", question=question, answer=answer, active_page="ai")


@app.route("/backtesting", methods=["GET", "POST"])
def backtesting_page():
    strategies = Strategy.query.all()
    result = None
    form = {"strategy_id": "", "from_date": "", "to_date": "", "starting_balance": 100000}

    if request.method == "POST":
        form.update(request.form)
        strategy = Strategy.query.get(request.form["strategy_id"])
        params = strategy.params
        universe = scanner.MCX_COMMODITIES if params.get("universe") == "MCX_COMMODITIES" else scanner.NIFTY500
        segment = "MCX" if params.get("universe") == "MCX_COMMODITIES" else "NSE"
        sample = universe[:30]  # keep on-demand backtests fast; widen for deeper runs
        resolver = lambda s: instrument_master.resolve(s, segment)
        result = backtest.run_backtest(
            _upstox, sample, resolver, params,
            from_date=request.form["from_date"], to_date=request.form["to_date"],
            starting_balance=float(request.form.get("starting_balance", 100000)),
        )

    return render_template("backtesting.html", strategies=strategies, result=result, form=form, active_page="backtesting")


@app.route("/leaderboard")
def leaderboard_page():
    period = request.args.get("period", "monthly")
    rows = []
    for p in Portfolio.query.all():
        r = reports.report_for_period(p.id, period)
        return_pct = round((p.cash_balance + p.deployed_capital() - p.starting_balance) / p.starting_balance * 100, 2) \
            if p.starting_balance else 0
        rows.append({"name": p.name, "strategy": p.strategy.name if p.strategy else "—",
                     "trades": r["trades"], "win_rate_pct": r["win_rate_pct"],
                     "gross_pnl": r["gross_pnl"], "return_pct": return_pct})
    rows.sort(key=lambda r: r["return_pct"], reverse=True)
    return render_template("leaderboard.html", rows=rows, period=period, active_page="leaderboard")


@app.route("/trade-journal")
def trade_journal_page():
    return redirect(url_for("trades_page"))


@app.route("/tax-statement")
def tax_statement_page():
    """Simple capital-gains style summary grouped by Indian financial year
    (Apr-Mar) from closed paper trades. Educational only - not tax advice."""
    closed = Trade.query.filter_by(status="CLOSED").order_by(Trade.exit_time).all()
    by_fy = {}
    for t in closed:
        if not t.exit_time:
            continue
        fy_start_year = t.exit_time.year if t.exit_time.month >= 4 else t.exit_time.year - 1
        fy_label = f"FY {fy_start_year}-{str(fy_start_year+1)[-2:]}"
        bucket = by_fy.setdefault(fy_label, {"trades": 0, "gross_pnl": 0.0})
        bucket["trades"] += 1
        bucket["gross_pnl"] += t.pnl or 0

    for v in by_fy.values():
        v["gross_pnl"] = round(v["gross_pnl"], 2)

    return render_template("tax_statement.html", by_fy=by_fy, active_page="tax")


@app.route("/risk-mgmt", methods=["GET", "POST"])
def risk_mgmt_page():
    if request.method == "POST":
        settings_store.set_risk_limits({
            "max_daily_loss_pct": float(request.form["max_daily_loss_pct"]),
            "max_open_positions_total": int(request.form["max_open_positions_total"]),
            "max_capital_deployed_pct": float(request.form["max_capital_deployed_pct"]),
        })
        return redirect(url_for("risk_mgmt_page"))

    limits = settings_store.get_risk_limits()
    return render_template("risk_mgmt.html", limits=limits, active_page="risk")


@app.route("/alerts", methods=["GET", "POST"])
def alerts_page():
    if request.method == "POST":
        db.session.add(Alert(
            symbol=request.form["symbol"].upper().strip(),
            condition=request.form["condition"],
            threshold=float(request.form["threshold"]),
        ))
        db.session.commit()
        return redirect(url_for("alerts_page"))

    all_alerts = Alert.query.order_by(Alert.created_at.desc()).all()
    return render_template("alerts.html", alerts=all_alerts, active_page="alerts")


@app.route("/alerts/<alert_id>/delete", methods=["POST"])
def alert_delete(alert_id):
    a = Alert.query.get_or_404(alert_id)
    db.session.delete(a)
    db.session.commit()
    return redirect(url_for("alerts_page"))


@app.route("/settings")
def settings_page():
    status = settings_store.get_api_key_status()
    return render_template("settings.html", status=status, balance_presets=config.BALANCE_PRESETS,
                            active_page="settings")


# ---------------------------------------------------------------------------
# JSON APIs (used by dashboard.js for live polling / the EOD popup)
# ---------------------------------------------------------------------------
@app.route("/api/events")
def api_events():
    return jsonify(sched_mod.pop_events())


@app.route("/api/portfolios")
def api_portfolios():
    ltp_lookup = _ltp_lookup_for_all()
    return jsonify([p.to_dict(ltp_lookup) for p in Portfolio.query.all()])


INDEX_KEYS = {
    "sensex": "BSE_INDEX|SENSEX",
    "nifty": "NSE_INDEX|Nifty 50",
    "crude": "MCX_INDEX|CRUDEOIL",
    "gold": "MCX_INDEX|GOLD",
}


@app.route("/api/indices")
def api_indices():
    ltp = _market_data_or_empty(list(INDEX_KEYS.values()))
    return jsonify({name: ltp.get(key) for name, key in INDEX_KEYS.items()})


def create_tables():
    with app.app_context():
        db.create_all()
        # seed one default strategy + portfolio on first run so the dashboard isn't empty
        if not Strategy.query.first():
            s = portfolio_manager.create_strategy("Balanced Swing")
            portfolio_manager.create_portfolio("Conservative Swing", "NSE", s.id, 100000)


if __name__ == "__main__":
    create_tables()
    sched_mod.init_scheduler(app)
    app.run(host="0.0.0.0", port=5000, debug=False)
