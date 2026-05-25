# Stock Research Agent

This project is a Python-based India stock analysis agent that:

- pulls live India stock and market data
- checks recent news from the internet
- scores stocks using multiple factors
- ranks Indian stocks by priority
- generates `BUY`, `HOLD`, or `SELL` style signals
- exports the results to Excel
- stores run history in PostgreSQL

## What it does

The agent analyzes stocks using:

- price momentum
- valuation and quality metrics
- earnings and revenue growth
- recent news sentiment
- sentiment trend over time
- risk score from volatility and drawdown
- sector rotation strength
- broad market context from index and volatility data

For each stock, it produces:

- priority rank
- overall score
- confidence score
- signal
- action such as `BUY_NOW`, `BUY_ON_DIP`, `WATCHLIST`, `SELL_NOW`, or `AVOID`
- timestamp for when the signal was generated
- timestamp for when the action was generated
- review timestamp for when to check the signal again
- entry price
- stop-loss
- take-profit
- explanation fields for why the stock was ranked that way

## What it is good for

- ranking a watchlist in order of strength
- checking which sectors are leading or lagging
- finding buy candidates and sell candidates quickly
- exporting everything to Excel for review
- generating a repeatable, rule-based daily stock report

## What it is not

- guaranteed financial advice
- a substitute for your own risk management
- a fully autonomous trading bot
- a promise that a stock will move exactly at the signal time

The date and time columns show when the signal was created, not a guaranteed future prediction. `BUY_NOW` means the setup looks favorable at the moment the report was generated.

## Project structure

```text
pyproject.toml
requirements.lock
requirements.txt
run_agent.py
.env.example
src/stock_agent/
watchlists/
tests/
```

## Installation

