from __future__ import annotations

from datetime import datetime, timedelta

from stock_agent.models import MarketContext, Recommendation, StockSnapshot


def _scaled_score(value: float, low: float, high: float) -> float:
    if value <= low:
        return 0.0
    if value >= high:
        return 1.0
    return (value - low) / (high - low)


def _average_news_sentiment(snapshot: StockSnapshot) -> float:
    if not snapshot.news:
        return 0.0
    return sum(item.sentiment_score for item in snapshot.news) / len(snapshot.news)


def _sentiment_trend(snapshot: StockSnapshot) -> float:
    if not snapshot.news:
        return 0.0

    weighted_total = 0.0
    weight_sum = 0.0
    for item in snapshot.news:
        age_hours = item.age_hours if item.age_hours is not None else 72.0
        weight = 1 / max(age_hours + 1, 1)
        weighted_total += item.sentiment_score * weight
        weight_sum += weight

    if weight_sum == 0:
        return 0.0
    return weighted_total / weight_sum


def _risk_score(snapshot: StockSnapshot) -> float:
    volatility = snapshot.annualized_volatility or 0.0
    drawdown = snapshot.max_drawdown_6m or 0.0
    volatility_component = 50 * _scaled_score(volatility, 0.15, 0.75)
    drawdown_component = 50 * _scaled_score(drawdown, 0.05, 0.45)
    return round(volatility_component + drawdown_component, 2)


def _build_signal(score: float) -> str:
    if score >= 70:
        return "BUY"
    if score <= 40:
        return "SELL"
    return "HOLD"


def _compute_trade_levels(snapshot: StockSnapshot, action: str) -> tuple[float, float, float, str]:
    current_price = snapshot.current_price
    volatility = snapshot.annualized_volatility or 0.22
    drawdown = snapshot.max_drawdown_6m or 0.10
    base_risk_pct = max(0.04, min(0.12, 0.03 + (volatility * 0.08) + (drawdown * 0.10)))

    if action == "BUY_NOW":
        entry_price = current_price
        stop_loss = current_price * (1 - base_risk_pct)
        take_profit = current_price * (1 + (base_risk_pct * 2.0))
        note = "Full position allowed only if risk stays within your plan."
    elif action == "BUY_ON_DIP":
        entry_price = current_price * (1 - min(base_risk_pct * 0.35, 0.03))
        stop_loss = entry_price * (1 - base_risk_pct)
        take_profit = entry_price * (1 + (base_risk_pct * 2.2))
        note = "Consider staggered entries on dips instead of chasing strength."
    elif action == "WATCHLIST":
        entry_price = current_price * 0.99
        stop_loss = entry_price * (1 - base_risk_pct)
        take_profit = entry_price * (1 + (base_risk_pct * 1.8))
        note = "Wait for better confirmation before taking size."
    else:
        entry_price = current_price
        stop_loss = current_price * (1 + base_risk_pct)
        take_profit = current_price * (1 - (base_risk_pct * 1.5))
        note = "Avoid fresh long exposure until the setup improves."

    return round(entry_price, 2), round(stop_loss, 2), round(take_profit, 2), note


def _confidence_score(score: float, risk_score: float, sentiment_trend: float, market: MarketContext) -> float:
    score_component = _scaled_score(score, 35, 85) * 55
    risk_component = (1 - _scaled_score(risk_score, 20, 85)) * 25
    sentiment_component = _scaled_score(sentiment_trend, -0.20, 0.20) * 10
    market_component = 10.0
    if market.risk_label == "risk_off":
        market_component = 4.0
    elif market.risk_label == "risk_on":
        market_component = 10.0
    return round(max(0.0, min(100.0, score_component + risk_component + sentiment_component + market_component)), 2)


def _build_action(
    signal: str,
    score: float,
    market: MarketContext,
    sentiment_trend: float,
    risk_score: float,
    momentum_3m: float,
) -> tuple[str, str]:
    if signal == "BUY" and market.risk_label != "risk_off" and risk_score <= 48 and sentiment_trend >= -0.02:
        if momentum_3m >= 5:
            return "BUY_NOW", "Immediate entry favored while trend, risk, and sentiment remain supportive."
        return "BUY_ON_DIP", "Bullish setup, but a pullback entry would improve risk-reward."
    if signal == "SELL" and (risk_score >= 55 or momentum_3m < -8):
        return "SELL_NOW", "Exit or reduce exposure on the current weak setup."
    if score >= 58:
        return "WATCHLIST", "Wait for confirmation or a better entry."
    return "AVOID", "Do not add new exposure until the setup improves."


