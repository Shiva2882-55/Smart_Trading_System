from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class NewsSignal:
    headline: str
    source: str
    published: str
    sentiment_score: float
    age_hours: float | None = None


@dataclass(slots=True)
class StockSnapshot:
    ticker: str
    sector: str
    company_name: str
    current_price: float
    change_percent_3m: float
    change_percent_6m: float
    revenue_growth: float | None
    earnings_growth: float | None
    profit_margin: float | None
    return_on_equity: float | None
    forward_pe: float | None
    debt_to_equity: float | None
    trailing_eps: float | None
    average_volume: float | None
    market_cap: float | None
    annualized_volatility: float | None
    max_drawdown_6m: float | None
    news: list[NewsSignal] = field(default_factory=list)


@dataclass(slots=True)
class MarketContext:
    spy_change_3m: float
    qqq_change_3m: float
    vix_level: float | None
    risk_label: str
    reasons: list[str]
    generated_at: str


@dataclass(slots=True)
class Recommendation:
    ticker: str
    company_name: str
    sector: str
    score: float
    confidence_score: float
    signal: str
    reasons: list[str]
    snapshot: StockSnapshot
    risk_score: float
    sentiment_trend: float
    sector_relative_strength: float
    generated_at: str
    action: str
    action_timestamp: str
    review_timestamp: str
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size_note: str
