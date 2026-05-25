from __future__ import annotations

from stock_agent.domain.run_report import RunReport


def format_run_summary(report: RunReport) -> str:
    lines = [
        "========== STOCK ANALYSIS RUN SUMMARY ==========",
        f"Run ID            : {report.run_id}",
        f"Status            : {report.status}",
        f"Warning Severity  : {report.warning_severity}",
        f"Total Requested   : {report.total_requested}",
        f"Succeeded         : {report.succeeded}",
        f"Failed            : {report.failed}",
        f"Skipped           : {report.skipped}",
        f"Degraded Sources  : {', '.join(report.degraded_sources) if report.degraded_sources else 'None'}",
        f"Output File       : {report.output_file_path or ''}",
    ]

    if report.provider_issues:
        lines.append("")
        lines.append("Provider Issues:")
        for issue in report.provider_issues:
            lines.append(
                f"- {issue.ticker} | {issue.provider} | {issue.error_type} | {issue.error_message}"
            )

    lines.append("================================================")
    return "\n".join(lines)
