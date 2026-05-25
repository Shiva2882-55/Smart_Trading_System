from __future__ import annotations

from stock_agent.config import get_settings
from stock_agent.providers.fallback_provider import FallbackMarketDataProvider, FallbackNewsProvider
from stock_agent.providers.google_news_provider import GoogleNewsProvider
from stock_agent.providers.mock_provider import MockMarketDataProvider, MockNewsProvider
from stock_agent.providers.yfinance_provider import YFinanceMarketDataProvider


def get_market_data_provider():
    settings = get_settings()
    if settings.market_provider == "yfinance":
        return YFinanceMarketDataProvider()
    if settings.market_provider == "mock":
        return MockMarketDataProvider()
    if settings.market_provider == "fallback":
        return FallbackMarketDataProvider(
            providers=[
                YFinanceMarketDataProvider(),
            ]
        )
    raise ValueError(f"Unsupported market provider: {settings.market_provider}")


def get_news_provider():
    settings = get_settings()
    if settings.news_provider == "google_news":
        return GoogleNewsProvider()
    if settings.news_provider == "mock":
        return MockNewsProvider()
    if settings.news_provider == "fallback":
        return FallbackNewsProvider(
            providers=[
                GoogleNewsProvider(),
            ]
        )
    raise ValueError(f"Unsupported news provider: {settings.news_provider}")
