from pathlib import Path

from stock_agent import config as config_module
from stock_agent.core.exceptions import ProviderTimeoutError
from stock_agent.core.logging import log_context
from stock_agent.core.retry import RetryConfig, run_with_retry
from stock_agent.persistence.database import init_db
from stock_agent.persistence.run_repository import RunRepository


def test_run_repository_persists_run_and_details(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "stock_agent.db"))
    config_module.get_settings.cache_clear()
    init_db()
    repo = RunRepository()

    repo.create_run("RUN-TEST", total_tickers=3)
    repo.add_ticker_result("RUN-TEST", "TCS", "SUCCESS", provider="analysis_service")
    repo.add_provider_error(
        run_id="RUN-TEST",
        ticker="INFY",
        provider="yfinance",
        operation="download_price_history",
        error_type="ProviderTimeoutError",
        error_message="timeout",
        retry_attempt=3,
    )
    repo.complete_run(
        run_id="RUN-TEST",
        status="PARTIAL_SUCCESS",
        total_tickers=3,
        successful_tickers=2,
        failed_tickers=1,
        skipped_tickers=0,
        output_file_path="reports/out.xlsx",
        error_summary="1 ticker failed",
    )

    details = repo.get_run_details("RUN-TEST")

    assert details["run"]["status"] == "PARTIAL_SUCCESS"
    assert details["run"]["output_file_path"] == "reports/out.xlsx"
    assert details["ticker_results"][0]["ticker"] == "TCS"
    assert details["provider_errors"][0]["provider"] == "yfinance"
    config_module.get_settings.cache_clear()


def test_retry_persists_provider_error_with_run_context(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "stock_agent.db"))
    config_module.get_settings.cache_clear()
    monkeypatch.setattr("stock_agent.core.retry.time.sleep", lambda _: None)
    monkeypatch.setattr("stock_agent.core.retry.random.uniform", lambda _a, _b: 0.0)
    init_db()
    repo = RunRepository()
    repo.create_run("RUN-CTX", total_tickers=1)

    with log_context(run_id="RUN-CTX"):
        try:
            run_with_retry(
                operation=lambda: (_ for _ in ()).throw(ProviderTimeoutError("provider timeout")),
                operation_name="fetch_google_news",
                provider="google_news",
                ticker="RELIANCE.NS",
                config=RetryConfig(max_attempts=2, base_delay_seconds=0.01, max_delay_seconds=0.1, jitter_seconds=0.0),
            )
        except ProviderTimeoutError:
            pass

    details = repo.get_run_details("RUN-CTX")

    assert len(details["provider_errors"]) == 1
    assert details["provider_errors"][0]["provider"] == "google_news"
    assert details["provider_errors"][0]["retry_attempt"] == 2
    config_module.get_settings.cache_clear()
