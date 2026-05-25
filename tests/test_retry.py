import logging

import pytest

from stock_agent.core.exceptions import InvalidTickerError, ProviderTimeoutError
from stock_agent.core.retry import RetryConfig, calculate_backoff_delay, run_with_retry


def test_run_with_retry_retries_until_success(monkeypatch, caplog):
    attempts = {"count": 0}
    monkeypatch.setattr("stock_agent.core.retry.time.sleep", lambda _: None)
    monkeypatch.setattr("stock_agent.core.retry.random.uniform", lambda _a, _b: 0.0)

    def operation():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ProviderTimeoutError("temporary timeout")
        return "ok"

    with caplog.at_level(logging.INFO):
        result = run_with_retry(
            operation=operation,
            operation_name="fetch_yfinance_market_data",
            provider="yfinance",
            ticker="TCS.NS",
            config=RetryConfig(max_attempts=3, base_delay_seconds=0.01, max_delay_seconds=0.1, jitter_seconds=0.0),
        )

    assert result == "ok"
    assert attempts["count"] == 3
    assert any(record.msg == "retryable_error_will_retry" for record in caplog.records)
    assert any(record.msg == "retry_attempt_success" for record in caplog.records)


def test_run_with_retry_raises_after_final_retryable_attempt(monkeypatch):
    monkeypatch.setattr("stock_agent.core.retry.time.sleep", lambda _: None)
    monkeypatch.setattr("stock_agent.core.retry.random.uniform", lambda _a, _b: 0.0)

    with pytest.raises(ProviderTimeoutError):
        run_with_retry(
            operation=lambda: (_ for _ in ()).throw(ProviderTimeoutError("network down")),
            operation_name="fetch_google_news",
            provider="google_news",
            ticker="INFY.NS",
            config=RetryConfig(max_attempts=2, base_delay_seconds=0.01, max_delay_seconds=0.1, jitter_seconds=0.0),
        )


def test_run_with_retry_fails_fast_for_non_retryable_error(monkeypatch, caplog):
    monkeypatch.setattr("stock_agent.core.retry.time.sleep", lambda _: None)

    with caplog.at_level(logging.INFO), pytest.raises(InvalidTickerError):
        run_with_retry(
            operation=lambda: (_ for _ in ()).throw(InvalidTickerError("invalid ticker")),
            operation_name="fetch_yfinance_market_data",
            provider="yfinance",
            ticker="BAD.NS",
            config=RetryConfig(max_attempts=3, base_delay_seconds=0.01, max_delay_seconds=0.1, jitter_seconds=0.0),
        )

    assert any(record.msg == "non_retryable_error" for record in caplog.records)
    assert not any(record.msg == "retryable_error_will_retry" for record in caplog.records)


def test_calculate_backoff_delay_uses_cap_and_jitter(monkeypatch):
    monkeypatch.setattr("stock_agent.core.retry.random.uniform", lambda _a, _b: 0.25)

    delay = calculate_backoff_delay(
        attempt=4,
        config=RetryConfig(base_delay_seconds=1.0, max_delay_seconds=5.0, jitter_seconds=0.5),
    )

    assert delay == 5.25
