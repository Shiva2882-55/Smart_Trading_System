from __future__ import annotations

from pathlib import Path

from stock_agent.core.exceptions import EmptyDataError, ProviderTimeoutError
from stock_agent.domain.run_report import RunReport
from stock_agent.models import MarketContext, NewsSignal, StockSnapshot
from stock_agent.providers.base import MarketDataProvider, NewsProvider, ReportProvider, RunRepository


def _market_context() -> MarketContext:
    return MarketContext(
        spy_change_3m=5.0,
        qqq_change_3m=4.0,
        vix_level=15.0,
        risk_label="risk_on",
        reasons=["Mock market context is favorable."],
        generated_at="2026-05-25T09:00:00+05:30",
    )


def _snapshot_for(ticker: str) -> StockSnapshot:
    normalized = ticker if "." in ticker else f"{ticker}.NS"
    return StockSnapshot(
        ticker=normalized,
        sector="Technology",
        company_name=f"{normalized} Mock Ltd",
        current_price=2500.0,
        change_percent_3m=12.5,
        change_percent_6m=18.2,
        revenue_growth=0.16,
        earnings_growth=0.19,
        profit_margin=0.22,
        return_on_equity=0.24,
        forward_pe=20.0,
        debt_to_equity=35.0,
        trailing_eps=10.5,
        average_volume=1_500_000,
        market_cap=50_000_000_000,
        annualized_volatility=0.18,
        max_drawdown_6m=0.08,
        news=[],
    )


class SuccessfulMarketDataProvider(MarketDataProvider):
    provider_name = "successful_market"

    def __init__(self) -> None:
        self.last_provider_issues = []

    def get_market_context(self) -> MarketContext:
        return _market_context()

    def get_stock_snapshot(self, ticker: str) -> StockSnapshot:
        return _snapshot_for(ticker)


class TimeoutMarketDataProvider(MarketDataProvider):
    provider_name = "timeout_market"

    def __init__(self) -> None:
        self.last_provider_issues = []

    def get_market_context(self) -> MarketContext:
        return _market_context()

    def get_stock_snapshot(self, ticker: str) -> StockSnapshot:
        raise ProviderTimeoutError(f"Timeout while fetching market data for {ticker}")


class PartialMarketDataProvider(MarketDataProvider):
    provider_name = "partial_market"

    def __init__(self, failed_tickers: set[str]):
        self.failed_tickers = failed_tickers
        self.last_provider_issues = []

    def get_market_context(self) -> MarketContext:
        return _market_context()

    def get_stock_snapshot(self, ticker: str) -> StockSnapshot:
        normalized = ticker if "." in ticker else f"{ticker}.NS"
        if normalized in self.failed_tickers or ticker in self.failed_tickers:
            raise ProviderTimeoutError(f"Timeout while fetching market data for {ticker}")
        return _snapshot_for(ticker)


class EmptyMarketDataProvider(MarketDataProvider):
    provider_name = "empty_market"

    def __init__(self) -> None:
        self.last_provider_issues = []

    def get_market_context(self) -> MarketContext:
        return _market_context()

    def get_stock_snapshot(self, ticker: str) -> StockSnapshot:
        raise EmptyDataError(f"No data found for ticker: {ticker}")


class SuccessfulNewsProvider(NewsProvider):
    provider_name = "successful_news"

    def __init__(self) -> None:
        self.last_provider_issues = []

    def get_news(self, ticker: str, lookback_days: int) -> list[NewsSignal]:
        return [
            NewsSignal(
                headline=f"{ticker} stock shows positive momentum",
                source="mock_news",
                published="",
                sentiment_score=0.25,
                age_hours=None,
            )
        ]


class MalformedNewsProvider(NewsProvider):
    provider_name = "malformed_news"

    def __init__(self) -> None:
        self.last_provider_issues = []

    def get_news(self, ticker: str, lookback_days: int) -> list[NewsSignal]:
        raise ValueError(f"Malformed news feed for {ticker}")


class InMemoryRunRepository(RunRepository):
    def __init__(self):
        self.created_runs = []
        self.completed_runs = []
        self.ticker_results = []
        self.provider_errors = []

    def create_run(self, run_id: str, total_tickers: int = 0) -> None:
        self.created_runs.append({"run_id": run_id, "total_tickers": total_tickers})

    def complete_run(
        self,
        run_id: str,
        status: str,
        successful_tickers: int,
        failed_tickers: int,
        skipped_tickers: int,
        total_tickers: int,
        output_file_path: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        self.completed_runs.append(
            {
                "run_id": run_id,
                "status": status,
                "successful_tickers": successful_tickers,
                "failed_tickers": failed_tickers,
                "skipped_tickers": skipped_tickers,
                "total_tickers": total_tickers,
                "output_file_path": output_file_path,
                "error_summary": error_summary,
            }
        )

    def add_ticker_result(
        self,
        run_id: str,
        ticker: str,
        status: str,
        provider: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self.ticker_results.append(
            {
                "run_id": run_id,
                "ticker": ticker,
                "status": status,
                "provider": provider,
                "error_type": error_type,
                "error_message": error_message,
            }
        )

    def add_provider_error(
        self,
        run_id: str,
        provider: str,
        error_type: str,
        error_message: str,
        ticker: str | None = None,
        operation: str | None = None,
        retry_attempt: int | None = None,
    ) -> None:
        self.provider_errors.append(
            {
                "run_id": run_id,
                "ticker": ticker,
                "provider": provider,
                "operation": operation,
                "error_type": error_type,
                "error_message": error_message,
                "retry_attempt": retry_attempt,
            }
        )

    def get_recent_runs(self, limit: int = 10) -> list[dict]:
        return self.completed_runs[-limit:]

    def get_run_details(self, run_id: str) -> dict:
        return {
            "run": next((item for item in self.completed_runs if item["run_id"] == run_id), None),
            "ticker_results": [item for item in self.ticker_results if item["run_id"] == run_id],
            "provider_errors": [item for item in self.provider_errors if item["run_id"] == run_id],
        }


class FakeReportProvider(ReportProvider):
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.write_called = False

    def write_report(
        self,
        output_path: Path,
        recommendations: list,
        by_sector: dict[str, list],
        failures: list[str],
        run_report: RunReport,
        top_n: int,
    ) -> Path:
        self.write_called = True
        self.output_dir.mkdir(parents=True, exist_ok=True)
        file_path = self.output_dir / f"{run_report.run_id}.xlsx"
        file_path.write_text("fake excel report generated", encoding="utf-8")
        return file_path
