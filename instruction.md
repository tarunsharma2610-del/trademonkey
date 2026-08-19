# TradeBot AI — Master Engineering Instructions

Version: 1.0
Repository: tarunsharma2610-del/tradebot
Default branch: main

---

# 0. PURPOSE

You are the engineering agent responsible for improving this repository.

This file is the primary engineering instruction for the project.

Read this file completely before modifying any code.

The goal is to turn the existing TradeBot AI application into a robust:

- live-market-data paper-trading platform
- multi-portfolio trading engine
- multi-strategy trading system
- automated scanner
- automated entry/exit engine
- risk-management engine
- market intelligence system
- notification system
- future AI trading-agent platform
- future Hermes integration layer
- future OpenAlgo/broker execution layer
- optional real-broker execution system

The current system is PAPER TRADING.

Real broker execution must remain disabled unless explicitly enabled through a separate execution mode and safety controls.

---

# 1. CRITICAL RULES

These rules override convenience.

## RULE 1 — NO DEMO MARKET DATA

The application must NEVER generate fake, simulated, random, sample, dummy, placeholder, or synthetic market prices.

Do NOT use:

- random prices
- random candles
- fake LTP
- simulated LTP
- generated candles
- fake market feeds
- mock market data in production code
- fallback prices
- hardcoded market prices
- hardcoded historical candles

The system must use actual Upstox market data.

If live market data is unavailable:

FAIL CLOSED.

Do not fall back to fake data.

---

# 2. NO DEMO MODE

Remove production support for:

- DEMO_MODE
- demo_mode
- Force demo
- simulated prices
- demo feed
- demo candles
- demo LTP
- fake market fallback

The following concepts must eventually disappear from production code:

- `_demo_price`
- `_demo_candles`
- `_start_demo_feed`
- `DEMO_MODE`
- `demo_mode`
- `Force demo`
- `simulated`
- `fake market`
- `mock market`
- random market data

Development testing may use isolated unit-test fixtures, but those fixtures must NEVER be reachable from the production market-data path.

---

# 3. FAIL-CLOSED MARKET DATA

If Upstox authentication is missing:

Raise an explicit configuration error.

If the access token is expired:

Raise an authentication error.

If Upstox returns an error:

Raise/report the error.

If historical data is unavailable:

Do not trade.

If LTP is stale:

Do not trade.

If WebSocket disconnects:

Do not assume the previous price is current.

If the feed is unhealthy:

Stop new entries.

Existing paper positions must continue to be risk-managed according to the last trustworthy state, with a clear stale-data state.

Never invent data.

---

# 4. CURRENT REPOSITORY AUDIT FINDINGS

The current repository contains the following important issues.

## 4.1 Demo market data exists

`upstox_client.py` currently contains:

- demo LTP generation
- demo candle generation
- demo WebSocket feed
- random price generation
- fallback behavior

This must be removed from the production path.

---

## 4.2 Scanner uses hardcoded historical dates

Current scanner behavior uses:

    from_date="2024-01-01"
    to_date="2024-01-02"

This is incorrect for a live trading scanner.

Historical data must be dynamically calculated based on:

- current trading date
- strategy timeframe
- required candle count
- market session
- lookback period

Never hardcode 2024 dates.

---

## 4.3 Scanner does not explicitly enforce sufficient candle quality

The scoring engine can operate with too few candles.

Every strategy must specify its minimum data requirement.

Example:

- SMA 21 requires at least 21 usable candles
- RSI 14 requires at least 15
- breakout 20 requires at least 20
- volume comparison requires sufficient history
- ATR requires sufficient history

If insufficient data exists:

Do not generate a trading signal.

---

## 4.4 Historical data should not be downloaded unnecessarily every cycle

The scheduler currently invokes scanning during market hours.

Historical candles should be cached intelligently.

Use:

- latest known candle timestamp
- incremental candle retrieval
- in-memory cache
- persistent cache where appropriate
- rate-limit aware refresh

Do not repeatedly download the entire historical dataset for every symbol every minute.

---

## 4.5 MCX instrument handling requires hardening

MCX contracts roll.

The instrument resolver must:

- refresh instrument master
- identify active contracts
- reject expired contracts
- avoid stale contracts
- cache instrument metadata
- refresh at appropriate intervals

Do not hardcode expired MCX instruments.

---

## 4.6 Risk calculations require review

The current scheduler's global risk calculation uses portfolio realized P&L and starting balances.

This needs to distinguish:

- daily P&L
- total realized P&L
- unrealized P&L
- portfolio-level risk
- global risk
- deployed capital
- reserved capital
- margin
- open-position risk

Do not use lifetime realized P&L as a substitute for today's loss.

---

## 4.7 Timezone handling needs correction

The scheduler uses:

- `datetime.now()`
- `datetime.utcnow()`
- `date.today()`

in different places.

The system must use one explicit timezone strategy.

Use:

    Asia/Kolkata

for Indian market calculations.

Store database timestamps consistently.

Prefer timezone-aware UTC timestamps internally and convert to IST for market logic/UI.

---

## 4.8 WebSocket error handling is too weak

The live feed currently effectively ignores WebSocket errors.

Errors must be captured.

Implement:

- connection state
- reconnect
- exponential backoff
- heartbeat
- stale-feed detection
- subscription recovery
- connection logging
- health metrics

---

## 4.9 Trade execution needs transaction safety

The centralized trade executor is a good architectural decision.

Keep it.

However, add:

