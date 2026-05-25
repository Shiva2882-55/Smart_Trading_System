from __future__ import annotations

import datetime as dt
import logging
import re
import socket
import time
import xml.etree.ElementTree as et
from urllib.parse import quote_plus

import requests

from stock_agent.config import get_settings
from stock_agent.core.exceptions import ProviderRateLimitError, ProviderTimeoutError, RetryableProviderError
from stock_agent.core.logging import log_context
from stock_agent.core.retry import RetryConfig, run_with_retry
from stock_agent.models import NewsSignal
from stock_agent.provider_utils import NEGATIVE_KEYWORDS, POSITIVE_KEYWORDS
from stock_agent.providers.base import NewsProvider


logger = logging.getLogger(__name__)


class GoogleNewsProvider(NewsProvider):
    provider_name = "google_news"

    def __init__(self) -> None:
        self.last_provider_issues = []

    def get_news(self, ticker: str, lookback_days: int) -> list[NewsSignal]:
        settings = get_settings()
        self.last_provider_issues = []
        base_symbol = ticker.replace(".NS", "").replace(".BO", "")
        query = quote_plus(f"{base_symbol} stock india when:{lookback_days}d")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"

        with log_context(provider=self.provider_name):
            start_time = time.perf_counter()
            logger.info(
                "news_fetch_started",
                extra={"event": "news_fetch_started", "lookback_days": lookback_days},
            )

            response = run_with_retry(
                operation=lambda: self._fetch_news_response(url, ticker),
                operation_name=f"fetch_google_news:{ticker}",
                provider=self.provider_name,
                ticker=ticker,
                config=self._retry_config(),
            )

            try:
                root = et.fromstring(response.text)
            except et.ParseError as exc:
                logger.exception(
                    "news_fetch_failed",
                    extra={
                        "event": "news_fetch_failed",
                        "status": "FAILED",
                        "error_type": type(exc).__name__,
                        "failure_reason": str(exc),
                    },
                )
                raise RuntimeError(f"Received malformed Google News RSS for {ticker}: {exc}") from exc

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

            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.info(
                "news_fetch_success",
                extra={
                    "event": "news_fetch_success",
                    "status": "SUCCESS",
                    "latency_ms": latency_ms,
                    "articles": len(signals),
                },
            )
            return signals

    def _fetch_news_response(self, url: str, ticker: str):
        settings = get_settings()
        try:
            response = requests.get(
                url,
                timeout=settings.request_timeout_seconds,
                headers={"User-Agent": "Mozilla/5.0 StockResearchAgent/1.0"},
            )
            response.raise_for_status()
            return response
        except (TimeoutError, socket.timeout, requests.exceptions.Timeout) as exc:
            raise ProviderTimeoutError(f"Timeout while fetching Google News for {ticker}") from exc
        except requests.exceptions.HTTPError as exc:
            status_code = getattr(exc.response, "status_code", None)
            if status_code == 429:
                raise ProviderRateLimitError(f"Rate limit while fetching Google News for {ticker}") from exc
            raise RetryableProviderError(f"HTTP error while fetching Google News for {ticker}") from exc
        except (ConnectionError, requests.exceptions.ConnectionError) as exc:
            raise RetryableProviderError(f"Connection error while fetching Google News for {ticker}") from exc

    def _retry_config(self) -> RetryConfig:
        settings = get_settings()
        return RetryConfig(
            max_attempts=settings.request_retry_attempts,
            base_delay_seconds=settings.request_base_delay_seconds,
            max_delay_seconds=settings.request_max_delay_seconds,
            jitter_seconds=settings.request_jitter_seconds,
        )
