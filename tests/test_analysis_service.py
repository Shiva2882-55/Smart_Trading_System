from stock_agent.providers.mock_provider import MockMarketDataProvider, MockNewsProvider
from stock_agent.services.analysis_service import StockAnalysisService


def test_analyze_ticker_success_without_network():
    service = StockAnalysisService(
        market_data_provider=MockMarketDataProvider(),
        news_provider=MockNewsProvider(),
    )

    result = service.analyze_ticker("TCS", lookback_days=7)

    assert result.status == "SUCCESS"
    assert result.snapshot is not None
    assert result.snapshot.ticker == "TCS.NS"
    assert len(result.news) == 1