- transaction boundaries
- idempotency
- duplicate-entry prevention
- position locks
- concurrency protection
- order state
- execution audit
- deterministic calculations

---

## 4.10 No real execution abstraction yet

The system must eventually support:

    PAPER
    BROKER

with a strict execution abstraction.

Do not mix broker execution code into strategy logic.

---

# 5. GOOD ARCHITECTURAL DECISIONS — PRESERVE THESE

Do not unnecessarily rewrite working architecture.

The following are good:

## 5.1 Centralized trade executor

`trade_executor.py` is the only module intended to mutate:

- cash balance
- Trade records

Keep this principle.

---

## 5.2 Strategy engine separation

Strategy decisions are separated from trade execution.

Preserve:

    scanner
        ↓
    strategy_engine
        ↓
    trade_executor

---

## 5.3 Multi-portfolio architecture

Keep:

- Portfolio
- Strategy
- Trade
- ScanResult
- AuditLog
- DailyReport

---

## 5.4 Strategy snapshots

Trade records store strategy configuration snapshots.

Preserve this because historical trades must remain explainable even if a strategy changes later.

---

## 5.5 Risk configuration

Global risk limits already exist.

Expand them rather than replacing them.

---

## 5.6 NIFTY 500 universe

Keep the bundled universe concept.

Improve freshness and validation.

---

## 5.7 Paper-trading separation

Keep paper trading as the default.

Real trading must be opt-in.

---

# 6. TARGET ARCHITECTURE

Target:

    Market Data
         |
         v
    Data Normalizer
         |
         +---- Historical Candle Store
         |
         +---- Live Tick Store
         |
         v
    Scanner
         |
         v
    Feature Engine
         |
         v
    Strategy Engine
         |
         v
    Risk Engine
         |
         v
    Trade Decision
         |
         v
    Execution Router
       /        \
      /          \
   PAPER       BROKER
      |
      v
 Portfolio / Trade Ledger
      |
      +---- Notifications
      |
      +---- Reports
      |
      +---- AI Agent
      |
      +---- Hermes
      |
      +---- OpenAlgo
      |
      +---- Telegram
      |
      +---- WhatsApp

---

# 7. EXECUTION MODES

Implement explicit execution modes.

    PAPER
    BROKER

Default:

    PAPER

Broker mode must require explicit enablement.

Never silently switch to broker mode.

---

# 8. BROKER SAFETY

Before real broker execution is enabled, require:

- explicit configuration
- broker credentials
- broker connection health
- instrument validation
- order-size limits
- max daily loss
- max trade value
- max open positions
- emergency stop
- kill switch
- audit logging

Never allow an AI agent to bypass risk controls.

---

# 9. UPSTOX DATA LAYER

Create a clean interface.

Example:

    MarketDataProvider

Required methods:

    get_ltp()
    get_quote()
    get_historical_candles()
    subscribe_ticks()
    unsubscribe_ticks()
    health()
    get_instruments()

Upstox becomes the first implementation.

Future providers must be possible without changing strategy code.

---

# 10. LIVE DATA VALIDATION

Every live price must have:

- instrument key
- timestamp
- price
- source
- received timestamp
- feed status

Reject:

- null prices
- negative prices
- zero prices where invalid
- impossible jumps
- stale ticks
- unknown instruments

---

# 11. STALE DATA PROTECTION

Implement:

    MAX_TICK_AGE_SECONDS

If:

    current_time - tick_timestamp > MAX_TICK_AGE_SECONDS

mark the instrument stale.

Do not generate new trades from stale data.

---

# 12. HISTORICAL DATA ENGINE

Replace hardcoded dates.

Historical request should be based on:

    required_candles
    timeframe
    trading calendar
    current date

Example:

For 30-minute candles requiring 100 candles:

calculate a sufficient historical date range automatically.

---

# 13. CANDLE QUALITY

Validate:

- timestamp ordering
- duplicate timestamps
- OHLC consistency
- volume
- missing candles
- session boundaries
- timezone

Reject malformed candles.

---

# 14. CANDLE CACHE

Implement cache keyed by:

    instrument_key
    timeframe

Store:

- candles
- latest timestamp
- fetch timestamp
- source

Only request missing/incremental data where possible.

---

# 15. TRADING CALENDAR

Implement proper Indian market calendar support.

Do not assume:

    Monday-Friday = trading day

Account for:

- NSE holidays
- BSE holidays
- MCX holidays
- special sessions
- Muhurat trading
- exchange-specific schedules

---

# 16. MARKET SESSION ENGINE

Create explicit session states:

    CLOSED
    PRE_MARKET
    OPEN
    PRE_CLOSE
    CLOSED_AFTER_MARKET

Strategies should query session state instead of independently calculating times.

---

# 17. SCANNER IMPROVEMENTS

Scanner must:

- use real data
- dynamically calculate historical range
- validate candles
- calculate factors
- return confidence
- return data timestamp
- return data quality
- record errors

No signal from incomplete data.

---

# 18. FACTOR ENGINE

Keep the existing factors:

- SMA crossover
- RSI
- volume spike
- breakout
- OI change

But improve:

- validation
- normalization
- factor confidence
- missing-data handling
- segment awareness

---

# 19. OI LOGIC

Do not use OI for instruments where OI is not meaningful.

For equities:

    OI factor disabled

For F&O/MCX:

    OI may be enabled

Strategy configuration must define applicable factors.

---

# 20. SCORE ENGINE

Ensure:

    0 <= score <= 100

Validate strategy weights.

Reject negative weights.

Normalize weights safely.

Record factor-level scores.

---

