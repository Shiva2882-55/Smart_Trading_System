from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from stock_agent import config as config_module


def test_settings_reject_invalid_yfinance_period(monkeypatch):
    monkeypatch.setenv("YFINANCE_PERIOD", "100years")
    config_module.get_settings.cache_clear()

    with pytest.raises(ValidationError):
        config_module.get_settings()

    config_module.get_settings.cache_clear()
    monkeypatch.delenv("YFINANCE_PERIOD", raising=False)


def test_settings_validate_startup_files_creates_directories(monkeypatch, tmp_path: Path):
    universe_file = tmp_path / "watchlists" / "core_watchlist.txt"
    universe_file.parent.mkdir(parents=True, exist_ok=True)
    universe_file.write_text("TCS\n", encoding="utf-8")

    monkeypatch.setenv("DEFAULT_UNIVERSE", str(universe_file))
    monkeypatch.setenv("REPORT_OUTPUT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "stock_agent.db"))
    config_module.get_settings.cache_clear()

    settings = config_module.get_settings()
    settings.validate_startup_files(require_universe=True)

    assert settings.resolved_report_output_dir.exists()
    assert settings.resolved_log_dir.exists()
    assert settings.resolved_database_path.parent.exists()

    config_module.get_settings.cache_clear()


def test_default_report_filename_uses_kolkata_timezone():
    settings = config_module.Settings()

    filename = settings.default_report_filename(now=datetime(2026, 5, 25, 10, 5, tzinfo=timezone.utc))

    assert filename == "stock_analysis_25-05-26--15-35.xlsx"
