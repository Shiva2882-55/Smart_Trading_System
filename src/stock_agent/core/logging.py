from __future__ import annotations

import contextvars
import json
import logging
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4


run_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("run_id", default=None)
ticker_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("ticker", default=None)
provider_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("provider", default=None)
retry_attempt_ctx: contextvars.ContextVar[int | None] = contextvars.ContextVar("retry_attempt", default=None)


def generate_run_id(now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).strftime("RUN-%Y%m%d-%H%M%S")
    return f"{timestamp}-{uuid4().hex[:8]}"


class JsonFormatter(logging.Formatter):
    """Convert Python log records into JSON payloads."""

    _reserved_keys = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "run_id",
        "ticker",
        "provider",
        "retry_attempt",
    }

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "run_id": getattr(record, "run_id", None),
            "ticker": getattr(record, "ticker", None),
            "provider": getattr(record, "provider", None),
            "retry_attempt": getattr(record, "retry_attempt", None),
        }

        for key, value in record.__dict__.items():
            if key not in self._reserved_keys:
                log_data[key] = value

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=str)


class ContextFilter(logging.Filter):
    """Attach execution context to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = run_id_ctx.get()
        record.ticker = ticker_ctx.get()
        record.provider = provider_ctx.get()
        record.retry_attempt = retry_attempt_ctx.get()
        return True


def setup_logging(log_dir: Path | str, log_file: str, log_level: str = "INFO") -> None:
    """Configure root logging once for both console and file sinks."""

    resolved_log_dir = Path(log_dir)
    resolved_log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(log_level.upper())
    logger.handlers.clear()

    formatter = JsonFormatter()
    context_filter = ContextFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(context_filter)

    file_handler = RotatingFileHandler(
        filename=resolved_log_dir / log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(context_filter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)


def get_current_run_id() -> str | None:
    return run_id_ctx.get()


def get_current_ticker() -> str | None:
    return ticker_ctx.get()


def get_current_provider() -> str | None:
    return provider_ctx.get()


def get_current_retry_attempt() -> int | None:
    return retry_attempt_ctx.get()


@contextmanager
def log_context(
    run_id: str | None = None,
    ticker: str | None = None,
    provider: str | None = None,
    retry_attempt: int | None = None,
):
    """Temporarily attach context to all logs emitted in the current scope."""

    tokens: list[tuple[contextvars.ContextVar[object], contextvars.Token[object]]] = []

    if run_id is not None:
        tokens.append((run_id_ctx, run_id_ctx.set(run_id)))
    if ticker is not None:
        tokens.append((ticker_ctx, ticker_ctx.set(ticker)))
    if provider is not None:
        tokens.append((provider_ctx, provider_ctx.set(provider)))
    if retry_attempt is not None:
        tokens.append((retry_attempt_ctx, retry_attempt_ctx.set(retry_attempt)))

    try:
        yield
    finally:
        for ctx_var, token in reversed(tokens):
            ctx_var.reset(token)