# 21. SIGNAL GENERATION

Separate:

    market data
    features
    score
    signal
    decision

Do not let the scanner directly place trades.

---

# 22. STRATEGY ENGINE

Strategy engine should output a decision object.

Example:

    NO_TRADE
    BUY
    SELL
    EXIT

with:

- reason
- score
- confidence
- stop loss
- target
- quantity
- risk
- strategy ID

---

# 23. POSITION SIZING

Position sizing must consider:

- portfolio equity
- risk percentage
- stop distance
- available cash
- max position value
- max capital deployment
- instrument lot size

Never exceed available capital.

---

# 24. STOP LOSS

Support:

    ATR
    PERCENT
    SWING_LOW

Validate stop placement.

For BUY:

    stop < entry

For SELL:

    stop > entry

---

# 25. TARGET

Support:

    RISK_REWARD
    ATR
    PERCENT

Validate target direction.

---

# 26. TRAILING STOP

Trailing stops must:

- never move backward
- be persisted
- survive restart
- be recalculated from live price
- have activation rules

---

# 27. EXIT ENGINE

Exit checks must include:

- stop loss
- target
- trailing stop
- square-off
- manual close
- emergency flatten

All exits must be audited.

---

# 28. DUPLICATE TRADE PROTECTION

Prevent:

- duplicate entry for same signal
- duplicate position
- repeated execution after restart
- repeated webhook/order processing

Use idempotency keys.

---

# 29. RESTART SAFETY

After restart:

1. Load open positions.
2. Load active strategies.
3. Restore risk state.
4. Restore trailing stops.
5. Restore feed subscriptions.
6. Validate current market data.
7. Resume safely.

Never recreate trades accidentally.

---

# 30. DATABASE

Current SQLite setup can remain for initial paper trading.

But structure the application so PostgreSQL can replace it.

Production recommendation:

    PostgreSQL

Do not make database migration a prerequisite for every other improvement.

---

# 31. DATABASE CONSTRAINTS

Add constraints for:

- unique instrument identifiers
- valid trade status
- valid execution mode
- valid portfolio state
- non-negative quantity
- valid timestamps

---

# 32. AUDIT LOG

Every important action must be logged.

Examples:

- strategy created
- strategy changed
- portfolio created
- trade signal
- trade opened
- trade closed
- risk rejection
- feed failure
- broker failure
- AI decision
- notification sent
- kill switch activated

---

# 33. RISK ENGINE

Create a dedicated risk engine.

Responsibilities:

- daily loss
- maximum positions
- capital deployment
- position risk
- sector exposure
- instrument exposure
- strategy exposure
- portfolio exposure

---

# 34. DAILY LOSS

Calculate daily loss from today's trading activity.

Do not use lifetime realized P&L as daily loss.

Include:

- realized P&L
- unrealized P&L
- fees if modeled
- slippage if modeled

---

# 35. GLOBAL KILL SWITCH

Implement:

    SYSTEM_ENABLED

and:

    TRADING_ENABLED

Separate:

    DATA
    PAPER_TRADING
    BROKER_TRADING

A data outage must not automatically enable anything.

---

# 36. EMERGENCY FLATTEN

Implement an emergency paper-trading flatten operation.

Future broker implementation must have a separate broker flatten operation.

Require explicit confirmation for real broker flatten.

---

# 37. SCHEDULER

Keep scheduler responsibilities but improve reliability.

Jobs:

    pre_market
    market_open
    market_hours
    pre_close
    eod
    health_check
    instrument_refresh
    notification

---

# 38. SCHEDULER TIMEZONE

Use:

    Asia/Kolkata

for exchange scheduling.

Use timezone-aware datetime objects.

---

# 39. JOB LOCKING

Prevent duplicate scheduler instances from executing the same trade cycle.

Use:

- distributed lock
- database lock
- process lock

depending on deployment architecture.

---

# 40. HEALTH MONITORING

Expose:

    /health

and:

    /health/market-data
    /health/database
    /health/scheduler
    /health/notifications
    /health/execution

Return structured status.

---

# 41. ERROR HANDLING

Do not silently swallow exceptions.

Current scanner behavior that effectively ignores scan errors must be improved.

Log:

- symbol
- instrument
- operation
- exception
- timestamp

Continue processing other symbols where safe.

---

# 42. RETRIES

Use bounded retries for:

- network failures
- temporary Upstox failures

Do NOT retry indefinitely.

Use exponential backoff.

Do not retry invalid authentication forever.

---

# 43. RATE LIMITING

Keep the existing rate limiter concept.

Improve it with:

- endpoint-specific limits
- retry-after handling
- centralized request accounting
- historical request batching/caching
- metrics

---

# 44. INSTRUMENT MASTER

Create a robust instrument service.

Responsibilities:

- download
- validate
- cache
- refresh
- version
- activate/deactivate instruments
- resolve symbol
- resolve instrument key

---

# 45. MCX CONTRACT ROLLOVER

Automatically detect:

- expiry
- active contract
- next contract
- invalid contract

Never trade an expired contract.

---

# 46. NIFTY 500 FRESHNESS

Do not permanently trust the bundled list.

Add periodic refresh/validation.

Keep a known-good cached copy.

If refresh fails:

use the last verified copy.

Do not fabricate constituents.

---

# 47. PAPER EXECUTION

Paper execution should simulate:

- cash
- quantity
- entry
- exit
- P&L
- stop
- target
- slippage
- fees if configured

But paper execution must use REAL market prices.

"Paper" means simulated order execution, NOT simulated market data.

