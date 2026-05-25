from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from stock_agent.domain.run_report import RunReport
from stock_agent.models import MarketContext, NewsSignal, StockSnapshot


class MarketDataProvider(ABC):
    provider_name: str = "market_data"

    @abstractmethod
    def get_market_context(self) -> MarketContext:
        raise NotImplementedError

    @abstractmethod
    def get_stock_snapshot(self, ticker: str) -> StockSnapshot:
        raise NotImplementedError


class NewsProvider(ABC):
    provider_name: str = "news"

    @abstractmethod
    def get_news(self, ticker: str, lookback_days: int) -> list[NewsSignal]:
        raise NotImplementedError


class ReportProvider(ABC):
    @abstractmethod
    def write_report(
        self,
        output_path: Path,
        recommendations: list,
        by_sector: dict[str, list],
        failures: list[str],
        run_report: RunReport,
        top_n: int,
    ) -> Path:
        raise NotImplementedError


class RunRepository(ABC):
    @abstractmethod
    def create_run(self, run_id: str, total_tickers: int = 0) -> None:
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    def add_ticker_result(
        self,
        run_id: str,
        ticker: str,
        status: str,
        provider: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    def get_recent_runs(self, limit: int = 10) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def get_run_details(self, run_id: str) -> dict:
        raise NotImplementedError
