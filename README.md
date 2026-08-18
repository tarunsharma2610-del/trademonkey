# TradeBot AI

Automated, 24/7 multi-portfolio paper trading system for NSE/BSE/MCX, built on
Flask + Upstox + Perplexity, matching the TradeBot AI dashboard design.

## What's built

- **Multi-portfolio, multi-strategy**: create any number of portfolios, each with its
  own paper balance (₹10k/25k/50k/75k/1L/5L presets, or custom), its own segment
  (NSE/BSE/MCX), and its own assigned strategy. Strategies can be created, cloned,
  and swapped onto a portfolio at any time from the UI.
- **Scanner**: 5-factor scoring engine (SMA crossover, RSI, volume spike, breakout,
  OI change) over the Nifty 500 universe or MCX commodities, fully weighted per strategy.
- **Auto entry/exit**: position sizing from risk %, automatic stop-loss (ATR /
  percent / swing-low) and target (risk:reward / ATR / percent), trailing stops,
  intraday square-off.
- **24/7 scheduler**: pre-market job (Perplexity research + scan), market-hours
  loop (checks exits, scans for entries, every strategy/portfolio independently),
  EOD job (daily report + newsletter + popup event).
- **Reports**: daily/weekly/monthly rollups per portfolio (win rate, avg win/loss,
  best/worst trade).
- **Newsletter**: Perplexity-generated daily wrap combining your live performance
  with fresh web research.
- **Audit log, trade journal**: every trade/strategy/portfolio action is logged.
- **Dashboard UI**: matches your TradeBot AI screenshots (dark theme, sidebar nav,
  portfolio cards, recent trades, EOD popup).

## Now fully built out (previously placeholders/stubs)