---

# 48. PAPER SLIPPAGE

Add configurable paper slippage.

Example:

    0.05%

But never modify market prices themselves.

Execution price may model slippage.

---

# 49. FEES

Create configurable fee model.

Support:

- brokerage
- exchange charges
- GST
- STT
- stamp duty
- SEBI charges

Keep it configurable by segment.

---

# 50. PERFORMANCE REPORTING

Reports should include:

- gross P&L
- net P&L
- win rate
- average winner
- average loser
- profit factor
- max drawdown
- Sharpe-like metrics where statistically meaningful
- expectancy
- average holding time
- exposure
- turnover

---

# 51. PORTFOLIO ANALYTICS

Add:

- equity curve
- drawdown curve
- daily returns
- strategy attribution
- sector attribution
- instrument attribution

---

# 52. TRADE JOURNAL

Each trade should contain:

- strategy
- signal
- factors
- entry
- exit
- risk
- target
- stop
- reason
- market regime if available
- AI reasoning if applicable

---

# 53. MARKET REGIME

Introduce a market-regime layer.

Possible states:

    BULL
    BEAR
    SIDEWAYS
    HIGH_VOLATILITY
    LOW_VOLATILITY

Do not hardcode regime labels.

Use measurable indicators.

---

# 54. STRATEGY ADAPTATION

Strategies may eventually adapt based on:

- volatility
- market regime
- performance

But adaptation must NOT directly rewrite production strategy parameters without controls.

Use:

    proposed change
        ↓
    validation
        ↓
    approval
        ↓
    activation

---

# 55. SELF-LEARNING

The system should NOT mean:

"AI can freely change itself."

Self-learning means:

- collect outcomes
- analyze performance
- detect patterns
- propose improvements
- backtest improvements
- paper-test improvements
- compare against baseline
- promote only after validation

---

# 56. AI TRADING AGENT

Prepare an AI-agent interface.

AI may:

- inspect market summaries
- inspect scanner results
- inspect portfolio state
- inspect strategy performance
- propose trades
- propose strategy changes
- explain decisions

AI must NOT bypass:

- risk engine
- execution router
- kill switch

---

# 57. HERMES INTEGRATION

Design a future adapter:

    HermesTradingAgent

Hermes should communicate through a controlled interface.

Possible inputs:

- market summary
- scanner candidates
- portfolio state
- risk state
- strategy state

Possible outputs:

- recommendation
- confidence
- reasoning
- proposed action

The final trade must pass through:

    Risk Engine
        ↓
    Execution Router

Hermes must never directly manipulate the database.

---

# 58. OPENALGO INTEGRATION

Prepare an adapter:

    OpenAlgoExecutionProvider

Do not make OpenAlgo a requirement for paper trading.

Architecture:

    Strategy
       ↓
    Risk Engine
       ↓
    Execution Router
       ↓
    PAPER provider

or:

    Strategy
       ↓
    Risk Engine
       ↓
    Execution Router
       ↓
    OpenAlgo provider
       ↓
    Broker

OpenAlgo must remain replaceable.

Do not couple strategy code to OpenAlgo APIs.

---

# 59. BROKER ABSTRACTION

Future providers should include:

    Upstox
    OpenAlgo
    other broker adapters

Define standard methods:

    place_order()
    modify_order()
    cancel_order()
    get_order()
    get_positions()
    get_account()
    health()

---

# 60. BROKER MODE SAFETY

Broker execution must require:

    EXECUTION_MODE=BROKER

plus:

    BROKER_TRADING_ENABLED=true

plus successful:

    risk check
    broker health check
    authentication check

Never default to broker mode.

---

# 61. TELEGRAM BOT

Add optional Telegram integration.

Capabilities:

- daily market summary
- portfolio summary
- open trades
- closed trades
- P&L
- scanner alerts
- risk alerts
- system health
- broker connection status
- emergency notification

Telegram credentials must be environment variables/secrets.

Never commit tokens.

---

# 62. WHATSAPP

Add optional WhatsApp integration.

Prefer an official provider/API.

Do not implement unofficial WhatsApp scraping.

Possible capabilities:

- market summary
- portfolio summary
- trade opened
- trade closed
- risk alert
- EOD report
- system failure

Use a notification abstraction.

---

# 63. NOTIFICATION ABSTRACTION

Create:

    NotificationProvider

Implement:

    TelegramProvider
    WhatsAppProvider

Future:

    EmailProvider
    WebPushProvider

Application code should call:

    notification_service.send(...)

not Telegram/WhatsApp directly.

---

# 64. USER NOTIFICATION PREFERENCES

Allow:

- enable/disable Telegram
- enable/disable WhatsApp
- market summary frequency
- trade notifications
- risk notifications
- EOD summary
- system alerts

---

# 65. MARKET SUMMARY

Generate a structured market summary.

Include:

- NIFTY
- BANK NIFTY
- SENSEX
- major sector movement
- market breadth
- volatility
- top scanner candidates
- portfolio status

Use live market data.

Never hardcode indices.

---

# 66. PORTFOLIO SUMMARY

Notification should include:

- portfolio
- balance
- invested capital
- open positions
- unrealized P&L
- realized P&L
- today's P&L
- risk status

---

# 67. TRADE ALERT

Trade-open notification:

    Portfolio
    Symbol
    Side
    Quantity
    Entry
    Stop
    Target
    Strategy
    Score
    Risk

Trade-close:

    Exit
    P&L
    Reason
    Holding duration

---

# 68. SECURITY

