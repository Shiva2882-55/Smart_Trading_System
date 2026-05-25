from __future__ import annotations


class StockAgentError(Exception):
    """Base exception for stock agent runtime failures."""


class ProviderError(StockAgentError):
    """Base exception for external provider failures."""


class RetryableProviderError(ProviderError):
    """Temporary provider error that should be retried."""


class NonRetryableProviderError(ProviderError):
    """Permanent provider error that should fail fast."""


class ProviderTimeoutError(RetryableProviderError):
    """Provider request timed out."""


class ProviderRateLimitError(RetryableProviderError):
    """Provider rate limit reached."""


class EmptyDataError(NonRetryableProviderError):
    """Provider returned empty or unusable data."""


class InvalidTickerError(NonRetryableProviderError):
    """Ticker is invalid or unsupported."""
