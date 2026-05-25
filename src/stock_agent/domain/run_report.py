from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ProviderIssue:
    ticker: str
    provider: str
    operation: str
    error_type: str
    error_message: str
    severity: str = "WARNING"


@dataclass(slots=True)
class TickerResult:
    ticker: str
    status: str
    error_message: str | None = None


@dataclass(slots=True)
class RunReport:
    run_id: str
    total_requested: int
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    degraded_sources: list[str] = field(default_factory=list)
    provider_issues: list[ProviderIssue] = field(default_factory=list)
    ticker_results: list[TickerResult] = field(default_factory=list)
    status: str = "IN_PROGRESS"
    warning_severity: str = "NONE"
    output_file_path: str | None = None