Never commit:

- Upstox access token
- Upstox API secret
- Perplexity API key
- Telegram bot token
- WhatsApp credentials
- broker credentials
- database passwords

Use:

    .env

or deployment secret manager.

---

# 69. SECRET SCANNING

Before every commit search for:

- API keys
- tokens
- passwords
- secrets
- private keys

Do not commit secrets.

---

# 70. .GITIGNORE

Ensure `.gitignore` excludes:

    .env
    .env.*
    venv/
    __pycache__/
    *.db
    *.sqlite
    *.sqlite3
    logs/
    *.log

Do not ignore source files.

---

# 71. TESTING

Create a real test suite.

Minimum:

    tests/

Include:

    test_market_data.py
    test_scanner.py
    test_strategy_engine.py
    test_risk_engine.py
    test_trade_executor.py
    test_portfolio.py
    test_notifications.py
    test_instrument_master.py

---

# 72. UNIT TESTS

Test:

- insufficient candles
- invalid prices
- invalid strategy
- risk rejection
- position sizing
- SL
- target
- trailing stop
- duplicate trade
- insufficient balance

---

# 73. INTEGRATION TESTS

Test:

    market data
       ↓
    scanner
       ↓
    strategy
       ↓
    risk
       ↓
    paper execution

Use deterministic fixtures.

Fixtures are allowed only inside tests.

They must never enter production data paths.

---

# 74. NO TEST FIXTURE LEAKAGE

Never import test fake market data from application modules.

Bad:

    from tests.fake_market import ...

inside production code.

Good:

production code expects MarketDataProvider.

Tests inject a fake provider.

---

# 75. LINTING

Add:

- Ruff
- Black if desired
- mypy where practical

At minimum run:

    ruff check .

---

# 76. TYPE SAFETY

Gradually introduce type hints.

Prioritize:

- market data
- strategy decisions
- risk decisions
- execution interfaces

---

# 77. API VALIDATION

Validate all incoming API/UI values.

Do not trust:

- symbol
- quantity
- price
- portfolio ID
- strategy ID
- execution mode

---

# 78. DATABASE TRANSACTIONS

Avoid committing halfway through a multi-step trade operation.

Prefer:

    begin
       validate
       create/update records
       update balance
       audit
    commit

Rollback on failure.

---

# 79. CONCURRENCY

Scheduler and web UI may access the same database simultaneously.

Protect:

- portfolio balance
- open trades
- strategy changes
- reset operations

---

# 80. MANUAL CONTROLS

Dashboard should provide:

- pause trading
- resume trading
- close paper position
- close portfolio
- disable strategy
- disable portfolio

Broker actions require stronger confirmation.

---

# 81. RESET SAFETY

Portfolio reset must never erase historical trade journal.

Preserve:

- closed trades
- audit history
- reports

Reset only allowed fields.

---

# 82. LOGGING

Use structured logging.

Include:

    timestamp
    level
    component
    portfolio
    strategy
    symbol
    event
    error

Avoid sensitive values.

---

# 83. OBSERVABILITY

Track:

- market-data requests
- response latency
- WebSocket state
- scan duration
- number of symbols
- rejected signals
- trades
- errors
- notification status

---

# 84. SYSTEM STATUS

Dashboard should clearly show:

    LIVE DATA
    DATA STALE
    UPSTOX DISCONNECTED
    SCANNER RUNNING
    TRADING PAUSED
    PAPER MODE
    BROKER MODE

Never display "LIVE" unless verified.

---

# 85. REMOVE MISLEADING UI

Remove all UI controls/messages suggesting demo market data.

There must be no:

    Demo
    Simulated
    Fake
    Force demo

market-data options.

---

# 86. README

Update README to reflect the actual architecture.

Do not document demo market data as a supported production mode.

Clearly document:

- live data requirement
- paper execution
- broker execution
- setup
- environment variables
- tests
- architecture
- Telegram
- WhatsApp
- Hermes
- OpenAlgo

---

# 87. CONFIGURATION

Move operational configuration to environment/config.

Examples:

    UPSTOX_ACCESS_TOKEN
    PERPLEXITY_API_KEY
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID
    WHATSAPP_PROVIDER
    WHATSAPP_API_KEY
    EXECUTION_MODE
    TRADING_ENABLED
    MAX_TICK_AGE_SECONDS

Do not hardcode secrets.

---

# 88. DATA PROVIDER CONTRACT

Define an interface so that AI agents and strategies never care whether data comes from:

    Upstox
    another provider
    test provider

But production must use the real provider.

---

# 89. EXECUTION PROVIDER CONTRACT

Define:

    ExecutionProvider

with:

    open_position
    close_position
    modify_position
    get_positions
    health

Paper provider:

    PaperExecutionProvider

Broker provider:

    BrokerExecutionProvider

---

# 90. AI PERMISSION MODEL

AI agents must have permission levels.

Example:

    OBSERVE
    RECOMMEND
    PAPER_EXECUTE
    BROKER_EXECUTE

Default:

    OBSERVE

AI must not automatically receive BROKER_EXECUTE permission.

---

# 91. AI DECISION LOG

Every AI-generated recommendation must be stored.

Record:

- model
- prompt version
- timestamp
- input snapshot
- recommendation
- confidence
- final decision
- risk result
- execution result

---

# 92. AI DOES NOT CONTROL RISK

Architecture:

    AI
      ↓
    Proposal
      ↓
    Risk Engine
      ↓
    Execution Router

Never:

    AI → Broker

---

# 93. BACKTESTING

