from __future__ import annotations

from stock_agent.provider_utils import validate_india_ticker, normalize_ticker
from stock_agent.models import MarketContext, NewsSignal, StockSnapshot
from stock_agent.providers.google_news_provider import GoogleNewsProvider
from stock_agent.providers.yfinance_provider import YFinanceMarketDataProvider
from stock_agent.services.analysis_service import StockAnalysisService


def fetch_market_context() -> MarketContext:
    return YFinanceMarketDataProvider().get_market_context()


def fetch_google_news(ticker: str, lookback_days: int) -> list[NewsSignal]:
    return GoogleNewsProvider().get_news(ticker, lookback_days)


def fetch_stock_snapshot(ticker: str, lookback_days: int) -> StockSnapshot:
    service = StockAnalysisService(
        market_data_provider=YFinanceMarketDataProvider(),
        news_provider=GoogleNewsProvider(),
    )
    return service.build_snapshot_with_news(ticker, lookback_days)
