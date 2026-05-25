from __future__ import annotations

import re

import pandas as pd

from stock_agent.config import get_settings


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


def normalize_ticker(ticker: str) -> str:
    symbol = validate_india_ticker(ticker)
    return f"{symbol}{get_settings().default_exchange_suffix}"


def safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pct_change(current: float | None, base: float | None) -> float:
    if current in (None, 0) or base in (None, 0):
        return 0.0
    return ((current - base) / base) * 100


def annualized_volatility(history: pd.DataFrame) -> float | None:
    returns = history["Close"].pct_change().dropna()
    if returns.empty:
        return None
    return float(returns.std() * (252 ** 0.5))


def max_drawdown(history: pd.DataFrame) -> float | None:
    if history.empty:
        return None
    running_peak = history["Close"].cummax()
    drawdown = (history["Close"] - running_peak) / running_peak
    return abs(float(drawdown.min()))