Backtesting must use historical market data.

It must not use generated candles.

Backtest engine must clearly identify:

    BACKTEST

versus:

    LIVE

versus:

    PAPER

---

# 94. BACKTEST VALIDATION

Prevent look-ahead bias.

Ensure:

- indicators use only past data
- no future candle leakage
- realistic execution
- slippage
- fees
- market hours

---

# 95. WALK-FORWARD TESTING

Add:

    train period
    validation period
    test period

Do not optimize against the entire history.

---

# 96. STRATEGY VERSIONING

Every strategy change should create a version.

Example:

    strategy_id
    version
    created_at
    parameters

Trades must reference the strategy version.

---

# 97. CHANGE MANAGEMENT

Never perform huge blind rewrites.

Before changing architecture:

1. inspect current implementation
2. identify dependencies
3. write tests
4. make small change
5. run tests
6. commit
7. continue

---

# 98. GIT COMMIT RULE — MANDATORY

After EVERY completed logical improvement:

    git status
    git diff
    tests
    git add
    git commit

Then push.

Do not accumulate dozens of unrelated changes in one uncommitted working tree.

---

# 99. COMMIT MESSAGE FORMAT

Use meaningful commits.

Examples:

    fix: remove simulated market-data fallback
    fix: make scanner historical range dynamic
    feat: add stale-market-data protection
    feat: add Telegram notification provider
    feat: add execution provider abstraction
    test: add scanner validation tests
    refactor: isolate Upstox market-data provider

---

# 100. PUSH RULE

After successful tests:

    git push origin <branch>

Verify the push succeeded.

If push fails:

STOP and report the failure.

Do not claim the work is saved remotely when it is not.

---

# 101. BRANCH SAFETY

For significant changes:

Create:

    feature/<name>

or:

    fix/<name>

Do not directly destroy `main`.

Use pull requests for major architecture changes.

---

# 102. NEVER FORCE PUSH

Do not use:

    git push --force

unless explicitly instructed by the repository owner.

---

# 103. NEVER DELETE WORKING CODE BLINDLY

Before removing a module:

- search references
- understand dependencies
- update imports
- run tests
- verify application startup

---

# 104. CHANGE VERIFICATION

After each change:

    python -m compileall .

and:

    pytest

where tests exist.

Also run relevant application checks.

---

# 105. LIVE DATA VERIFICATION

Before declaring live-data work complete, verify:

1. token exists
2. Upstox authentication works
3. real LTP received
4. real historical candles received
5. timestamps are current
6. no demo fallback is reachable
7. stale detection works
8. scanner uses dynamic dates
9. scanner produces valid results

---

# 106. MARKET DATA FAILURE TEST

Test:

- expired token
- no token
- Upstox 401
- Upstox 429
- network timeout
- malformed response
- empty candle response
- WebSocket disconnect

Expected behavior:

    NO FAKE DATA
    NO NEW TRADES

---

# 107. PAPER TRADE VALIDATION

Run paper trading using real Upstox market data.

Verify:

- real LTP
- scanner
- signal
- risk
- paper entry
- paper exit
- P&L
- notifications

---

# 108. TELEGRAM IMPLEMENTATION ORDER

Implement:

1. provider interface
2. credentials
3. connectivity test
4. send message
5. market summary
6. trade-open alert
7. trade-close alert
8. risk alert
9. EOD report
10. user preferences

---

# 109. WHATSAPP IMPLEMENTATION ORDER

Implement:

1. provider interface
2. official API/provider
3. credentials
4. connectivity test
5. message service
6. market summary
7. trade alerts
8. portfolio summary
9. risk alerts

---

# 110. HERMES IMPLEMENTATION ORDER

Implement:

1. adapter interface
2. authentication/configuration
3. market-context API
4. portfolio-context API
5. strategy-context API
6. risk-context API
7. proposal schema
8. decision logging
9. paper execution integration
10. performance feedback loop

---

# 111. OPENALGO IMPLEMENTATION ORDER

Implement:

1. execution interface
2. OpenAlgo adapter
3. connection health
4. instrument mapping
5. order request mapping
6. order status mapping
7. position synchronization
8. paper/broker separation
9. risk enforcement
10. kill switch

---

# 112. REAL BROKER ACTIVATION

Do NOT activate real trading merely because OpenAlgo/Hermes integration works.

Require:

- explicit configuration
- manual confirmation
- broker health
- test order path
- risk limits
- kill switch
- audit logs

---

# 113. SELF-LEARNING IMPLEMENTATION ORDER

Phase 1:

Collect outcomes.

Phase 2:

Analyze strategy performance.

Phase 3:

Generate improvement proposals.

Phase 4:

Backtest proposals.

Phase 5:

Paper-test proposals.

Phase 6:

Compare against baseline.

Phase 7:

Require approval.

Phase 8:

Activate versioned strategy.

---

# 114. NO AUTONOMOUS UNCONTROLLED SELF-MODIFICATION

The AI agent must NEVER directly modify:

- risk limits
- broker credentials
- execution permissions
- kill switch
- production strategy
- system configuration

without explicit approval.

---

# 115. SECURITY REVIEW

Before broker integration:

Audit:

- authentication
- authorization
- secrets
- API routes
- CSRF
- session security
- SQL injection
- command injection
- SSRF
- webhook validation

---

# 116. WEBHOOK SECURITY

Telegram/WhatsApp/webhooks must use:

- authentication
- signature verification where supported
- replay protection
- rate limiting

---

# 117. RATE LIMIT UI

