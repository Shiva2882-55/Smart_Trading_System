from __future__ import annotations

import datetime as dt
import logging
import socket
import time

import pandas as pd
import requests
import yfinance as yf

from stock_agent.config import get_settings
from stock_agent.core.exceptions import EmptyDataError, InvalidTickerError, ProviderRateLimitError, ProviderTimeoutError, RetryableProviderError
from stock_agent.core.logging import log_context
from stock_agent.core.retry import RetryConfig, run_with_retry
from stock_agent.models import MarketContext, StockSnapshot
from stock_agent.provider_utils import annualized_volatility, max_drawdown, normalize_ticker, pct_change, safe_float
from stock_agent.providers.base import MarketDataProvider


logger = logging.getLogger(__name__)


class YFinanceMarketDataProvider(MarketDataProvider):
    provider_name = "yfinance"

    def __init__(self) -> None:
        self.last_provider_issues = []

    def get_market_context(self) -> MarketContext:
        settings = get_settings()
        self.last_provider_issues = []
        generated_at = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
        with log_context(provider=self.provider_name):
            start_time = time.perf_counter()
            logger.info(
                "market_data_fetch_started",
                extra={"event": "market_data_fetch_started", "target": "market_context"},
            )
            nifty_history = self._download_history("^NSEI", period="3mo")
            banknifty_history = self._download_history("^NSEBANK", period="3mo")

            spy_change = pct_change(float(nifty_history["Close"].iloc[-1]), float(nifty_history["Close"].iloc[0]))
            qqq_change = pct_change(float(banknifty_history["Close"].iloc[-1]), float(banknifty_history["Close"].iloc[0]))

            vix_level = None
            try:
                vix_history = self._download_history("^INDIAVIX", period="5d")
                if not vix_history.empty:
                    vix_level = float(vix_history["Close"].iloc[-1])
            except Exception as exc:
                logger.warning(
                    "market_data_fetch_failed",
                    extra={
                        "event": "market_data_fetch_failed",
                        "target": "india_vix",
                        "status": "FAILED",
                        "error_type": type(exc).__name__,
                        "failure_reason": str(exc),
                    },
                )

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

            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.info(
                "market_data_fetch_success",
                extra={
                    "event": "market_data_fetch_success",
                    "target": "market_context",
                    "status": "SUCCESS",
                    "latency_ms": latency_ms,
                },
            )

        return MarketContext(
            spy_change_3m=round(spy_change, 2),
            qqq_change_3m=round(qqq_change, 2),
            vix_level=round(vix_level, 2) if vix_level is not None else None,
            risk_label=risk_label,
            reasons=reasons,
            generated_at=generated_at,
        )

    def get_stock_snapshot(self, ticker: str) -> StockSnapshot:
        settings = get_settings()
        self.last_provider_issues = []
        normalized_ticker = normalize_ticker(ticker)
        with log_context(ticker=normalized_ticker, provider=self.provider_name):
            start_time = time.perf_counter()
            logger.info(
                "market_data_fetch_started",
                extra={"event": "market_data_fetch_started", "target": "stock_snapshot"},
            )
            stock = yf.Ticker(normalized_ticker)
            history = self._download_history(normalized_ticker, period="6mo")

            info = {}
            try:
                info = run_with_retry(
                    operation=lambda: self._fetch_stock_info(stock, normalized_ticker),
                    operation_name=f"fetch_stock_info:{normalized_ticker}",
                    provider=self.provider_name,
                    ticker=normalized_ticker,
                    config=self._retry_config(max_delay_seconds=settings.request_max_delay_seconds),
                )
            except Exception as exc:
                logger.warning(
                    "market_data_fetch_failed",
                    extra={
                        "event": "market_data_fetch_failed",
                        "target": "stock_info",
                        "status": "FAILED",
                        "error_type": type(exc).__name__,
                        "failure_reason": str(exc),
                    },
                )

            last_close = float(history["Close"].iloc[-1])
            close_3m = float(history["Close"].iloc[max(0, len(history) - 63)])
            close_6m = float(history["Close"].iloc[0])

            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.info(
                "market_data_fetch_success",
                extra={
                    "event": "market_data_fetch_success",
                    "target": "stock_snapshot",
                    "status": "SUCCESS",
                    "latency_ms": latency_ms,
                    "rows": len(history),
                },
            )

        return StockSnapshot(
            ticker=normalized_ticker.upper(),
            sector=str(info.get("sector") or "Unknown"),
            company_name=str(info.get("shortName") or normalized_ticker.upper()),
            current_price=round(last_close, 2),
            change_percent_3m=round(pct_change(last_close, close_3m), 2),
            change_percent_6m=round(pct_change(last_close, close_6m), 2),
            revenue_growth=safe_float(info.get("revenueGrowth")),
            earnings_growth=safe_float(info.get("earningsGrowth")),
            profit_margin=safe_float(info.get("profitMargins")),
            return_on_equity=safe_float(info.get("returnOnEquity")),
            forward_pe=safe_float(info.get("forwardPE")),
            debt_to_equity=safe_float(info.get("debtToEquity")),
            trailing_eps=safe_float(info.get("trailingEps")),
            average_volume=safe_float(info.get("averageVolume")),
            market_cap=safe_float(info.get("marketCap")),
            annualized_volatility=annualized_volatility(history),
            max_drawdown_6m=max_drawdown(history),
            source=self.provider_name,
            news=[],
        )

    def _download_history(self, ticker: str, period: str) -> pd.DataFrame:
        settings = get_settings()
        return run_with_retry(
            operation=lambda: self._fetch_history(ticker, period),
            operation_name=f"download_price_history:{ticker}:{period}",
            provider=self.provider_name,
            ticker=ticker,
            config=self._retry_config(max_delay_seconds=settings.request_max_delay_seconds),
        )

    def _fetch_history(self, ticker: str, period: str) -> pd.DataFrame:
        try:
            history = yf.Ticker(ticker).history(period=period, auto_adjust=True)
        except (TimeoutError, socket.timeout, requests.exceptions.Timeout) as exc:
            raise ProviderTimeoutError(f"Timeout while fetching yfinance data for {ticker}") from exc
        except requests.exceptions.HTTPError as exc:
            status_code = getattr(exc.response, "status_code", None)
            if status_code == 429:
                raise ProviderRateLimitError(f"Rate limit while fetching yfinance data for {ticker}") from exc
            if status_code is not None and 400 <= status_code < 500:
                raise InvalidTickerError(f"Invalid request or ticker for yfinance data: {ticker}") from exc
            raise RetryableProviderError(f"HTTP error while fetching yfinance data for {ticker}") from exc
        except (ConnectionError, requests.exceptions.ConnectionError) as exc:
            raise RetryableProviderError(f"Connection error while fetching yfinance data for {ticker}") from exc
        except Exception as exc:
            message = str(exc).lower()
            if "rate limit" in message or "too many requests" in message:
                raise ProviderRateLimitError(f"Rate limit while fetching yfinance data for {ticker}") from exc
            if "invalid" in message or "not found" in message:
                raise InvalidTickerError(f"Invalid ticker for yfinance data: {ticker}") from exc
            raise

        if history.empty:
            raise EmptyDataError(f"No price history returned for {ticker}")
        return history

    def _fetch_stock_info(self, stock: yf.Ticker, ticker: str) -> dict:
        try:
            return stock.info
        except (TimeoutError, socket.timeout, requests.exceptions.Timeout) as exc:
            raise ProviderTimeoutError(f"Timeout while fetching stock info for {ticker}") from exc
        except requests.exceptions.HTTPError as exc:
            status_code = getattr(exc.response, "status_code", None)
            if status_code == 429:
                raise ProviderRateLimitError(f"Rate limit while fetching stock info for {ticker}") from exc
            if status_code is not None and 400 <= status_code < 500:
                raise InvalidTickerError(f"Invalid ticker for stock info lookup: {ticker}") from exc
            raise RetryableProviderError(f"HTTP error while fetching stock info for {ticker}") from exc
        except (ConnectionError, requests.exceptions.ConnectionError) as exc:
            raise RetryableProviderError(f"Connection error while fetching stock info for {ticker}") from exc

    def _retry_config(self, max_delay_seconds: float) -> RetryConfig:
        settings = get_settings()
        return RetryConfig(
            max_attempts=settings.request_retry_attempts,
            base_delay_seconds=settings.request_base_delay_seconds,
            max_delay_seconds=max_delay_seconds,
            jitter_seconds=settings.request_jitter_seconds,
        )
