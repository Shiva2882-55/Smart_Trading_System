from __future__ import annotations

import logging
from dataclasses import replace

from stock_agent.domain.run_report import ProviderIssue
from stock_agent.models import MarketContext, NewsSignal, StockSnapshot
from stock_agent.providers.base import MarketDataProvider, NewsProvider


logger = logging.getLogger(__name__)


class FallbackMarketDataProvider(MarketDataProvider):
    provider_name = "fallback_market_data"

    def __init__(self, providers: list[MarketDataProvider]):
        if not providers:
            raise ValueError("At least one market data provider is required")
        self.providers = providers
        self.last_provider_issues: list[ProviderIssue] = []

    def get_market_context(self) -> MarketContext:
        self.last_provider_issues = []
        errors: list[str] = []
        for provider in self.providers:
            try:
                context = provider.get_market_context()
                self.last_provider_issues.extend(list(getattr(provider, "last_provider_issues", [])))
                if hasattr(provider, "last_provider_issues"):
                    provider.last_provider_issues = []
                return context
            except Exception as exc:
                errors.append(f"{provider.provider_name}: {exc}")
                self.last_provider_issues.append(
                    ProviderIssue(
                        ticker="",
                        provider=provider.provider_name,
                        operation="get_market_context",
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                        severity="WARNING",
                    )
                )
        raise RuntimeError(f"All market context providers failed. Errors: {' | '.join(errors)}")

    def get_stock_snapshot(self, ticker: str) -> StockSnapshot:
        self.last_provider_issues = []
        errors: list[str] = []
        for provider in self.providers:
            try:
                logger.info(
                    "market_provider_attempt_started",
                    extra={"event": "market_provider_attempt_started", "ticker": ticker, "provider": provider.provider_name},
                )
                snapshot = provider.get_stock_snapshot(ticker)
                self.last_provider_issues.extend(list(getattr(provider, "last_provider_issues", [])))
                if hasattr(provider, "last_provider_issues"):
                    provider.last_provider_issues = []
                if errors:
                    snapshot = replace(
                        snapshot,
                        degraded=True,
                        warning=f"Primary provider failed. Data loaded from fallback provider: {provider.provider_name}",
                        source=provider.provider_name,
                    )
                else:
                    snapshot = replace(snapshot, source=provider.provider_name)
                logger.info(
                    "market_provider_attempt_success",
                    extra={
                        "event": "market_provider_attempt_success",
                        "ticker": ticker,
                        "provider": provider.provider_name,
                        "degraded": snapshot.degraded,
                    },
                )
                return snapshot
            except Exception as exc:
                errors.append(f"{provider.provider_name} failed for {ticker}: {exc}")
                self.last_provider_issues.append(
                    ProviderIssue(
                        ticker=ticker,
                        provider=provider.provider_name,
                        operation="get_stock_snapshot",
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                        severity="WARNING",
                    )
                )
                logger.warning(
                    "market_provider_attempt_failed",
                    extra={
                        "event": "market_provider_attempt_failed",
                        "ticker": ticker,
                        "provider": provider.provider_name,
                        "error_type": type(exc).__name__,
                        "failure_reason": str(exc),
                    },
                )
        raise RuntimeError(f"All market data providers failed for {ticker}. Errors: {' | '.join(errors)}")


class FallbackNewsProvider(NewsProvider):
    provider_name = "fallback_news"

    def __init__(self, providers: list[NewsProvider]):
        if not providers:
            raise ValueError("At least one news provider is required")
        self.providers = providers
        self.last_provider_issues: list[ProviderIssue] = []

    def get_news(self, ticker: str, lookback_days: int) -> list[NewsSignal]:
        self.last_provider_issues = []
        errors: list[str] = []
        for provider in self.providers:
            try:
                logger.info(
                    "news_provider_attempt_started",
                    extra={"event": "news_provider_attempt_started", "ticker": ticker, "provider": provider.provider_name},
                )
                news = provider.get_news(ticker, lookback_days=lookback_days)
                self.last_provider_issues.extend(list(getattr(provider, "last_provider_issues", [])))
                if hasattr(provider, "last_provider_issues"):
                    provider.last_provider_issues = []
                logger.info(
                    "news_provider_attempt_success",
                    extra={
                        "event": "news_provider_attempt_success",
                        "ticker": ticker,
                        "provider": provider.provider_name,
                        "news_count": len(news),
                    },
                )
                return news
            except Exception as exc:
                errors.append(f"{provider.provider_name}: {exc}")
                self.last_provider_issues.append(
                    ProviderIssue(
                        ticker=ticker,
                        provider=provider.provider_name,
                        operation="get_news",
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                        severity="WARNING",
                    )
                )
                logger.warning(
                    "news_provider_attempt_failed",
                    extra={
                        "event": "news_provider_attempt_failed",
                        "ticker": ticker,
                        "provider": provider.provider_name,
                        "error_type": type(exc).__name__,
                        "failure_reason": str(exc),
                    },
                )
        logger.warning(
            "all_news_providers_failed_degraded",
            extra={"event": "all_news_providers_failed_degraded", "ticker": ticker, "failure_reason": " | ".join(errors)},
        )
        return []