Open PowerShell in the project folder and run:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env
```

For local development tools:

```powershell
pip install -e ".[dev]"
```

For reproducible runtime installs:

```powershell
pip install -r requirements.lock
```

If PostgreSQL support is missing in your environment:

```powershell
pip install "psycopg[binary]>=3.2,<4.0"
```

Recommended pre-push checks:

```powershell
ruff check .
ruff format --check .
mypy src/stock_agent
pytest -q
python -m build
twine check dist/*
stock-agent --help
```

Configuration is validated at startup. If retry values, provider names, output directories, database settings, or the universe file are invalid, the app stops before analysis begins with a clear error.

## Database setup

The current runtime database is PostgreSQL.

Default connection settings:

- host: `localhost`
- port: `5432`
- database: `trading_stock_db`
- username: `postgres`
- password: `5502`
- schema: `trading_stock`

The app automatically creates and uses these tables inside the `trading_stock` schema:

- `analysis_runs`
- `run_ticker_results`
- `provider_errors`

If the schema or tables do not exist yet, `stock-agent healthcheck` or the first run will create them automatically.

## How to run

Run the default watchlist:

```powershell
stock-agent run
```

Backward-compatible script entrypoint:

```powershell
python run_agent.py run
```

Validate startup configuration only:

```powershell
stock-agent healthcheck
```

Run continuously in a loop until you stop it:

```powershell
stock-agent watch --tickers TCS.NS INFY.NS --interval-seconds 300
```

Use `Ctrl+C` to stop watch mode.

Show recent run history from PostgreSQL:

```powershell
stock-agent history --limit 10
```

Run specific stocks:

```powershell
stock-agent run --tickers TCS.NS INFY.NS RELIANCE.NS
```

Run a ticker file:

```powershell
stock-agent run --universe watchlists/core_watchlist.txt
```

Run from a previous Excel report:

```powershell
stock-agent run --input-excel reports\stock_analysis_25-05-26--15-56.xlsx
```

You can also point `--universe` to an Excel file, and the app will read ticker columns like `ticker` or `leader_ticker`.

Run the India preset universe:

```powershell
stock-agent run --preset nifty50 --top 20 --output nifty50_ranked_stocks.xlsx
```

Save output to a custom Excel file:

```powershell
stock-agent run --tickers TCS.NS INFY.NS --output stock_report.xlsx
```

Save reports to a directory:

```powershell
stock-agent run --output-dir reports
```

Run safely without live providers:

```powershell
$env:MARKET_PROVIDER="mock"
$env:NEWS_PROVIDER="mock"
stock-agent run --tickers TCS.NS INFY.NS --output-dir reports
```

Before analysis starts, the CLI now prints continuous feedback about what it understood, including:

- whether input came from explicit tickers, a text watchlist, or an Excel file
- which Excel sheet and column were used
- how many tickers were loaded
- a short ticker preview
- which providers will be used
- where the output report will be written

In `watch` mode, it repeats this process every cycle and tells you:

- which watch cycle is running
- when a cycle starts and finishes
- the last exit code
- how long it will sleep before the next cycle

## Excel output

Each run creates a new timestamped Excel file using Kolkata time (`Asia/Kolkata`), for example:

```text
stock_analysis_25-05-26--15-35.xlsx
```

If a file already exists for the same minute, a numeric suffix is added instead of overwriting the file.

The generated Excel file contains these sheets:

- `Dashboard`
- `Run Summary`
- `Provider Issues`
- `Report Summary`
- `Comparison Summary`
- `All Ranked Stocks`
- `Top Recommendations`
- `Bottom Signals`
- `Best Buy Opportunities`
- `Best Sell Candidates`
- `Sector Leaders`
- `Compare With Previous`
- `Skipped Tickers`

### `All Ranked Stocks`

This is the main sheet. It contains all analyzed stocks sorted by priority.

Important columns:

- `priority_rank`
- `ticker`
- `company_name`
- `sector`
- `signal`
- `action`
- `signal_generated_at`
- `action_timestamp`
- `review_timestamp`
- `score`
- `confidence_score`
- `risk_score`
- `sentiment_trend`
- `sector_relative_strength`
- `entry_price`
- `stop_loss`
- `take_profit`
- `top_reason_1`
- `top_reason_2`

### `Dashboard`

The first sheet is now a user-friendly dashboard for quick understanding.

It includes:

- run status and warning severity
- total requested, succeeded, failed, and skipped counts
- degraded source summary
- top stock, top action, average score, and average confidence
- top recommendations table
- a previous-report comparison section
- a plain-language answer to whether following the previous report looked helpful or not
- comparison details for quick review

## Reliability and runtime behavior

Each run writes structured JSON logs to `logs/stock_agent.log` with fields such as `run_id`, `ticker`, `provider`, `retry_attempt`, `latency_ms`, and failure details.

Run metadata is persisted to PostgreSQL. Excel remains the report output, while PostgreSQL keeps permanent history for runs, ticker-level results, and provider failures.

Runs produce explicit partial-failure summaries too. When some tickers or providers fail, the run can still finish as `PARTIAL_SUCCESS`, with warning severity, degraded sources, console summary output, database audit entries, and extra Excel sheets for `Run Summary` and `Provider Issues`.

The runtime uses provider abstraction:

- `providers/yfinance_provider.py` handles market data only
- `providers/google_news_provider.py` handles news only
- `providers/fallback_provider.py` handles best-effort fallback and degraded mode
- `services/analysis_service.py` orchestrates them
- `providers/mock_provider.py` supports network-free tests

The application flow is split by layer:

- `cli.py` bootstraps commands and exit codes
- `services/run_orchestrator.py` controls the full run
- `services/analysis_service.py` analyzes one ticker at a time
- `providers/` own yfinance, Google News, Excel, and PostgreSQL I/O
- `models.py`, `scoring.py`, and `domain/` hold business rules and reporting models

## How the scoring works

The final ranking is a weighted combination of:

- momentum
- valuation
- quality
- growth
- average news sentiment
- recency-weighted sentiment trend
- sector relative strength
- market risk regime
- risk penalty from volatility and drawdown

### Main ideas

- momentum matters, but less than before
- strong sectors get a boost
- high-volatility and deep-drawdown stocks get penalized
- improving news trend helps
- broad market risk conditions affect the final recommendation

## Meaning of the action field

- `BUY_NOW`: conditions currently support entering
- `BUY_ON_DIP`: setup is bullish, but a slightly lower entry is preferred
- `WATCHLIST`: strong enough to monitor, but wait for better confirmation
- `SELL_NOW`: current setup is weak and may justify exiting or reducing
- `AVOID`: not attractive for fresh buying until conditions improve

## Example workflow

1. Run the agent in the morning or before market open.
2. Open the newest `stock_analysis_dd-mm-yy--hr-mm.xlsx` report.
3. Start with the `All Ranked Stocks` sheet.
4. Look at the highest `priority_rank` stocks.
5. Check `action`, `risk_score`, and `top_reason_1`.
6. Recheck stocks again at the `review_timestamp`.

## Report-to-report comparison

Every new run also keeps a history of earlier reports in a `report_history` folder.

When a new Excel report is generated, the agent:

- finds the latest previous archived report
- compares the current report with the previous one
- creates a `Compare With Previous` sheet
- creates a `Comparison Summary` sheet

This helps answer:

- if you had followed the earlier `BUY_NOW` or `BUY_ON_DIP` action, what would the result look like now
- if you had followed `SELL_NOW` or `AVOID`, would staying out have helped
- how each stock's priority rank changed from the previous report

Important note:

- this comparison is based on report-to-report price change
- it does not reconstruct intraday movement
- it does not guarantee the stop-loss or take-profit was touched during the day

## Notes

- Internet access is required for live market and news data.
- Results can change throughout the day because prices and headlines change.
- If a data source is temporarily unavailable, the run may still finish in degraded mode or `PARTIAL_SUCCESS`.
- External calls use structured retry logging with exponential backoff for traceability.

## Future improvements

- additional formal market-data/news providers behind the fallback layer
- email or Telegram delivery
- OpenAI-based narrative summaries
- scheduled cloud deployment options
