from __future__ import annotations

from stock_agent.models import MarketContext, NewsSignal, StockSnapshot
from stock_agent.providers.base import MarketDataProvider, NewsProvider


class MockMarketDataProvider(MarketDataProvider):
    provider_name = "mock_market_data"

    def __init__(
        self,
        market_context: MarketContext | None = None,
        snapshots: dict[str, StockSnapshot] | None = None,
    ) -> None:
        self.last_provider_issues = []
        self._market_context = market_context or MarketContext(
            spy_change_3m=5.0,
            qqq_change_3m=4.0,
            vix_level=15.0,
            risk_label="risk_on",
            reasons=["Mock market context is favorable."],
            generated_at="2026-05-25T09:00:00+05:30",
        )
        self._snapshots = snapshots or {}

    def get_market_context(self) -> MarketContext:
        return self._market_context

    def get_stock_snapshot(self, ticker: str) -> StockSnapshot:
        if ticker in self._snapshots:
            return self._snapshots[ticker]

        return StockSnapshot(
            ticker=f"{ticker}.NS" if "." not in ticker else ticker,
            sector="Technology",
            company_name=f"{ticker} Mock Ltd",
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
            source=self.provider_name,
            news=[],
        )


class MockNewsProvider(NewsProvider):
    provider_name = "mock_news"

    def __init__(self) -> None:
        self.last_provider_issues = []

    def get_news(self, ticker: str, lookback_days: int) -> list[NewsSignal]:
        return [
            NewsSignal(
                headline=f"{ticker} shows positive market movement",
                source="mock_news",
                published="",
                sentiment_score=0.25,
                age_hours=None,
            )
        ]
