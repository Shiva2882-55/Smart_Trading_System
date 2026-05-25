from stock_agent.domain.run_report import ProviderIssue, TickerResult
from stock_agent.services.run_report_service import RunReportService


def test_build_summary_marks_partial_success_and_medium_severity():
    service = RunReportService()

    report = service.build_summary(
        run_id="RUN-123",
        total_requested=10,
        ticker_results=[
            TickerResult(ticker="TCS", status="SUCCESS"),
            TickerResult(ticker="INFY", status="FAILED", error_message="timeout"),
            TickerResult(ticker="RELIANCE", status="SKIPPED", error_message="news unavailable"),
        ],
        provider_issues=[
            ProviderIssue(
                ticker="INFY",
                provider="google_news",
                operation="fetch_google_news",
                error_type="ProviderTimeoutError",
                error_message="timeout",
            )
        ],
        output_file_path="reports/report.xlsx",
    )

    assert report.status == "PARTIAL_SUCCESS"
    assert report.warning_severity == "MEDIUM"
    assert report.degraded_sources == ["google_news"]


def test_build_summary_marks_degraded_run_as_partial_success():
    service = RunReportService()

    report = service.build_summary(
        run_id="RUN-456",
        total_requested=2,
        ticker_results=[
            TickerResult(ticker="TCS", status="SUCCESS"),
            TickerResult(ticker="INFY", status="SUCCESS"),
        ],
        provider_issues=[
            ProviderIssue(
                ticker="TCS",
                provider="google_news",
                operation="get_news",
                error_type="ProviderTimeoutError",
                error_message="timeout",
            )
        ],
        output_file_path="reports/report.xlsx",
    )

    assert report.status == "PARTIAL_SUCCESS"
    assert report.warning_severity == "LOW"
    assert report.degraded_sources == ["google_news"]
