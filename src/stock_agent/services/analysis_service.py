from __future__ import annotations

import logging
from dataclasses import replace

from stock_agent.domain.run_report import ProviderIssue
from stock_agent.core.logging import get_current_provider, log_context
from stock_agent.models import MarketContext, StockAnalysisResult, StockSnapshot
from stock_agent.providers.base import MarketDataProvider, NewsProvider


logger = logging.getLogger(__name__)


class StockAnalysisService:
    def __init__(
        self,
        market_data_provider: MarketDataProvider,
        news_provider: NewsProvider,
    ) -> None:
        self.market_data_provider = market_data_provider
        self.news_provider = news_provider

    def get_market_context(self) -> MarketContext:
        return self.market_data_provider.get_market_context()

    def analyze_ticker(self, ticker: str, lookback_days: int) -> StockAnalysisResult:
        with log_context(ticker=ticker):
            logger.info(
                "ticker_analysis_started",
                extra={"event": "ticker_analysis_started"},
            )
            try:
                market_snapshot = self.market_data_provider.get_stock_snapshot(ticker)
                market_issues = self._provider_issues_for(self.market_data_provider)
                news = self.news_provider.get_news(market_snapshot.ticker, lookback_days)
                news_issues = self._provider_issues_for(self.news_provider)
                full_snapshot = replace(market_snapshot, news=news)
                provider_issues = market_issues + news_issues
                degraded = full_snapshot.degraded or bool(provider_issues)
                warning = full_snapshot.warning
                if warning is None and provider_issues:
                    sources = ", ".join(sorted({issue.provider for issue in provider_issues if issue.provider}))
                    warning = (
                        "One or more best-effort providers failed. "
                        f"Run completed in degraded mode using: {sources or 'fallback data'}."
                    )
                logger.info(
                    "ticker_analysis_completed",
                    extra={"event": "ticker_analysis_completed", "status": "SUCCESS", "degraded": degraded},
                )
                return StockAnalysisResult(
                    ticker=ticker,
                    snapshot=full_snapshot,
                    news=news,
                    status="SUCCESS",
                    degraded=degraded,
                    warning=warning,
                    provider_issues=provider_issues,
                )
            except Exception as exc:
                provider_issues = self._provider_issues_for(self.market_data_provider) + self._provider_issues_for(self.news_provider)
                logger.exception(
                    "ticker_analysis_failed",
                    extra={
                        "event": "ticker_analysis_failed",
                        "status": "FAILED",
                        "error_type": type(exc).__name__,
                        "failure_reason": str(exc),
                    },
                )
                return StockAnalysisResult(
                    ticker=ticker,
                    snapshot=None,
                    news=[],
                    status="FAILED",
                    error=str(exc),
                    error_type=type(exc).__name__,
                    provider=get_current_provider(),
                    degraded=bool(provider_issues),
                    provider_issues=provider_issues,
                )

    def build_snapshot_with_news(self, ticker: str, lookback_days: int) -> StockSnapshot:
        result = self.analyze_ticker(ticker, lookback_days)
        if result.snapshot is None:
            raise RuntimeError(result.error or f"Unable to analyze ticker {ticker}.")
        return result.snapshot

    @staticmethod
    def _provider_issues_for(provider) -> list[ProviderIssue]:
        issues = list(getattr(provider, "last_provider_issues", []))
        if hasattr(provider, "last_provider_issues"):
            provider.last_provider_issues = []
        return issues
