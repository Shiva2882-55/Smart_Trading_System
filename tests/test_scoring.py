from stock_agent.models import MarketContext, StockSnapshot
from stock_agent.scoring import score_stock


def test_score_stock_buy_signal_for_strong_profile():
    snapshot = StockSnapshot(
        ticker="TEST",
        sector="Technology",
        company_name="Test Corp",
        current_price=100.0,
        change_percent_3m=18.0,
        change_percent_6m=32.0,
        revenue_growth=0.22,
        earnings_growth=0.24,
        profit_margin=0.26,
        return_on_equity=0.31,
        forward_pe=18.0,
        debt_to_equity=30.0,
        trailing_eps=4.5,
        average_volume=1_000_000,
        market_cap=50_000_000_000,
        annualized_volatility=0.18,
        max_drawdown_6m=0.08,
        news=[],
    )
    market = MarketContext(
        spy_change_3m=8.0,
        qqq_change_3m=10.0,
        vix_level=14.0,
        risk_label="risk_on",
        reasons=[],
        generated_at="2026-04-28T10:00:00+05:30",
    )

    recommendation = score_stock(snapshot, market, sector_relative_strength=6.0)

    assert recommendation.signal == "BUY"
    assert recommendation.score >= 70
    assert recommendation.action == "BUY_NOW"
    assert recommendation.entry_price > 0
    assert recommendation.stop_loss < recommendation.entry_price
    assert recommendation.take_profit > recommendation.entry_price
    assert recommendation.confidence_score > 0
