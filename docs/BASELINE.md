# TradeBot AI — Repository Baseline (Phase 1)

Date: 2026-08-19
Branch: main

This document is the Phase 1 repository baseline per `instruction.md` §121
(PHASE 1 — REPOSITORY BASELINE). It records the dependency map, known issues,
and the state of the repository before subsequent phases begin. It also serves
as the running handover doc: each phase updates this file with what was done
and what remains.

## 1. Dependency map

```
app.py  (Flask routes + JSON APIs)
   -> config.py, settings_store.py, models.py
   -> portfolio_manager.py, reports.py, newsletter.py
   -> scheduler.py, upstox_client.py, instrument_master.py
   -> scanner.py, heatmap.py, backtest.py, calendar_data.py
   -> perplexity_client.py

scheduler.py  (APScheduler background jobs)
   -> config.py, settings_store.py, models.py
   -> upstox_client.py, perplexity_client.py, instrument_master.py
   -> scanner.py, strategy_engine.py, trade_executor.py, alerts_engine.py

scanner.py
   -> instrument_master.py
   (pure factor/score functions; receives candles + strategy params)

strategy_engine.py  (pure decision functions)
trade_executor.py   (sole mutator of Portfolio.cash_balance / Trade rows)
   -> models.py, strategy_engine.py

upstox_client.py  (Upstox REST + WebSocket wrapper, token-bucket rate limiter)
   -> config.py

instrument_master.py  (ISIN-based equity resolution + MCX master cache)
   -> data/nifty500.json, data/mcx_commodities.json (NOT PRESENT in repo)

heatmap.py, backtest.py, calendar_data.py, alerts_engine.py, reports.py,
newsletter.py, perplexity_client.py, portfolio_manager.py, models.py, auth.py
```

Runtime entry points:
- `python app.py` — Flask UI + (previously, when not DEMO_MODE) scheduler.
- `python scheduler.py` — documented as the long-lived loop (does not currently
  have a `__main__` block; runs via `init_scheduler(app)` from app.py).

Database: SQLite at `data/tradebot.db` via Flask-SQLAlchemy (`models.py`).

## 2. Baseline findings

### 2.1 Demo / fake market data (P0 — Phase 2)
- `upstox_client.py`: `_demo_price`, `_demo_candles`, `_start_demo_feed`,
  `demo_mode` constructor flag, `import random`. Demo fallback is reachable
  whenever `config.DEMO_MODE` is true OR the access token is missing.
- `config.py`: `DEMO_MODE` env toggle (default false).
- `app.py`: scheduler is skipped when `DEMO_MODE`; `debug=DEMO_MODE`.
- `heatmap.py`: previous-close placeholder uses `client._demo_price()` in
  demo mode.
- `settings_store.py`: exposes `demo_mode` in API-key status.

### 2.2 Non-market-data demo placeholders
- `perplexity_client.py`: `_demo_response` placeholder text when
  `PERPLEXITY_API_KEY` is missing. This is AI/editorial content, not market
  data; intentionally left out of the market-data removal phase. Address under
  AI-failure behavior (§119) in the AI phase.

### 2.3 Hardcoded historical dates (P0 — Phase 3)
- `scanner.py:141` uses `from_date="2024-01-01", to_date="2024-01-02"`.
- `backtest.py` takes user-supplied dates (OK for backtests).

### 2.4 Bundled universe files missing
- `instrument_master.py` reads `data/nifty500.json` / `data/mcx_commodities.json`;
  neither file is present in the repo, so `NIFTY500`/`MCX_COMMODITIES` are
  empty and `scanner.DEMO_NIFTY500_SAMPLE` falls back to a hardcoded list.
- Do NOT fabricate constituents (instruction §46). Needs a real sourced copy.

### 2.5 Timezone handling inconsistent (P0 — Phase 6)
- `datetime.now()`, `datetime.utcnow()`, `date.today()` mixed across
  `scheduler.py`, `models.py`, `trade_executor.py`.

### 2.6 Risk calculation (P0 — Phase 7)
- `scheduler._global_risk_ok` uses lifetime `realized_pnl` / starting balance
  as a proxy for today's loss (§4.6, §34).

### 2.7 WebSocket error handling weak (P0 — Phase 4)
- `start_feed` swallows errors (`streamer.on("error", lambda e: None)`), no
  reconnect/heartbeat/stale detection.

