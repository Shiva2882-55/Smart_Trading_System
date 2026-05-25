from stock_agent.providers.fallback_provider import FallbackMarketDataProvider, FallbackNewsProvider
from tests.fakes import (
    SuccessfulMarketDataProvider,
    SuccessfulNewsProvider,
    TimeoutMarketDataProvider,
)


class AlwaysFailNewsProvider:
    provider_name = "always_fail_news"

    def __init__(self) -> None:
        self.last_provider_issues = []

    def get_news(self, ticker: str, lookback_days: int):
        raise RuntimeError(f"News unavailable for {ticker}")


def test_market_fallback_marks_snapshot_degraded_after_primary_failure():
    provider = FallbackMarketDataProvider(
        providers=[TimeoutMarketDataProvider(), SuccessfulMarketDataProvider()]
    )

    snapshot = provider.get_stock_snapshot("TCS.NS")

    assert snapshot.source == "successful_market"
    assert snapshot.degraded is True
    assert snapshot.warning is not None
    assert len(provider.last_provider_issues) == 1
    assert provider.last_provider_issues[0].provider == "timeout_market"


def test_news_fallback_returns_empty_news_in_degraded_mode_when_all_fail():
    provider = FallbackNewsProvider(providers=[AlwaysFailNewsProvider()])

    news = provider.get_news("TCS.NS", lookback_days=7)

    assert news == []
    assert len(provider.last_provider_issues) == 1
    assert provider.last_provider_issues[0].provider == "always_fail_news"


def test_news_fallback_uses_secondary_provider_after_primary_failure():
    provider = FallbackNewsProvider(
        providers=[AlwaysFailNewsProvider(), SuccessfulNewsProvider()]
    )

    news = provider.get_news("TCS.NS", lookback_days=7)

    assert len(news) == 1
    assert len(provider.last_provider_issues) == 1
    assert provider.last_provider_issues[0].provider == "always_fail_news"