- **Instrument resolution** (`instrument_master.py`) — NSE/BSE equities resolve
  instantly and offline via ISIN → Upstox instrument_key (`NSE_EQ|{isin}`), using
  a real 501-stock Nifty 500 list with sector data bundled at `data/nifty500.json`
  (sourced from NSE's published index constituent data). MCX resolves via a
  cached instrument master that needs one live download once you're off demo mode
  (`instrument_master.refresh_mcx_master()`) since futures contracts roll monthly.
- **Live WebSocket feed** — `upstox_client.start_feed()` now uses the *official*
  `upstox-python-sdk` package's `MarketDataStreamerV3`, which handles the protobuf
  decoding for you. No hand-rolled `.proto` compilation needed.
- **Full Nifty 500 universe** — `scanner.NIFTY500` is the real 501-symbol list
  with sectors, used by the scanner, sector heatmap, and pre-market job.
- **Rate-limit-safe live loop** — the market-hours job no longer scans all 500
  stocks every minute. The pre-market job scans the full universe once and
  caches each strategy's top-40 shortlist; the live loop re-checks just that
  shortlist every cycle (plus watchlist/alert symbols).
- **Scanner, Sector Heatmap, Calendar, Watchlist, AI Assistant, Backtesting,
  Leaderboard, Risk Mgmt, Alerts, Settings, Tax Statement** — all fully wired
  to real logic (see `heatmap.py`, `backtest.py`, `calendar_data.py`,
  `alerts_engine.py`, `settings_store.py`) and real DB tables (`WatchlistItem`,
  `Alert`, `Setting`), not placeholders.
- **Ticker bar** — `/api/indices` pulls live (or demo) LTP for Sensex/Nifty/MCX
  Crude/Gold instead of hardcoded numbers.

## What still needs a manual step from you

1. **MCX instrument master refresh** — call `instrument_master.refresh_mcx_master()`
   once you're off demo mode (wire it into the pre-market job) to get real MCX
   contract instrument_keys. The URL in that function is Upstox's published
   instruments file - double check it against their current docs, since these
   paths shift occasionally.
2. **Upstox token** — since this system only ever *paper* trades, you don't need
   daily OAuth refresh at all. Your existing long-lived, read-only **Analytics
   Token** is enough — just set it as `UPSTOX_ACCESS_TOKEN`. `auth.py` documents
   the full OAuth flow for the day you want to add real order placement.
3. **Sector day-change accuracy** — `heatmap.py`'s day % change is a placeholder
   comparison in demo mode. In live mode, swap it for Upstox's OHLC quote
   endpoint's `close` (previous close) for accurate sector moves.
4. **Nifty 500 list freshness** — the bundled list should be refreshed
   periodically (NSE rebalances it), a quick re-run of the same download step
   used to build `data/nifty500.json`.

## Local development (demo mode, no API keys needed)

```bash
pip install -r requirements.txt --break-system-packages
export DEMO_MODE=true
python app.py
```

Visit http://localhost:5000 — a default "Conservative Swing" portfolio + "Balanced
Swing" strategy is seeded automatically on first run.

In demo mode, `app.py` does **not** start the scheduler (so the UI is easy to develop
against without background jobs firing). To exercise the scheduler locally:

```bash
python3 -c "
import app, scheduler
app.create_tables()
scheduler.init_scheduler(app.app)
app.app.run(port=5000)
"
```

## Production setup (Oracle Cloud Free Tier, matching your existing plan)

1. Provision your Always Free ARM Ampere instance in the Mumbai region (as you've
   already set up for AlgoEdge) and note its static public IP — this is the IP you
   register with Upstox/SEBI for order placement.
2. `git clone` this project, `pip install -r requirements.txt`.
3. Set real environment variables (don't commit these):
   ```bash
   export UPSTOX_API_KEY=...
   export UPSTOX_API_SECRET=...
   export UPSTOX_REDIRECT_URI=https://yourdomain/upstox/callback
   export UPSTOX_ACCESS_TOKEN=...   # refreshed daily
   export PERPLEXITY_API_KEY=...
   export DEMO_MODE=false
   ```
4. Run the Flask UI and the scheduler as **two separate systemd services** (the
   scheduler should keep running even if you restart the web process):
   ```
   # tradebot-web.service -> gunicorn app:app --bind 0.0.0.0:5000
   # tradebot-scheduler.service -> python3 -c "import app, scheduler; app.create_tables(); scheduler.init_scheduler(app.app); import time; [time.sleep(3600) for _ in iter(int,1)]"
   ```
   (Or simply run `python app.py` with `DEMO_MODE=false`, which starts both in one
   process — fine to start with, split later once you want independent restarts.)
5. Put nginx in front with a TLS cert if you want to access the dashboard remotely.

## Project layout

```
config.py            balance presets, market hours, strategy defaults, risk limits
models.py             Portfolio, Strategy, Trade, ScanResult, AuditLog, DailyReport, NewsletterIssue
upstox_client.py       REST + WebSocket wrapper, rate limiter, demo-mode fallback
perplexity_client.py   pre-market brief + newsletter copy generation
scanner.py             5-factor scoring engine
strategy_engine.py     entry/exit decisions, dynamic SL/target, position sizing
portfolio_manager.py   create/edit portfolios & strategies, balance presets
trade_executor.py      the only module that touches cash_balance / Trade rows
scheduler.py           pre-market / market-hours / EOD jobs, the 24/7 loop
reports.py             daily/weekly/monthly rollups
newsletter.py          daily newsletter generation
app.py                 Flask routes + JSON APIs
templates/             dashboard UI (dark theme matching your screenshots)
static/                CSS + JS (ticker, EOD popup polling)
```

## A design note on the balance reset

`portfolio_manager.reset_portfolio()` only resets `cash_balance` and `realized_pnl`
back to the starting amount — it deliberately does **not** touch the `trades` table,
so your trade journal/reports/audit history survive a reset. This avoids the
Nifty-500-scale trade-log-wiping issue you hit in AlgoEdge.