### 2.8 Test baseline (Phase 1 item 10)
- No `tests/` directory exists. pytest added as a dev dependency.

### 2.9 .gitignore
- Strengthened to match §70 (`.env.*`, `*.db`, `*.sqlite*`, `logs/`, `*.log`,
  `venv/`).

## 3. Secrets check
- No `.env` file committed; all credentials read from environment variables in
  `config.py`. `git log` shows a single commit (initial upload).

## 4. Phase progress

| Phase | Status |
|-------|--------|
| 1 — Repository baseline | DONE (this doc) |
| 2 — Remove demo market data | DONE (commit `fix: enforce real market data only`) |
| 3 — Historical data (dynamic dates, cache) | DONE (commit `fix: make historical market data dynamic and validated`) |
| 4 — Live feed hardening | NEXT |
| 5 — Scanner | pending |
| 6 — Market calendar / timezone | pending |
| 7 — Risk engine | pending |
| 8 — Execution layer | pending |
| 9 — Database hardening | pending |
| 10 — Observability | pending |
| 11 — Notifications | pending |
| 12+ — AI / Hermes / OpenAlgo / self-learning | pending |

## 5. Phase 2 completion notes

- Removed `DEMO_MODE` from `config.py` and all `demo_mode` handling.
- Removed `_demo_price`, `_demo_candles`, `_start_demo_feed`, and the `random`
  import from `upstox_client.py`. No fake market data path remains.
- Added `MarketDataConfigError`; `get_ltp`, `get_quote`, `get_historical_candles`,
  and `start_feed` now fail closed with an explicit `UPSTOX_ACCESS_TOKEN`
  configuration error when no token is set.
- Added `UpstoxClient.get_quote()` (OHLC quote with previous close) and rewired
  `heatmap.py` to compute sector day-change from real last_price vs prev_close
  instead of the demo placeholder.
- `app.py` no longer gates the scheduler on `DEMO_MODE`; the scheduler always
  runs. UI market-data lookups fail closed (log + empty, never fake prices).
- `settings_store.get_api_key_status()` no longer reports `demo_mode`.
- Fixed `instrument_master.py` to tolerate missing bundled data files (was a
  startup crash) — does not fabricate constituents.
- Added `tests/test_market_data.py` (11 fail-closed + parsing tests).
- README updated: real-data-only requirement, no demo-mode instructions.

Remaining (not in scope for Phase 2, tracked for later phases):
- `perplexity_client._demo_response` placeholder text when no AI key is set
  (AI/editorial content, not market data — address in AI phase per §119).
- `scanner.DEMO_NIFTY500_SAMPLE` naming + missing `data/nifty500.json` /
  `data/mcx_commodities.json` (scanner/universe phase; do not fabricate).
- `scanner.py` hardcoded `2024-01-01`/`2024-01-02` dates (Phase 3).

## 6. Phase 3 completion notes

- New `historical_data.py`:
  - `historical_date_range()` computes from/to dates dynamically from required
    candle count, timeframe, and end date — no hardcoded dates.
  - `validate_candles()` rejects malformed candles, OHLC inconsistencies,
    negative volume, and duplicate/out-of-order timestamps.
  - `HistoricalDataService` caches by (instrument_key, timeframe), serves fresh
    cache without network, and fetches only the missing incremental tail.
  - Stale-data detection: data not covering the requested end date is flagged
    stale (no trades on it).
- `scanner.py`:
  - Hardcoded 2024 dates removed; `run_scan` uses `HistoricalDataService`.
  - `required_candles_for_params()` enforces per-factor minimum candle counts
    (SMA21 needs 21, RSI needs 15, volume needs 21, breakout needs 20, OI needs 5).
  - No signal from incomplete/invalid/stale data: such symbols get score 0,
    `data_quality=False`, and an `error` marker.
  - Results now carry `data_quality`, `data_timestamp`, and `error`.
- Added `tests/test_historical_data.py` (dynamic ranges, validation, caching,
  staleness, scanner minimum-candle rules). Full suite: 26 passing.
- `python app.py` imports cleanly with no token (fails closed on data access).

Remaining for Phase 3 items not fully covered (tracked):
- Live verification of candles requires a real token (item 30) — deferred until
  credentials are available in a runtime environment.
- `backtest.py` still uses caller-supplied date ranges (intended, §93).
