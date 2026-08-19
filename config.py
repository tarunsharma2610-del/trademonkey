"""
TradeBot AI - central configuration.
All secrets are read from environment variables. Never hardcode keys here.
"""
import os
from datetime import time

# ---------------------------------------------------------------------------
# API credentials (set these as environment variables on your server)
# ---------------------------------------------------------------------------
UPSTOX_API_KEY = os.environ.get("UPSTOX_API_KEY", "")
UPSTOX_API_SECRET = os.environ.get("UPSTOX_API_SECRET", "")
UPSTOX_REDIRECT_URI = os.environ.get("UPSTOX_REDIRECT_URI", "http://localhost:5000/upstox/callback")
UPSTOX_ACCESS_TOKEN = os.environ.get("UPSTOX_ACCESS_TOKEN", "")  # refreshed daily, see upstox_client.py

PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
PERPLEXITY_MODEL = os.environ.get("PERPLEXITY_MODEL", "sonar-pro")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "data", "tradebot.db")
SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"

# ---------------------------------------------------------------------------
# Market hours (IST) - the scheduler uses these to decide when to run jobs
# ---------------------------------------------------------------------------
PRE_MARKET_JOB_TIME = time(8, 30)     # pre-market research + scan
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
EOD_JOB_TIME = time(15, 40)           # end-of-day summary + newsletter draft
SCAN_INTERVAL_SECONDS = 60            # how often the live loop re-scans/checks positions during market hours

MCX_OPEN = time(9, 0)
MCX_CLOSE = time(23, 30)              # MCX runs later than equity; adjust for season (23:30 or 23:55)

# Which weekdays the market is open (0=Monday ... 6=Sunday)
TRADING_WEEKDAYS = {0, 1, 2, 3, 4}

# ---------------------------------------------------------------------------
# Paper trading balance presets
# User can pick one of these when creating a portfolio, or type a custom amount.
# ---------------------------------------------------------------------------
BALANCE_PRESETS = [10_000, 25_000, 50_000, 75_000, 100_000, 500_000]
MIN_CUSTOM_BALANCE = 1_000
MAX_CUSTOM_BALANCE = 10_00_00_000  # 10 crore sanity ceiling

# ---------------------------------------------------------------------------
# Segments this system trades
# ---------------------------------------------------------------------------
SEGMENTS = ["NSE", "BSE", "MCX"]

# ---------------------------------------------------------------------------
# Strategy engine defaults (used as the starting template for new strategies;
# every field is editable per-strategy from the UI)
# ---------------------------------------------------------------------------
DEFAULT_STRATEGY_PARAMS = {
    "name": "Balanced Swing",
    "segment": "NSE",
    "universe": "NIFTY500",          # NIFTY500 | MCX_COMMODITIES | WATCHLIST
    "timeframe": "30minute",         # candle interval used for signals
    "factors": {
        # each factor contributes a weighted score; weights must sum to ~1.0
        "sma_crossover": 0.25,
        "rsi": 0.20,
        "volume_spike": 0.20,
        "breakout": 0.20,
        "oi_change": 0.15,           # ignored for equity, used for F&O/commodities
    },
    "entry_score_threshold": 70,     # 0-100 score required to trigger an entry
    "max_positions": 8,              # max concurrent open trades in this portfolio
    "risk_per_trade_pct": 2.0,       # % of portfolio balance risked per trade
    "stop_loss_method": "atr",       # atr | percent | swing_low
    "stop_loss_atr_multiple": 1.5,
    "stop_loss_percent": 2.0,
    "target_method": "risk_reward",  # risk_reward | atr | percent
    "risk_reward_ratio": 2.0,        # target distance = R multiple of stop distance
    "trailing_stop": True,
    "trailing_stop_activation_pct": 1.0,   # start trailing once trade is +1% in profit
    "trailing_stop_trail_pct": 0.75,
    "square_off_time": "15:15",      # force-close intraday-only strategies before close
    "intraday_only": False,
}

# Risk management global guardrails (apply across all portfolios for the user)
GLOBAL_RISK_LIMITS = {
    "max_daily_loss_pct": 5.0,       # halt all new entries if today's combined loss exceeds this %
    "max_open_positions_total": 25,
    "max_capital_deployed_pct": 80.0,
}
