from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[2]
KOLKATA_TZ = ZoneInfo("Asia/Kolkata")


class Settings(BaseSettings):
    """Central validated runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = Field(default="Trading Stock Prediction")
    environment: Literal["local", "dev", "qa", "uat", "prod"] = "local"

    default_universe: Path = Field(default=Path("watchlists/core_watchlist.txt"))
    report_output_dir: Path = Field(default=Path("."))
    log_dir: Path = Field(default=Path("logs"))
    database_path: Path = Field(default=Path("data/stock_agent.db"))
    lock_file: Path = Field(default=Path("data/stock_agent.lock"))
    database_backend: Literal["sqlite", "postgres"] = "sqlite"
    database_name: str = Field(default="stock_agent")
    database_host: str = Field(default="localhost")
    database_port: int = Field(default=5432, ge=1, le=65535)
    database_user: str = Field(default="postgres")
    database_password: str | None = None
    database_schema: str = Field(default="trading_stock")

    market_provider: Literal["yfinance", "mock", "fallback"] = "yfinance"
    news_provider: Literal["google_news", "mock", "fallback"] = "google_news"

    news_lookback_days: int = Field(default=7, ge=1, le=30)
    top_n: int = Field(default=10, ge=1, le=100)
    default_exchange_suffix: str = ".NS"
    yfinance_period: str = Field(default="6mo")
    news_limit: int = Field(default=8, ge=1, le=20)

    request_timeout_seconds: float = Field(default=20.0, gt=0, le=300)
    request_retry_attempts: int = Field(default=3, ge=1, le=10)
    request_base_delay_seconds: float = Field(default=1.0, gt=0, le=30)
    request_max_delay_seconds: float = Field(default=8.0, gt=0, le=120)
    request_jitter_seconds: float = Field(default=0.5, ge=0, le=30)
    lock_stale_after_seconds: int = Field(default=21600, ge=60, le=86400)

    report_basename: str = Field(default="stock_analysis", min_length=1)
    log_file: str = Field(default="stock_agent.log", min_length=1)
    log_level: str = Field(default="INFO", min_length=1)

    enable_excel_report: bool = True
    enable_sqlite_history: bool = True
    enable_graceful_degradation: bool = True
    alpha_vantage_api_key: str | None = None
    twelve_data_api_key: str | None = None
    finnhub_api_key: str | None = None
    marketaux_api_key: str | None = None
    newsapi_api_key: str | None = None

    @field_validator("default_universe", "report_output_dir", "log_dir", "database_path", "lock_file", mode="before")
    @classmethod
    def _coerce_path(cls, value: str | Path) -> Path:
        return Path(value)

    @field_validator("yfinance_period")
    @classmethod
    def validate_yfinance_period(cls, value: str) -> str:
        allowed_periods = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}
        if value not in allowed_periods:
            raise ValueError(f"Invalid YFINANCE_PERIOD='{value}'. Allowed values: {sorted(allowed_periods)}")
        return value

    @field_validator("database_schema")
    @classmethod
    def validate_database_schema(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("DATABASE_SCHEMA cannot be empty")
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
        if any(char not in allowed for char in normalized):
            raise ValueError("DATABASE_SCHEMA may only contain letters, numbers, and underscores")
        return normalized

    @model_validator(mode="after")
    def validate_retry_delays(self) -> "Settings":
        if self.request_base_delay_seconds > self.request_max_delay_seconds:
            raise ValueError("REQUEST_BASE_DELAY_SECONDS cannot be greater than REQUEST_MAX_DELAY_SECONDS")
        return self

    @property
    def resolved_default_universe(self) -> Path:
        return (ROOT / self.default_universe).resolve() if not self.default_universe.is_absolute() else self.default_universe.resolve()

    @property
    def resolved_report_output_dir(self) -> Path:
        return (ROOT / self.report_output_dir).resolve() if not self.report_output_dir.is_absolute() else self.report_output_dir.resolve()

    @property
    def resolved_log_dir(self) -> Path:
        return (ROOT / self.log_dir).resolve() if not self.log_dir.is_absolute() else self.log_dir.resolve()

    @property
    def resolved_database_path(self) -> Path:
        return (ROOT / self.database_path).resolve() if not self.database_path.is_absolute() else self.database_path.resolve()

    @property
    def postgres_dsn(self) -> str:
        password = self.database_password or ""
        return (
            f"dbname={self.database_name} "
            f"user={self.database_user} "
            f"password={password} "
            f"host={self.database_host} "
            f"port={self.database_port}"
        )

    @property
    def resolved_lock_file(self) -> Path:
        return (ROOT / self.lock_file).resolve() if not self.lock_file.is_absolute() else self.lock_file.resolve()

    def validate_startup_files(self, require_universe: bool = True) -> None:
        if require_universe and not self.resolved_default_universe.exists():
            raise FileNotFoundError(
                f"Universe file not found: {self.resolved_default_universe}. "
                "Create the file or update DEFAULT_UNIVERSE in .env"
            )

        self.resolved_report_output_dir.mkdir(parents=True, exist_ok=True)
        self.resolved_log_dir.mkdir(parents=True, exist_ok=True)
        self.resolved_lock_file.parent.mkdir(parents=True, exist_ok=True)
        if self.database_backend == "sqlite":
            self.resolved_database_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.resolved_report_output_dir.is_dir():
            raise NotADirectoryError(f"REPORT_OUTPUT_DIR is not a directory: {self.resolved_report_output_dir}")
        if not self.resolved_log_dir.is_dir():
            raise NotADirectoryError(f"LOG_DIR is not a directory: {self.resolved_log_dir}")

    def default_report_filename(self, now: datetime | None = None) -> str:
        if now is None:
            localized_now = datetime.now(KOLKATA_TZ)
        elif now.tzinfo is None:
            localized_now = now.replace(tzinfo=KOLKATA_TZ)
        else:
            localized_now = now.astimezone(KOLKATA_TZ)
        timestamp = localized_now.strftime("%d-%m-%y--%H-%M")
        return f"{self.report_basename}_{timestamp}.xlsx"


@lru_cache
def get_settings() -> Settings:
    return Settings()
