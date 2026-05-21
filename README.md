# Stock Research Agent

This project is a Python-based India stock analysis agent that:

- pulls live India stock and market data
- checks recent news from the internet
- scores stocks using multiple factors
- ranks Indian stocks by priority
- generates `BUY`, `HOLD`, or `SELL` style signals
- exports the results to Excel

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
run_agent.py
requirements.txt
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
pip install -r requirements.txt
copy .env.example .env
```

If Excel export fails because of a missing package, run:

```powershell
pip install openpyxl
```

## How to run

Run the default watchlist:

```powershell
python run_agent.py
```

Run specific stocks:

```powershell
python run_agent.py --tickers AAPL MSFT NVDA AMZN META
```

Run a ticker file:

```powershell
python run_agent.py --universe watchlists/core_watchlist.txt
```

Run the India preset universe:

```powershell
python run_agent.py --preset nifty50 --top 20 --output nifty50_ranked_stocks.xlsx
```

Save output to a custom Excel file:

```powershell
python run_agent.py --tickers AAPL MSFT NVDA --output stock_report.xlsx
```

## Excel output

The generated Excel file contains these sheets:

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
2. Open `stock_analysis.xlsx`.
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
- how each stock’s priority rank changed from the previous report

Important note:

- this comparison is based on report-to-report price change
- it does not reconstruct intraday movement
- it does not guarantee the stop-loss or take-profit was touched during the day

## Notes

- Internet access is required for live market and news data.
- Results can change throughout the day because prices and headlines change.
- If a data source is temporarily unavailable, some signals may be weaker or missing.

## Future improvements

- Excel formatting with colors for `BUY`, `HOLD`, and `SELL`
- stop-loss and take-profit suggestion columns
- SEC filings and earnings transcript analysis
- scheduled daily report generation
- OpenAI-based narrative summaries
- email or Telegram delivery