def score_stock(snapshot: StockSnapshot, market: MarketContext, sector_relative_strength: float = 0.0) -> Recommendation:
    reasons: list[str] = []

    momentum_score = 12 * _scaled_score(snapshot.change_percent_3m, -15, 25)
    if snapshot.change_percent_3m > 10:
        reasons.append(f"Strong 3-month momentum at {snapshot.change_percent_3m:.2f}%.")
    elif snapshot.change_percent_3m < -10:
        reasons.append(f"Weak 3-month momentum at {snapshot.change_percent_3m:.2f}%.")

    valuation_component = 0.0
    if snapshot.forward_pe is not None:
        valuation_component = 10 * (1 - _scaled_score(snapshot.forward_pe, 12, 40))
        if snapshot.forward_pe < 20:
            reasons.append(f"Forward P/E looks reasonable at {snapshot.forward_pe:.2f}.")
        elif snapshot.forward_pe > 35:
            reasons.append(f"Forward P/E is stretched at {snapshot.forward_pe:.2f}.")

    quality_component = 0.0
    if snapshot.profit_margin is not None:
        quality_component += 6 * _scaled_score(snapshot.profit_margin, 0.02, 0.30)
    if snapshot.return_on_equity is not None:
        quality_component += 6 * _scaled_score(snapshot.return_on_equity, 0.05, 0.35)
    if snapshot.debt_to_equity is not None:
        quality_component += 4 * (1 - _scaled_score(snapshot.debt_to_equity, 40, 220))
        if snapshot.debt_to_equity > 180:
            reasons.append(f"Balance sheet leverage is high with debt/equity at {snapshot.debt_to_equity:.2f}.")

    growth_component = 0.0
    if snapshot.revenue_growth is not None:
        growth_component += 8 * _scaled_score(snapshot.revenue_growth, -0.05, 0.30)
    if snapshot.earnings_growth is not None:
        growth_component += 8 * _scaled_score(snapshot.earnings_growth, -0.10, 0.35)
        if snapshot.earnings_growth > 0.15:
            reasons.append("Earnings growth is supportive.")
        elif snapshot.earnings_growth < 0:
            reasons.append("Earnings growth is negative.")

    news_sentiment = _average_news_sentiment(snapshot)
    sentiment_trend = _sentiment_trend(snapshot)
    news_component = 10 * _scaled_score(news_sentiment, -0.35, 0.35)
    sentiment_trend_component = 8 * _scaled_score(sentiment_trend, -0.35, 0.35)
    if news_sentiment > 0.10:
        reasons.append("Recent news flow leans positive.")
    elif news_sentiment < -0.10:
        reasons.append("Recent news flow leans negative.")
    if sentiment_trend > 0.08:
        reasons.append("News sentiment trend is improving.")
    elif sentiment_trend < -0.08:
        reasons.append("News sentiment trend is deteriorating.")

    sector_component = 10 * _scaled_score(sector_relative_strength, -15, 15)
    if sector_relative_strength > 4:
        reasons.append(f"Sector rotation is supportive with relative strength at {sector_relative_strength:.2f}%.")
    elif sector_relative_strength < -4:
        reasons.append(f"Sector rotation is weak with relative strength at {sector_relative_strength:.2f}%.")

    risk_score = _risk_score(snapshot)
    risk_penalty = 12 * _scaled_score(risk_score, 20, 85)
    if risk_score > 65:
        reasons.append(f"Risk profile is elevated with risk score {risk_score:.2f}.")

    market_component = 12.0
    if market.risk_label == "risk_on":
        market_component += 4
    elif market.risk_label == "risk_off":
        market_component -= 4

    raw_score = (
        momentum_score
        + valuation_component
        + quality_component
        + growth_component
        + news_component
        + sentiment_trend_component
        + sector_component
        + market_component
        - risk_penalty
    )
    score = max(0.0, min(100.0, raw_score))

    if not reasons:
        reasons.append("Signal is mostly neutral with mixed underlying factors.")

    generated_at = market.generated_at
    signal = _build_signal(score)
    action, action_reason = _build_action(
        signal,
        score,
        market,
        sentiment_trend,
        risk_score,
        snapshot.change_percent_3m,
    )
    if action_reason not in reasons:
        reasons.append(action_reason)
    action_timestamp = generated_at
    review_timestamp = (datetime.fromisoformat(generated_at) + timedelta(days=3)).isoformat(timespec="seconds")
    entry_price, stop_loss, take_profit, position_size_note = _compute_trade_levels(snapshot, action)
    confidence_score = _confidence_score(score, risk_score, sentiment_trend, market)

    return Recommendation(
        ticker=snapshot.ticker,
        company_name=snapshot.company_name,
        sector=snapshot.sector,
        score=round(score, 2),
        confidence_score=confidence_score,
        signal=signal,
        reasons=reasons,
        snapshot=snapshot,
        risk_score=risk_score,
        sentiment_trend=round(sentiment_trend, 3),
        sector_relative_strength=round(sector_relative_strength, 2),
        generated_at=generated_at,
        action=action,
        action_timestamp=action_timestamp,
        review_timestamp=review_timestamp,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        position_size_note=position_size_note,
    )
