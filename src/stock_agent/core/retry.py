from __future__ import annotations

import random
import logging
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

from stock_agent.core.exceptions import NonRetryableProviderError, RetryableProviderError
from stock_agent.core.logging import get_current_retry_attempt, get_current_run_id, log_context
from stock_agent.persistence.run_repository import RunRepository


logger = logging.getLogger(__name__)
run_repository = RunRepository()

T = TypeVar("T")


@dataclass(slots=True)
class RetryConfig:
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 10.0
    jitter_seconds: float = 0.5


def calculate_backoff_delay(attempt: int, config: RetryConfig) -> float:
    delay = config.base_delay_seconds * (2 ** (attempt - 1))
    delay = min(delay, config.max_delay_seconds)
    jitter = random.uniform(0, config.jitter_seconds)
    return round(delay + jitter, 2)


def run_with_retry(
    operation: Callable[[], T],
    operation_name: str = "external_operation",
    provider: str = "unknown_provider",
    ticker: str | None = None,
    config: RetryConfig | None = None,
) -> T:
    """Run an operation with centralized retry classification and backoff."""

    retry_config = config or RetryConfig()

    last_exception: Exception | None = None

    for attempt in range(1, retry_config.max_attempts + 1):
        with log_context(retry_attempt=attempt, provider=provider, ticker=ticker):
            start_time = time.perf_counter()
            logger.info(
                "retry_attempt_started",
                extra={
                    "event": "retry_attempt_started",
                    "operation": operation_name,
                    "provider": provider,
                    "ticker": ticker,
                    "attempt": attempt,
                    "max_attempts": retry_config.max_attempts,
                },
            )
            try:
                result = operation()
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                logger.info(
                    "retry_attempt_success",
                    extra={
                        "event": "retry_attempt_success",
                        "operation": operation_name,
                        "provider": provider,
                        "ticker": ticker,
                        "attempt": attempt,
                        "max_attempts": retry_config.max_attempts,
                        "latency_ms": latency_ms,
                    },
                )
                return result
            except NonRetryableProviderError as exc:
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                _record_provider_error(
                    provider=provider,
                    ticker=ticker,
                    operation=operation_name,
                    error=exc,
                    retry_attempt=attempt,
                )
                logger.error(
                    "non_retryable_error",
                    extra={
                        "event": "non_retryable_error",
                        "operation": operation_name,
                        "provider": provider,
                        "ticker": ticker,
                        "attempt": attempt,
                        "latency_ms": latency_ms,
                        "error_type": type(exc).__name__,
                        "failure_reason": str(exc),
                    },
                )
                raise
            except RetryableProviderError as exc:
                last_exception = exc
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                if attempt >= retry_config.max_attempts:
                    _record_provider_error(
                        provider=provider,
                        ticker=ticker,
                        operation=operation_name,
                        error=exc,
                        retry_attempt=attempt,
                    )
                    logger.exception(
                        "retry_failed_final",
                        extra={
                            "event": "retry_failed_final",
                            "operation": operation_name,
                            "provider": provider,
                            "ticker": ticker,
                            "attempt": attempt,
                            "max_attempts": retry_config.max_attempts,
                            "latency_ms": latency_ms,
                            "error_type": type(exc).__name__,
                            "failure_reason": str(exc),
                        },
                    )
                    raise

                sleep_seconds = calculate_backoff_delay(attempt, retry_config)
                logger.warning(
                    "retryable_error_will_retry",
                    extra={
                        "event": "retryable_error_will_retry",
                        "operation": operation_name,
                        "provider": provider,
                        "ticker": ticker,
                        "attempt": attempt,
                        "max_attempts": retry_config.max_attempts,
                        "latency_ms": latency_ms,
                        "error_type": type(exc).__name__,
                        "failure_reason": str(exc),
                        "next_retry_in_seconds": sleep_seconds,
                    },
                )
                time.sleep(sleep_seconds)
            except Exception as exc:
                last_exception = exc
                latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                if attempt >= retry_config.max_attempts:
                    _record_provider_error(
                        provider=provider,
                        ticker=ticker,
                        operation=operation_name,
                        error=exc,
                        retry_attempt=attempt,
                    )
                    logger.exception(
                        "unexpected_error_final",
                        extra={
                            "event": "unexpected_error_final",
                            "operation": operation_name,
                            "provider": provider,
                            "ticker": ticker,
                            "attempt": attempt,
                            "max_attempts": retry_config.max_attempts,
                            "latency_ms": latency_ms,
                            "error_type": type(exc).__name__,
                            "failure_reason": str(exc),
                        },
                    )
                    raise

                sleep_seconds = calculate_backoff_delay(attempt, retry_config)
                logger.warning(
                    "unexpected_error_will_retry",
                    extra={
                        "event": "unexpected_error_will_retry",
                        "operation": operation_name,
                        "provider": provider,
                        "ticker": ticker,
                        "attempt": attempt,
                        "max_attempts": retry_config.max_attempts,
                        "latency_ms": latency_ms,
                        "error_type": type(exc).__name__,
                        "failure_reason": str(exc),
                        "next_retry_in_seconds": sleep_seconds,
                    },
                )
                time.sleep(sleep_seconds)

    if last_exception is None:
        raise RuntimeError(f"Retry operation {operation_name} failed without raising an exception.")
    raise last_exception


def _record_provider_error(
    provider: str,
    ticker: str | None,
    operation: str,
    error: Exception,
    retry_attempt: int | None,
) -> None:
    run_id = get_current_run_id()
    if run_id is None:
        return
    try:
        run_repository.add_provider_error(
            run_id=run_id,
            ticker=ticker,
            provider=provider,
            operation=operation,
            error_type=type(error).__name__,
            error_message=str(error),
            retry_attempt=retry_attempt or get_current_retry_attempt(),
        )
    except Exception:
        logger.debug("provider_error_persistence_failed", exc_info=True)