Prevent users from repeatedly triggering:

- scanner
- backtest
- notifications
- AI calls
- instrument refresh

---

# 118. AI COST CONTROL

Track:

- AI requests
- tokens
- cost
- response time

Prevent infinite AI loops.

---

# 119. AI FAILURE BEHAVIOR

If AI is unavailable:

The core trading system must continue safely.

AI is an enhancement.

It must not become a single point of failure.

---

# 120. CORE PRINCIPLE

The system must be able to operate:

    LIVE MARKET DATA
          +
    PAPER EXECUTION
          +
    NO AI

AI is optional.

---

# 121. PHASED IMPLEMENTATION PLAN

Do not attempt everything in one giant rewrite.

Implement in this order.

---

## PHASE 1 — REPOSITORY BASELINE

1. Inspect entire repository.
2. Generate dependency map.
3. Identify unused modules.
4. Identify duplicate logic.
5. Identify hardcoded values.
6. Identify demo/fake/mock market data.
7. Identify secrets.
8. Identify runtime state.
9. Identify database dependencies.
10. Establish test baseline.

Commit:

    chore: establish repository baseline

---

## PHASE 2 — REMOVE DEMO MARKET DATA

11. Remove demo LTP.
12. Remove demo candles.
13. Remove demo WebSocket.
14. Remove random market prices.
15. Remove DEMO_MODE production behavior.
16. Remove Force Demo UI.
17. Remove demo fallback.
18. Make missing token an error.
19. Make failed market data fail closed.
20. Update README.

Commit:

    fix: enforce real market data only

---

## PHASE 3 — FIX HISTORICAL DATA

21. Remove 2024 hardcoded dates.
22. Add dynamic historical range.
23. Add candle requirements.
24. Add candle validation.
25. Add timestamp validation.
26. Add incremental candle caching.
27. Add stale historical-data checks.
28. Add rate-limit protection.
29. Add historical-data tests.
30. Verify live candles manually.

Commit:

    fix: make historical market data dynamic and validated

---

## PHASE 4 — LIVE FEED HARDENING

31. Improve WebSocket errors.
32. Add reconnect.
33. Add heartbeat.
34. Add stale-feed detection.
35. Add subscription recovery.
36. Add feed health.
37. Add live-data metrics.
38. Reject stale LTP.
39. Add connection tests.
40. Verify real-time feed.

Commit:

    feat: harden live market-data feed

---

## PHASE 5 — SCANNER

41. Validate minimum candles.
42. Improve factor calculations.
43. Validate weights.
44. Remove silent failures.
45. Add scanner diagnostics.
46. Add market timestamp.
47. Add data quality score.
48. Add segment-aware factors.
49. Disable OI for equities.
50. Add scanner tests.

Commit:

    fix: harden scanner signal generation

---

## PHASE 6 — MARKET CALENDAR

51. Add India market calendar.
52. Add exchange-specific sessions.
53. Fix timezone handling.
54. Fix scheduler date handling.
55. Add pre-market state.
56. Add market-open state.
57. Add pre-close state.
58. Add holiday tests.
59. Add MCX session handling.
60. Verify scheduler timing.

Commit:

    feat: add exchange-aware market session engine

---

## PHASE 7 — RISK ENGINE

61. Create dedicated risk engine.
62. Fix daily P&L.
63. Add unrealized P&L.
64. Add capital deployment.
65. Add position exposure.
66. Add strategy exposure.
67. Add sector exposure.
68. Add maximum trade value.
69. Add global kill switch.
70. Add risk tests.

Commit:

    feat: implement centralized risk engine

---

## PHASE 8 — EXECUTION

71. Preserve trade executor.
72. Add execution provider interface.
73. Implement paper provider.
74. Add idempotency.
75. Add duplicate-entry protection.
76. Add transaction safety.
77. Add restart recovery.
78. Add slippage.
79. Add fees.
80. Add execution tests.

Commit:

    feat: implement safe paper execution layer

---

## PHASE 9 — DATABASE

81. Review schema.
82. Add constraints.
83. Add indexes.
84. Add strategy versioning.
85. Add execution records.
86. Add AI decision records.
87. Add notification records.
88. Add migration framework improvements.
89. Test concurrent operations.
90. Document PostgreSQL migration path.

Commit:

    feat: harden trading database

---

## PHASE 10 — OBSERVABILITY

91. Structured logging.
92. Health endpoint.
93. Market-data health.
94. Scheduler health.
95. Database health.
96. Execution health.
97. Notification health.
98. Error metrics.
99. Scan duration metrics.
100. Feed latency metrics.

Commit:

    feat: add trading-system observability

---

## PHASE 11 — NOTIFICATIONS

101. Create notification abstraction.
102. Add Telegram provider.
103. Add Telegram connectivity test.
104. Add market summary.
105. Add trade-open notification.
106. Add trade-close notification.
107. Add risk notifications.
108. Add EOD report.
109. Add WhatsApp provider.
110. Add notification preferences.

Commit:

    feat: add Telegram and WhatsApp notifications

---

## PHASE 12 — AI AGENT

111. Define AI adapter.
112. Add market context.
113. Add portfolio context.
114. Add strategy context.
115. Add risk context.
116. Add proposal schema.
117. Add AI decision logging.
118. Add confidence.
119. Add paper execution proposal path.
120. Add AI permission levels.

Commit:

    feat: add controlled AI trading-agent interface

---

## PHASE 13 — HERMES

