"""
Portfolio manager: CRUD for portfolios (each with its own paper balance and
assigned strategy) and for strategies themselves (create/edit/clone).
Single user, multiple portfolios, multiple strategies - matches your spec.
"""
from models import db, Portfolio, Strategy, AuditLog
import config


def _log(category, message):
    db.session.add(AuditLog(category=category, message=message))


def validate_balance(amount):
    if amount < config.MIN_CUSTOM_BALANCE:
        raise ValueError(f"Balance must be at least ₹{config.MIN_CUSTOM_BALANCE:,}")
    if amount > config.MAX_CUSTOM_BALANCE:
        raise ValueError(f"Balance must be under ₹{config.MAX_CUSTOM_BALANCE:,}")
    return amount


def create_strategy(name, params=None):
    base = dict(config.DEFAULT_STRATEGY_PARAMS)
    if params:
        base.update(params)
    base["name"] = name
    strategy = Strategy(name=name)
    strategy.params = base
    db.session.add(strategy)
    _log("STRATEGY", f"Created strategy '{name}'")
    db.session.commit()
    return strategy


def update_strategy(strategy_id, params):
    strategy = Strategy.query.get(strategy_id)
    if not strategy:
        raise ValueError("Strategy not found")
    merged = strategy.params
    merged.update(params)
    strategy.params = merged
    if "name" in params:
        strategy.name = params["name"]
    _log("STRATEGY", f"Updated strategy '{strategy.name}' ({strategy_id})")
    db.session.commit()
    return strategy


def clone_strategy(strategy_id, new_name):
    src = Strategy.query.get(strategy_id)
    if not src:
        raise ValueError("Strategy not found")
    return create_strategy(new_name, params=src.params)


def create_portfolio(name, segment, strategy_id, balance):
    validate_balance(balance)
    strategy = Strategy.query.get(strategy_id)
    if not strategy:
        raise ValueError("Strategy not found")

    portfolio = Portfolio(
        name=name,
        segment=segment,
        strategy_id=strategy_id,
        starting_balance=balance,
        cash_balance=balance,
    )
    db.session.add(portfolio)
    _log("PORTFOLIO", f"Created portfolio '{name}' ({segment}) with ₹{balance:,} on strategy '{strategy.name}'")
    db.session.commit()
    return portfolio


def change_portfolio_strategy(portfolio_id, new_strategy_id):
    """Switch strategies on an existing portfolio. Open positions keep running under
    their original strategy_snapshot (saved on the Trade row); only future entries
    use the new strategy."""
    portfolio = Portfolio.query.get(portfolio_id)
    if not portfolio:
        raise ValueError("Portfolio not found")
    new_strategy = Strategy.query.get(new_strategy_id)
    if not new_strategy:
        raise ValueError("Strategy not found")

    old_name = portfolio.strategy.name if portfolio.strategy else "none"
    portfolio.strategy_id = new_strategy_id
    _log("PORTFOLIO", f"Portfolio '{portfolio.name}' switched strategy: {old_name} -> {new_strategy.name}")
    db.session.commit()
    return portfolio


def set_portfolio_active(portfolio_id, active: bool):
    portfolio = Portfolio.query.get(portfolio_id)
    if not portfolio:
        raise ValueError("Portfolio not found")
    portfolio.is_active = active
    _log("PORTFOLIO", f"Portfolio '{portfolio.name}' {'activated' if active else 'paused'}")
    db.session.commit()
    return portfolio


def reset_portfolio(portfolio_id, close_open_trades_only=False):
    """Resets a portfolio's cash back to starting_balance. IMPORTANT: unlike the
    AlgoEdge bug you hit before, this does NOT touch the trades table - closed
    trade history is preserved for the journal/reports. Only cash_balance and
    realized_pnl reset, and (optionally) open trades are force-closed at LTP
    rather than deleted."""
    portfolio = Portfolio.query.get(portfolio_id)
    if not portfolio:
        raise ValueError("Portfolio not found")

    portfolio.cash_balance = portfolio.starting_balance
    portfolio.realized_pnl = 0.0
    _log("PORTFOLIO", f"Portfolio '{portfolio.name}' cash reset to starting balance ₹{portfolio.starting_balance:,} "
                       f"(trade history preserved)")
    db.session.commit()
    return portfolio


def list_portfolios():
    return Portfolio.query.all()


def list_strategies():
    return Strategy.query.all()
