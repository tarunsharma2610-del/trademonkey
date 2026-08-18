"""
Database models. One user is assumed (single-user system per your spec),
but the schema leaves a user_id column in place in case you add multi-user later.
"""
import json
import uuid
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def _uid():
    return str(uuid.uuid4())[:8]


class Strategy(db.Model):
    __tablename__ = "strategies"

    id = db.Column(db.String(8), primary_key=True, default=_uid)
    name = db.Column(db.String(100), nullable=False)
    params_json = db.Column(db.Text, nullable=False)  # serialized dict, see config.DEFAULT_STRATEGY_PARAMS
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    portfolios = db.relationship("Portfolio", backref="strategy", lazy=True)

    @property
    def params(self):
        return json.loads(self.params_json)

    @params.setter
    def params(self, value):
        self.params_json = json.dumps(value)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "params": self.params,
            "active": self.active,
            "updated_at": self.updated_at.isoformat(),
        }


class Portfolio(db.Model):
    __tablename__ = "portfolios"

    id = db.Column(db.String(8), primary_key=True, default=_uid)
    name = db.Column(db.String(100), nullable=False)
    segment = db.Column(db.String(10), nullable=False, default="NSE")  # NSE | BSE | MCX
    strategy_id = db.Column(db.String(8), db.ForeignKey("strategies.id"), nullable=False)

    starting_balance = db.Column(db.Float, nullable=False)
    cash_balance = db.Column(db.Float, nullable=False)        # cash currently free (not in open positions)
    realized_pnl = db.Column(db.Float, default=0.0)

    is_active = db.Column(db.Boolean, default=True)           # bot trades this portfolio when active
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    trades = db.relationship("Trade", backref="portfolio", lazy=True)

    def deployed_capital(self):
        return sum(t.entry_price * t.quantity for t in self.trades if t.status == "OPEN")

    def unrealized_pnl(self, ltp_lookup):
        total = 0.0
        for t in self.trades:
            if t.status == "OPEN":
                ltp = ltp_lookup.get(t.symbol, t.entry_price)
                direction = 1 if t.side == "BUY" else -1
                total += (ltp - t.entry_price) * t.quantity * direction
        return total

    def equity(self, ltp_lookup):
        return self.cash_balance + self.deployed_capital() + self.unrealized_pnl(ltp_lookup)

    def to_dict(self, ltp_lookup=None):
        ltp_lookup = ltp_lookup or {}
        return {
            "id": self.id,
            "name": self.name,
            "segment": self.segment,
            "strategy": self.strategy.name if self.strategy else None,
            "strategy_id": self.strategy_id,
            "starting_balance": self.starting_balance,
            "cash_balance": self.cash_balance,
            "deployed_capital": self.deployed_capital(),
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl(ltp_lookup),
            "equity": self.equity(ltp_lookup),
            "is_active": self.is_active,
            "open_positions": len([t for t in self.trades if t.status == "OPEN"]),
        }


class Trade(db.Model):
    __tablename__ = "trades"

    id = db.Column(db.String(8), primary_key=True, default=_uid)
    portfolio_id = db.Column(db.String(8), db.ForeignKey("portfolios.id"), nullable=False)

    symbol = db.Column(db.String(30), nullable=False)
    instrument_key = db.Column(db.String(60))
    side = db.Column(db.String(4), nullable=False)          # BUY | SELL
    quantity = db.Column(db.Integer, nullable=False)

    entry_price = db.Column(db.Float, nullable=False)
    entry_time = db.Column(db.DateTime, default=datetime.utcnow)
    stop_loss = db.Column(db.Float, nullable=False)
    target = db.Column(db.Float, nullable=False)
    trailing_stop_price = db.Column(db.Float)                # updated live once trailing activates

    exit_price = db.Column(db.Float)
    exit_time = db.Column(db.DateTime)
    exit_reason = db.Column(db.String(20))                   # TARGET | STOPLOSS | TRAILING_SL | SQUARE_OFF | MANUAL

    status = db.Column(db.String(10), default="OPEN")        # OPEN | CLOSED
    pnl = db.Column(db.Float)
    score = db.Column(db.Float)                               # scanner score that triggered this entry
    strategy_snapshot_json = db.Column(db.Text)               # strategy params at time of entry, for audit

    def to_dict(self):
        return {
            "id": self.id,
            "portfolio_id": self.portfolio_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "stop_loss": self.stop_loss,
            "target": self.target,
            "trailing_stop_price": self.trailing_stop_price,
            "exit_price": self.exit_price,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "exit_reason": self.exit_reason,
            "status": self.status,
            "pnl": self.pnl,
            "score": self.score,
        }


class ScanResult(db.Model):
    """Snapshot of scanner output, kept for the audit log / research history."""
    __tablename__ = "scan_results"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    run_at = db.Column(db.DateTime, default=datetime.utcnow)
    strategy_id = db.Column(db.String(8))
    symbol = db.Column(db.String(30))
    score = db.Column(db.Float)
    factor_breakdown_json = db.Column(db.Text)
    action_taken = db.Column(db.String(20))  # ENTERED | SKIPPED_MAX_POSITIONS | SKIPPED_LOW_SCORE | SKIPPED_RISK_LIMIT


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ts = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(30))   # TRADE | STRATEGY | PORTFOLIO | SYSTEM | RISK
    message = db.Column(db.Text)

    def to_dict(self):
        return {"id": self.id, "ts": self.ts.isoformat(), "category": self.category, "message": self.message}


class DailyReport(db.Model):
    __tablename__ = "daily_reports"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    report_date = db.Column(db.Date, nullable=False)
    portfolio_id = db.Column(db.String(8), db.ForeignKey("portfolios.id"))
    trades_taken = db.Column(db.Integer, default=0)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)
    gross_pnl = db.Column(db.Float, default=0.0)
    summary_text = db.Column(db.Text)         # human-readable EOD summary shown in the popup / newsletter


class WatchlistItem(db.Model):
    __tablename__ = "watchlist_items"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    symbol = db.Column(db.String(30), nullable=False)
    segment = db.Column(db.String(10), default="NSE")
    note = db.Column(db.String(200))
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "symbol": self.symbol, "segment": self.segment,
                "note": self.note, "added_at": self.added_at.isoformat()}


class Alert(db.Model):
    __tablename__ = "alerts"

    id = db.Column(db.String(8), primary_key=True, default=_uid)
    symbol = db.Column(db.String(30), nullable=False)
    condition = db.Column(db.String(10), nullable=False)   # ABOVE | BELOW | SCORE_ABOVE
    threshold = db.Column(db.Float, nullable=False)
    active = db.Column(db.Boolean, default=True)
    triggered_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "symbol": self.symbol, "condition": self.condition,
            "threshold": self.threshold, "active": self.active,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
        }


class Setting(db.Model):
    """Persisted, user-editable settings that override config.py defaults
    (global risk limits, etc.) without needing a redeploy to change them."""
    __tablename__ = "settings"

    key = db.Column(db.String(50), primary_key=True)
    value_json = db.Column(db.Text, nullable=False)

    @property
    def value(self):
        return json.loads(self.value_json)

    @value.setter
    def value(self, v):
        self.value_json = json.dumps(v)


class NewsletterIssue(db.Model):
    __tablename__ = "newsletter_issues"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    issue_date = db.Column(db.Date, nullable=False)
    subject = db.Column(db.String(200))
    body_markdown = db.Column(db.Text)
    sent = db.Column(db.Boolean, default=False)
