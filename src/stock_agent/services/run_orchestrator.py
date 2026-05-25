from __future__ import annotations

import logging
from pathlib import Path

from stock_agent.core.logging import generate_run_id, log_context
from stock_agent.domain.run_report import ProviderIssue, RunReport, TickerResult
from stock_agent.models import Recommendation, StockAnalysisResult
from stock_agent.provider_utils import validate_india_ticker
from stock_agent.providers.base import ReportProvider, RunRepository
from stock_agent.scoring import score_stock
from stock_agent.services.analysis_service import StockAnalysisService
from stock_agent.services.run_report_service import RunReportService


logger = logging.getLogger(__name__)


class StockAnalysisRunOrchestrator:
    def __init__(
        self,
        ticker_analysis_service: StockAnalysisService,
        report_provider: ReportProvider | None,
        run_repository: RunRepository | None,
        run_report_service: RunReportService,
        lookback_days: int,
        top_n: int,
        enable_excel_report: bool,
        enable_sqlite_history: bool,
    ) -> None:
        self.ticker_analysis_service = ticker_analysis_service
        self.report_provider = report_provider
        self.run_repository = run_repository
        self.run_report_service = run_report_service
        self.lookback_days = lookback_days
        self.top_n = top_n
        self.enable_excel_report = enable_excel_report
        self.enable_sqlite_history = enable_sqlite_history
        self.last_results: list[StockAnalysisResult] = []
        self.last_failures: list[str] = []

    def run(self, tickers: list[str], output_path: Path) -> RunReport:
        run_id = generate_run_id()
        self.last_results = []
        self.last_failures = []

        with log_context(run_id=run_id):
            logger.info(
                "analysis_run_started",
                extra={
                    "event": "analysis_run_started",
                    "run_id": run_id,
                    "total_tickers": len(tickers),
                    "output_path": str(output_path),
                },
            )
            if self.enable_sqlite_history and self.run_repository is not None:
                self.run_repository.create_run(run_id=run_id, total_tickers=0)

            try:
                if len(tickers) == 0:
                    report = self.run_report_service.build_summary(
                        run_id=run_id,
                        total_requested=0,
                        ticker_results=[],
                        provider_issues=[],
                        output_file_path=None,
                    )
                    if self.enable_sqlite_history and self.run_repository is not None:
                        self.run_repository.complete_run(
                            run_id=run_id,
                            status="FAILED",
                            total_tickers=0,
                            successful_tickers=0,
                            failed_tickers=0,
                            skipped_tickers=0,
                            output_file_path=None,
                            error_summary="Ticker universe is empty",
                        )
                    logger.error(
                        "analysis_run_failed_empty_universe",
                        extra={
                            "event": "analysis_run_failed_empty_universe",
                            "run_id": run_id,
                            "failure_reason": "Ticker universe is empty",
                        },
                    )
                    return report

                normalized_tickers = self._normalize_tickers(tickers)
                market = self.ticker_analysis_service.get_market_context()
                successful_snapshots = []

                for ticker in normalized_tickers:
                    result = self.ticker_analysis_service.analyze_ticker(ticker, self.lookback_days)
                    self.last_results.append(result)
                    if result.snapshot is None:
                        self.last_failures.append(f"{ticker}: {result.error or 'Unknown analysis failure'}")
                        continue
                    successful_snapshots.append(result.snapshot)

                if self.enable_sqlite_history and self.run_repository is not None:
                    self._persist_ticker_results(run_id, self.last_results)

                if not successful_snapshots:
                    report = self._build_run_report(run_id, len(tickers), output_file_path=None)
                    if self.enable_sqlite_history and self.run_repository is not None:
                        self.run_repository.complete_run(
                            run_id=run_id,
                            status=report.status,
                            total_tickers=len(tickers),
                            successful_tickers=report.succeeded,
                            failed_tickers=report.failed,
                            skipped_tickers=report.skipped,
                            output_file_path=None,
                            error_summary=self._build_error_summary(report),
                        )
                    logger.info(
                        "analysis_run_completed",
                        extra={
                            "event": "analysis_run_completed",
                            "run_id": run_id,
                            "status": report.status,
                            "successful": report.succeeded,
                            "failed": report.failed,
                            "skipped": report.skipped,
                        },
                    )
                    return report

                recommendations, by_sector = self._score_snapshots(successful_snapshots, market)
                report = self._build_run_report(run_id, len(tickers), output_file_path=str(output_path.resolve()))

                if self.enable_excel_report and self.report_provider is not None:
                    saved_path = self.report_provider.write_report(
                        output_path=output_path,
                        recommendations=recommendations,
                        by_sector=by_sector,
                        failures=self.last_failures,
                        run_report=report,
                        top_n=self.top_n,
                    )
                    report.output_file_path = str(saved_path.resolve())

                if self.enable_sqlite_history and self.run_repository is not None:
                    self.run_repository.complete_run(
                        run_id=run_id,
                        status=report.status,
                        total_tickers=len(tickers),
                        successful_tickers=report.succeeded,
                        failed_tickers=report.failed,
                        skipped_tickers=report.skipped,
                        output_file_path=report.output_file_path,
                        error_summary=self._build_error_summary(report),
                    )

                logger.info(
                    "analysis_run_completed",
                    extra={
                        "event": "analysis_run_completed",
                        "run_id": run_id,
                        "status": report.status,
                        "successful": report.succeeded,
                        "failed": report.failed,
                        "skipped": report.skipped,
                        "output_file_path": report.output_file_path,
                        "degraded_sources": report.degraded_sources,
                        "warning_severity": report.warning_severity,
                    },
                )
                return report
            except Exception as exc:
                logger.info(
                    "analysis_run_failed",
                    extra={
                        "event": "analysis_run_failed",
                        "run_id": run_id,
                        "status": "FAILED",
                        "error_type": type(exc).__name__,
                        "failure_reason": str(exc),
                    },
                )
                if self.enable_sqlite_history and self.run_repository is not None:
                    if self.last_results:
                        self._persist_ticker_results(run_id, self.last_results)
                    self.run_repository.complete_run(
                        run_id=run_id,
                        status="FAILED",
                        total_tickers=len(tickers),
                        successful_tickers=sum(1 for item in self.last_results if item.status == "SUCCESS"),
                        failed_tickers=sum(1 for item in self.last_results if item.status == "FAILED"),
                        skipped_tickers=sum(1 for item in self.last_results if item.status == "SKIPPED"),
                        output_file_path=None,
                        error_summary=str(exc),
                    )
                raise

    def _normalize_tickers(self, tickers: list[str]) -> list[str]:
        normalized_tickers: list[str] = []
        seen: set[str] = set()
        for ticker in tickers:
            try:
                normalized_ticker = validate_india_ticker(ticker)
                if normalized_ticker in seen:
                    continue
                seen.add(normalized_ticker)
                normalized_tickers.append(normalized_ticker)
            except Exception as exc:
                self.last_failures.append(f"{ticker}: {exc}")
                self.last_results.append(
                    StockAnalysisResult(
                        ticker=ticker,
                        snapshot=None,
                        news=[],
                        status="FAILED",
                        error=str(exc),
                        error_type=type(exc).__name__,
                        provider="validation",
                    )
                )
        return normalized_tickers

    def _score_snapshots(self, snapshots: list, market) -> tuple[list[Recommendation], dict[str, list[Recommendation]]]:
        from collections import defaultdict

        recommendations: list[Recommendation] = []
        sector_momentum: dict[str, list[float]] = defaultdict(list)
        for snapshot in snapshots:
            sector_momentum[snapshot.sector].append(snapshot.change_percent_3m)

        sector_strength = {
            sector: (sum(values) / len(values)) - market.spy_change_3m
            for sector, values in sector_momentum.items()
            if values
        }

        for snapshot in snapshots:
            recommendations.append(
                score_stock(
                    snapshot,
                    market,
                    sector_relative_strength=sector_strength.get(snapshot.sector, 0.0),
                )
            )

        recommendations.sort(key=lambda item: item.score, reverse=True)

        by_sector: dict[str, list[Recommendation]] = defaultdict(list)
        for item in recommendations:
            by_sector[item.sector].append(item)

        for items in by_sector.values():
            items.sort(key=lambda item: item.score, reverse=True)

        return recommendations, dict(by_sector)

    def _persist_ticker_results(self, run_id: str, results: list[StockAnalysisResult]) -> None:
        if self.run_repository is None:
            return
        for result in results:
            self.run_repository.add_ticker_result(
                run_id=run_id,
                ticker=result.ticker,
                status=result.status,
                provider=result.provider or "analysis_service",
                error_type=result.error_type,
                error_message=result.error,
            )
            if result.status == "SUCCESS":
                for issue in result.provider_issues:
                    self.run_repository.add_provider_error(
                        run_id=run_id,
                        ticker=issue.ticker or result.ticker,
                        provider=issue.provider,
                        operation=issue.operation,
                        error_type=issue.error_type,
                        error_message=issue.error_message,
                    )

    def _build_run_report(self, run_id: str, total_requested: int, output_file_path: str | None) -> RunReport:
        if self.enable_sqlite_history and self.run_repository is not None:
            details = self.run_repository.get_run_details(run_id)
            ticker_results = [
                TickerResult(
                    ticker=row["ticker"],
                    status=row["status"],
                    error_message=row["error_message"],
                )
                for row in details["ticker_results"]
            ]
            provider_issues = [
                ProviderIssue(
                    ticker=row["ticker"] or "",
                    provider=row["provider"],
                    operation=row["operation"] or "",
                    error_type=row["error_type"],
                    error_message=row["error_message"],
                    severity=self._issue_severity_from_error_type(row["error_type"]),
                )
                for row in details["provider_errors"]
            ]
        else:
            ticker_results = [
                TickerResult(ticker=result.ticker, status=result.status, error_message=result.error)
                for result in self.last_results
            ]
            provider_issues = []
            for result in self.last_results:
                provider_issues.extend(result.provider_issues)
                if result.status != "SUCCESS" and not result.provider_issues:
                    provider_issues.append(
                        ProviderIssue(
                            ticker=result.ticker,
                            provider=result.provider or "analysis_service",
                            operation="analyze_ticker",
                            error_type=result.error_type or "AnalysisFailure",
                            error_message=result.error or "Unknown analysis failure",
                            severity=self._issue_severity_from_error_type(result.error_type or "AnalysisFailure"),
                        )
                    )

        return self.run_report_service.build_summary(
            run_id=run_id,
            total_requested=total_requested,
            ticker_results=ticker_results,
            provider_issues=provider_issues,
            output_file_path=output_file_path,
        )

    @staticmethod
    def _build_error_summary(report: RunReport) -> str | None:
        if report.warning_severity == "NONE":
            return None
        degraded = ", ".join(report.degraded_sources) if report.degraded_sources else "None"
        return f"{report.warning_severity}: {report.failed} failed, {report.skipped} skipped, degraded sources: {degraded}"

    @staticmethod
    def _issue_severity_from_error_type(error_type: str) -> str:
        if error_type in {"ProviderTimeoutError", "ProviderRateLimitError"}:
            return "WARNING"
        if error_type in {"EmptyDataError", "InvalidTickerError"}:
            return "ERROR"
        return "ERROR"
