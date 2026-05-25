from __future__ import annotations

from collections import Counter

from stock_agent.domain.run_report import ProviderIssue, RunReport, TickerResult


class RunReportService:
    def build_summary(
        self,
        run_id: str,
        total_requested: int,
        ticker_results: list[TickerResult],
        provider_issues: list[ProviderIssue],
        output_file_path: str | None = None,
    ) -> RunReport:
        succeeded = sum(1 for result in ticker_results if result.status == "SUCCESS")
        failed = sum(1 for result in ticker_results if result.status == "FAILED")
        skipped = sum(1 for result in ticker_results if result.status == "SKIPPED")
        degraded_sources = self._get_degraded_sources(provider_issues)
        status = self._calculate_status(
            total_requested=total_requested,
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            degraded_sources=degraded_sources,
        )
        warning_severity = self._calculate_warning_severity(
            total_requested=total_requested,
            failed=failed,
            skipped=skipped,
            degraded_sources=degraded_sources,
        )
        return RunReport(
            run_id=run_id,
            total_requested=total_requested,
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            degraded_sources=degraded_sources,
            provider_issues=provider_issues,
            ticker_results=ticker_results,
            status=status,
            warning_severity=warning_severity,
            output_file_path=output_file_path,
        )

    def _get_degraded_sources(self, provider_issues: list[ProviderIssue]) -> list[str]:
        provider_counts = Counter(issue.provider for issue in provider_issues)
        return sorted(provider_counts.keys())

    def _calculate_status(
        self,
        total_requested: int,
        succeeded: int,
        failed: int,
        skipped: int,
        degraded_sources: list[str],
    ) -> str:
        if total_requested == 0:
            return "FAILED"
        if succeeded == total_requested and failed == 0 and skipped == 0 and not degraded_sources:
            return "SUCCESS"
        if succeeded > 0:
            return "PARTIAL_SUCCESS"
        return "FAILED"

    def _calculate_warning_severity(
        self,
        total_requested: int,
        failed: int,
        skipped: int,
        degraded_sources: list[str],
    ) -> str:
        if total_requested == 0:
            return "CRITICAL"

        failed_or_skipped = failed + skipped
        failure_percent = (failed_or_skipped / total_requested) * 100

        if failure_percent == 0 and not degraded_sources:
            return "NONE"
        if failure_percent <= 10:
            return "LOW"
        if failure_percent <= 30:
            return "MEDIUM"
        if failure_percent <= 60:
            return "HIGH"
        return "CRITICAL"
