from stock_agent.providers.fallback_provider import FallbackMarketDataProvider, FallbackNewsProvider
from pathlib import Path

from tests.fakes import (
    EmptyMarketDataProvider,
    MalformedNewsProvider,
    PartialMarketDataProvider,
    SuccessfulMarketDataProvider,
    SuccessfulNewsProvider,
    TimeoutMarketDataProvider,
)


def test_successful_full_report_generation(build_orchestrator):
    orchestrator, report_provider, run_repository = build_orchestrator(
        market_provider=SuccessfulMarketDataProvider(),
        news_provider=SuccessfulNewsProvider(),
    )

    report = orchestrator.run(["TCS.NS", "INFY.NS", "RELIANCE.NS"], Path("unused.xlsx"))

    assert report.status == "SUCCESS"
    assert report.total_requested == 3
    assert report.succeeded == 3
    assert report.failed == 0
    assert report.skipped == 0
    assert report_provider.write_called is True

    completed_run = run_repository.completed_runs[0]
    assert completed_run["status"] == "SUCCESS"
    assert completed_run["successful_tickers"] == 3
    assert completed_run["failed_tickers"] == 0
    assert completed_run["output_file_path"] is not None
    assert Path(completed_run["output_file_path"]).exists()


def test_provider_timeout_marks_run_as_failed_when_all_tickers_fail(build_orchestrator):
    orchestrator, report_provider, run_repository = build_orchestrator(
        market_provider=TimeoutMarketDataProvider(),
        news_provider=SuccessfulNewsProvider(),
    )

    report = orchestrator.run(["TCS.NS", "INFY.NS"], Path("unused.xlsx"))

    assert report.status == "FAILED"
    assert report.total_requested == 2
    assert report.succeeded == 0
    assert report.failed == 2
    assert report_provider.write_called is False

    completed_run = run_repository.completed_runs[0]
    assert completed_run["status"] == "FAILED"
    assert completed_run["successful_tickers"] == 0
    assert completed_run["failed_tickers"] == 2
    assert completed_run["output_file_path"] is None
    assert completed_run["error_summary"] is not None


def test_malformed_news_feed_marks_ticker_failed(build_orchestrator):
    orchestrator, report_provider, run_repository = build_orchestrator(
        market_provider=SuccessfulMarketDataProvider(),
        news_provider=MalformedNewsProvider(),
    )

    report = orchestrator.run(["TCS.NS", "INFY.NS"], Path("unused.xlsx"))

    assert report.status == "FAILED"
    assert report.total_requested == 2
    assert report.succeeded == 0
    assert report.failed == 2
    assert report_provider.write_called is False

    completed_run = run_repository.completed_runs[0]
    assert completed_run["status"] == "FAILED"
    assert completed_run["failed_tickers"] == 2


def test_empty_ticker_universe_fails_cleanly(build_orchestrator):
    orchestrator, report_provider, run_repository = build_orchestrator(
        market_provider=SuccessfulMarketDataProvider(),
        news_provider=SuccessfulNewsProvider(),
    )

    report = orchestrator.run([], Path("unused.xlsx"))

    assert report.status == "FAILED"
    assert report.total_requested == 0
    assert report.succeeded == 0
    assert report.failed == 0
    assert report.skipped == 0
    assert report_provider.write_called is False

    completed_run = run_repository.completed_runs[0]
    assert completed_run["status"] == "FAILED"
    assert completed_run["output_file_path"] is None
    assert completed_run["error_summary"] == "Ticker universe is empty"


def test_partial_data_availability_creates_partial_success_report(build_orchestrator):
    orchestrator, report_provider, run_repository = build_orchestrator(
        market_provider=PartialMarketDataProvider(failed_tickers={"INFY.NS", "WIPRO.NS"}),
        news_provider=SuccessfulNewsProvider(),
    )

    report = orchestrator.run(["TCS.NS", "INFY.NS", "RELIANCE.NS", "WIPRO.NS"], Path("unused.xlsx"))

    assert report.status == "PARTIAL_SUCCESS"
    assert report.total_requested == 4
    assert report.succeeded == 2
    assert report.failed == 2
    assert report.skipped == 0
    assert report_provider.write_called is True

    completed_run = run_repository.completed_runs[0]
    assert completed_run["status"] == "PARTIAL_SUCCESS"
    assert completed_run["successful_tickers"] == 2
    assert completed_run["failed_tickers"] == 2
    assert completed_run["output_file_path"] is not None
    assert completed_run["error_summary"] is not None
    assert Path(completed_run["output_file_path"]).exists()


def test_empty_market_data_marks_run_failed(build_orchestrator):
    orchestrator, report_provider, run_repository = build_orchestrator(
        market_provider=EmptyMarketDataProvider(),
        news_provider=SuccessfulNewsProvider(),
    )

    report = orchestrator.run(["INVALID.NS"], Path("unused.xlsx"))

    assert report.status == "FAILED"
    assert report.total_requested == 1
    assert report.succeeded == 0
    assert report.failed == 1
    assert report_provider.write_called is False

    completed_run = run_repository.completed_runs[0]
    assert completed_run["status"] == "FAILED"
    assert completed_run["failed_tickers"] == 1


def test_market_fallback_creates_partial_success_with_degraded_source(build_orchestrator):
    orchestrator, report_provider, run_repository = build_orchestrator(
        market_provider=FallbackMarketDataProvider(
            providers=[PartialMarketDataProvider(failed_tickers={"TCS.NS"}), SuccessfulMarketDataProvider()]
        ),
        news_provider=SuccessfulNewsProvider(),
    )

    report = orchestrator.run(["TCS.NS", "INFY.NS"], Path("unused.xlsx"))

    assert report.status == "PARTIAL_SUCCESS"
    assert report.succeeded == 2
    assert report.degraded_sources == ["partial_market"]
    assert report_provider.write_called is True
    assert any(item["provider"] == "partial_market" for item in run_repository.provider_errors)


def test_news_failure_is_best_effort_and_report_stays_degraded_success(build_orchestrator):
    orchestrator, report_provider, run_repository = build_orchestrator(
        market_provider=SuccessfulMarketDataProvider(),
        news_provider=FallbackNewsProvider(providers=[MalformedNewsProvider()]),
    )

    report = orchestrator.run(["TCS.NS", "INFY.NS"], Path("unused.xlsx"))

    assert report.status == "PARTIAL_SUCCESS"
    assert report.failed == 0
    assert report.succeeded == 2
    assert report.degraded_sources == ["malformed_news"]
    assert report_provider.write_called is True
    assert len(run_repository.provider_errors) == 2
