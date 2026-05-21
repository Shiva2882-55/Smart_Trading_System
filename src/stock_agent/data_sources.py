from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as et
from time import sleep
from urllib.parse import quote_plus

import pandas as pd
import requests
import yfinance as yf

from stock_agent.config import settings
from stock_agent.models import MarketContext, NewsSignal, StockSnapshot


POSITIVE_KEYWORDS = {
    "beat",
    "surge",
    "growth",
    "upgrade",
    "strong",
    "profit",
    "record",
    "outperform",
    "bullish",
    "expand",
    "gain",
    "buyback",
    "partnership",
}

NEGATIVE_KEYWORDS = {
    "miss",
    "drop",
    "lawsuit",
    "downgrade",
    "weak",
    "loss",
    "warning",
    "cut",
    "bearish",
    "probe",
    "fraud",
    "layoff",
    "decline",
}


def validate_india_ticker(ticker: str) -> str:
    symbol = ticker.strip().upper()
    if not symbol:
        raise ValueError("Ticker cannot be empty.")

    if any(char in symbol for char in ("^", "/", "\\")):
        raise ValueError(f"{ticker} is not a valid India equity ticker.")

    if "." in symbol:
        if not symbol.endswith((".NS", ".BO")):
            raise ValueError(f"{ticker} is not an India stock ticker. Use NSE/BSE symbols only.")
        symbol = symbol.rsplit(".", 1)[0]

    if not re.fullmatch(r"[A-Z0-9&-]+", symbol):
        raise ValueError(f"{ticker} contains unsupported characters for an India ticker.")

    return symbol


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct_change(current: float | None, base: float | None) -> float:
    if current in (None, 0) or base in (None, 0):
        return 0.0
    return ((current - base) / base) * 100


def normalize_ticker(ticker: str) -> str:
    symbol = validate_india_ticker(ticker)
    return f"{symbol}{settings.default_exchange_suffix}"


def _download_history(ticker: str, period: str = "6mo"):
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            history = yf.Ticker(ticker).history(period=period, auto_adjust=True)
            if not history.empty:
                return history
            last_error = ValueError(f"No price history returned for {ticker}")
        except Exception as exc:
            last_error = exc
        sleep(1 + attempt)
    raise ValueError(f"Could not download price history for {ticker}: {last_error}")


def _annualized_volatility(history: pd.DataFrame) -> float | None:
    returns = history["Close"].pct_change().dropna()
    if returns.empty:
        return None
    return float(returns.std() * (252 ** 0.5))


def _max_drawdown(history: pd.DataFrame) -> float | None:
    if history.empty:
        return None
    running_peak = history["Close"].cummax()
    drawdown = (history["Close"] - running_peak) / running_peak
    return abs(float(drawdown.min()))


def fetch_market_context() -> MarketContext:
    generated_at = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    nifty_history = _download_history("^NSEI", period="3mo")
    banknifty_history = _download_history("^NSEBANK", period="3mo")

    spy_change = _pct_change(float(nifty_history["Close"].iloc[-1]), float(nifty_history["Close"].iloc[0]))
    qqq_change = _pct_change(float(banknifty_history["Close"].iloc[-1]), float(banknifty_history["Close"].iloc[0]))

    vix_level = None
    try:
        vix_history = yf.Ticker("^INDIAVIX").history(period="5d", auto_adjust=True)
        if not vix_history.empty:
            vix_level = float(vix_history["Close"].iloc[-1])
    except Exception:
        vix_level = None

    reasons: list[str] = []
    if spy_change > 5:
        reasons.append("Broad market trend is positive based on NIFTY 50.")
    elif spy_change < -5:
        reasons.append("Broad market trend is weak based on NIFTY 50.")

    if qqq_change > 6:
        reasons.append("Banking leadership is supportive based on Bank Nifty.")
    elif qqq_change < -6:
        reasons.append("Banking leadership is weak based on Bank Nifty.")

    risk_label = "neutral"
    if vix_level is not None:
        if vix_level >= 25:
            risk_label = "risk_off"
            reasons.append("Volatility is elevated, which raises short-term risk.")
        elif vix_level <= 16:
            risk_label = "risk_on"
            reasons.append("Volatility is calm, which supports risk appetite.")

    return MarketContext(
        spy_change_3m=round(spy_change, 2),
        qqq_change_3m=round(qqq_change, 2),
        vix_level=round(vix_level, 2) if vix_level is not None else None,
        risk_label=risk_label,
        reasons=reasons,
        generated_at=generated_at,
    )