121. Create Hermes adapter.
122. Connect market context.
123. Connect portfolio context.
124. Connect scanner context.
125. Connect risk context.
126. Receive proposals.
127. Validate proposals.
128. Log decisions.
129. Route through risk.
130. Route to paper execution.

Commit:

    feat: integrate Hermes trading agent

---

## PHASE 14 — OPENALGO

131. Create OpenAlgo adapter.
132. Implement authentication.
133. Implement health.
134. Implement order mapping.
135. Implement order status.
136. Implement positions.
137. Implement instrument mapping.
138. Add risk enforcement.
139. Add kill switch.
140. Test paper-to-broker architecture without enabling real orders.

Commit:

    feat: add OpenAlgo execution adapter

---

## PHASE 15 — SELF-LEARNING

141. Collect trade outcomes.
142. Calculate strategy statistics.
143. Detect weak strategies.
144. Generate improvement proposals.
145. Backtest proposals.
146. Walk-forward test.
147. Paper-test proposals.
148. Compare against baseline.
149. Version strategy changes.
150. Require approval before promotion.

Commit:

    feat: add controlled self-learning strategy pipeline

---

# 122. PRIORITY ORDER

If there is limited time, prioritize:

P0:

- remove demo market data
- remove hardcoded historical dates
- fail closed
- fix live feed
- fix scanner
- fix risk calculation
- fix timezone
- test paper execution

P1:

- health monitoring
- notifications
- execution abstraction
- database hardening

P2:

- Hermes
- OpenAlgo
- AI agent

P3:

- self-learning
- advanced analytics

---

# 123. DEFINITION OF DONE

The project is NOT considered production-ready until:

[ ] No demo market data exists.
[ ] No random market data exists.
[ ] No fake candles exist.
[ ] No hardcoded historical dates exist.
[ ] Missing Upstox data causes fail-closed behavior.
[ ] Real Upstox LTP is verified.
[ ] Real Upstox historical candles are verified.
[ ] WebSocket reconnect works.
[ ] Stale data is detected.
[ ] Scanner validates candle quality.
[ ] Risk engine is centralized.
[ ] Daily P&L is correct.
[ ] Paper execution is deterministic.
[ ] Duplicate trades are prevented.
[ ] Restart recovery works.
[ ] Market calendar works.
[ ] Timezone handling is correct.
[ ] Tests exist.
[ ] Tests pass.
[ ] Secrets are not committed.
[ ] Telegram is optional.
[ ] WhatsApp is optional.
[ ] Hermes is isolated behind an adapter.
[ ] OpenAlgo is isolated behind an adapter.
[ ] Broker mode is disabled by default.
[ ] Kill switch exists.
[ ] AI cannot bypass risk.
[ ] AI cannot directly access broker execution.
[ ] Audit logs exist.
[ ] README is updated.
[ ] Git history contains incremental commits.

---

# 124. FINAL AGENT BEHAVIOR

Before every task:

1. Read this file.
2. Inspect relevant existing code.
3. Do not assume missing functionality exists.
4. Do not rewrite working code unnecessarily.
5. Make the smallest safe change.
6. Add/update tests.
7. Run tests.
8. Run syntax checks.
9. Inspect git diff.
10. Search for secrets.
11. Commit the completed logical change.
12. Push the commit.
13. Verify the remote branch contains the commit.
14. Continue with the next task.

If a task cannot be safely completed:

STOP.

Explain:

- what failed
- why
- which files are affected
- what was tested
- what remains

Never fabricate success.

---

# 125. ABSOLUTE MARKET-DATA RULE

This project uses:

    REAL MARKET DATA

for:

- scanning
- indicators
- signals
- paper trading
- portfolio valuation
- alerts
- AI context
- Hermes context
- future broker execution

Paper trading does NOT mean fake market data.

Paper trading means:

    REAL MARKET DATA
          +
    SIMULATED ORDER EXECUTION

This distinction must never be violated.

---

# 126. ABSOLUTE BROKER RULE

Real broker execution must always be:

    OFF BY DEFAULT

and must never be activated automatically by:

- AI
- Hermes
- OpenAlgo
- scheduler
- configuration fallback
- missing configuration
- deployment restart

---

# 127. ABSOLUTE AI RULE

AI can recommend.

Risk engine decides whether a recommendation is allowed.

Execution provider executes only an approved decision.

Architecture:

    AI
      ↓
    Proposal
      ↓
    Validation
      ↓
    Risk Engine
      ↓
    Execution Router
      ↓
    PAPER / BROKER

Never bypass this chain.

---

# 128. ABSOLUTE GIT RULE

No completed work may remain only on the local machine.

After each logical improvement:

    TEST
      ↓
    COMMIT
      ↓
    PUSH
      ↓
    VERIFY

If GitHub push fails, resolve it before continuing.

---

# 129. FINAL OBJECTIVE

Build a system that can eventually operate as:

    REAL UPSTOX MARKET DATA
             ↓
       MARKET ENGINE
             ↓
          SCANNER
             ↓
        STRATEGIES
             ↓
       AI / HERMES
             ↓
        RISK ENGINE
             ↓
      EXECUTION ROUTER
          /       \
       PAPER     OPENALGO
                    |
                  BROKER
             ↓
        TRADE LEDGER
             ↓
       ANALYTICS / AI
             ↓
    TELEGRAM / WHATSAPP

while maintaining:

- safety
- auditability
- reproducibility
- real market data
- deterministic paper execution
- controlled AI
- controlled broker access
- incremental Git history
- no demo market-data fallback

This repository should evolve into a serious automated trading platform, not a demo application.