def fetch_google_news(ticker: str, lookback_days: int) -> list[NewsSignal]:
    base_symbol = ticker.replace(".NS", "").replace(".BO", "")
    query = quote_plus(f"{base_symbol} stock india when:{lookback_days}d")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    response = None
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.get(
                url,
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0 StockResearchAgent/1.0"},
            )
            response.raise_for_status()
            break
        except Exception as exc:
            last_error = exc
            sleep(1 + attempt)
    if response is None:
        raise RuntimeError(f"Could not fetch news for {ticker}: {last_error}")

    root = et.fromstring(response.text)
    items = root.findall(".//item")[:8]
    signals: list[NewsSignal] = []

    for item in items:
        title = (item.findtext("title") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        source = (item.findtext("source") or "Unknown").strip()
        normalized = re.sub(r"[^a-zA-Z\s]", " ", title.lower())
        words = set(normalized.split())
        sentiment = 0.0
        sentiment += 0.18 * len(words & POSITIVE_KEYWORDS)
        sentiment -= 0.18 * len(words & NEGATIVE_KEYWORDS)
        age_hours = None
        try:
            published_at = dt.datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=dt.timezone.utc)
            age_hours = (dt.datetime.now(dt.timezone.utc) - published_at).total_seconds() / 3600
        except ValueError:
            age_hours = None
        signals.append(
            NewsSignal(
                headline=title,
                source=source,
                published=pub_date,
                sentiment_score=round(sentiment, 2),
                age_hours=round(age_hours, 2) if age_hours is not None else None,
            )
        )

    return signals


def fetch_stock_snapshot(ticker: str, lookback_days: int) -> StockSnapshot:
    normalized_ticker = normalize_ticker(ticker)
    stock = yf.Ticker(normalized_ticker)
    history = _download_history(normalized_ticker, period="6mo")

    info = {}
    try:
        info = stock.info
    except Exception:
        info = {}

    last_close = float(history["Close"].iloc[-1])
    close_3m = float(history["Close"].iloc[max(0, len(history) - 63)])
    close_6m = float(history["Close"].iloc[0])

    try:
        news = fetch_google_news(normalized_ticker, lookback_days)
    except Exception:
        news = []

    return StockSnapshot(
        ticker=normalized_ticker.upper(),
        sector=str(info.get("sector") or "Unknown"),
        company_name=str(info.get("shortName") or normalized_ticker.upper()),
        current_price=round(last_close, 2),
        change_percent_3m=round(_pct_change(last_close, close_3m), 2),
        change_percent_6m=round(_pct_change(last_close, close_6m), 2),
        revenue_growth=_safe_float(info.get("revenueGrowth")),
        earnings_growth=_safe_float(info.get("earningsGrowth")),
        profit_margin=_safe_float(info.get("profitMargins")),
        return_on_equity=_safe_float(info.get("returnOnEquity")),
        forward_pe=_safe_float(info.get("forwardPE")),
        debt_to_equity=_safe_float(info.get("debtToEquity")),
        trailing_eps=_safe_float(info.get("trailingEps")),
        average_volume=_safe_float(info.get("averageVolume")),
        market_cap=_safe_float(info.get("marketCap")),
        annualized_volatility=_annualized_volatility(history),
        max_drawdown_6m=_max_drawdown(history),
        news=news,
    )
