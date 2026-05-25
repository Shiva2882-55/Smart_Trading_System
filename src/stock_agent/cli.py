from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from stock_agent.config import get_settings
from stock_agent.core.exit_codes import CONFIG_ERROR, FAILED, LOCK_EXISTS, PARTIAL_SUCCESS, SUCCESS, UNEXPECTED_ERROR
from stock_agent.core.logging import setup_logging
from stock_agent.core.run_lock import RunLockError, run_lock
from stock_agent.persistence.database import init_db
from stock_agent.providers.excel_report_provider import ExcelReportProvider
from stock_agent.providers.factory import get_market_data_provider, get_news_provider
from stock_agent.providers.sqlite_run_repository import SQLiteRunRepository
from stock_agent.services.analysis_service import StockAnalysisService
from stock_agent.services.healthcheck_service import HealthcheckService
from stock_agent.services.run_orchestrator import StockAnalysisRunOrchestrator
from stock_agent.services.run_report_service import RunReportService
from stock_agent.services.summary_printer import format_run_summary


logger = logging.getLogger(__name__)


def _add_run_arguments(parser: argparse.ArgumentParser, settings) -> None:
    parser.add_argument("--universe", type=Path, default=settings.resolved_default_universe, help="Path to a file with one ticker per line.")
    parser.add_argument(
        "--input-excel",
        type=Path,
        nargs="+",
        help="One or more Excel files to use as ticker input. The app reads ticker columns from report sheets like 'All Ranked Stocks'.",
    )
    parser.add_argument("--preset", choices=["nifty50"], help="Load a built-in India stock universe.")
    parser.add_argument("--tickers", nargs="*", help="Explicit list of tickers to analyze.")
    parser.add_argument("--top", type=int, default=settings.top_n, help="How many top-ranked stocks to display.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Excel output file path. If omitted, a timestamped file like stock_analysis_dd-mm-yy--hr-mm.xlsx is created.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory where Excel reports should be saved.",
    )
    parser.add_argument(
        "--no-lock",
        action="store_true",
        help="Disable run lock. Use only for local debugging.",
    )


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        prog="stock-agent",
        description="Analyze India stocks and generate buy/hold/sell recommendations.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run stock analysis")
    _add_run_arguments(run_parser, settings)

    watch_parser = subparsers.add_parser("watch", help="Continuously rerun stock analysis on a timer")
    _add_run_arguments(watch_parser, settings)
    watch_parser.add_argument(
        "--interval-seconds",
        type=int,
        default=300,
        help="How long to wait between cycles. Default is 300 seconds.",
    )
    watch_parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Optional limit for how many cycles to run before stopping.",
    )

    subparsers.add_parser("healthcheck", help="Validate startup configuration")
    history_parser = subparsers.add_parser("history", help="Show recent analysis runs")
    history_parser.add_argument("--limit", type=int, default=10, help="How many recent runs to show.")
    return parser


def _build_default_output_path(base_dir: Path, now: datetime | None = None) -> Path:
    settings = get_settings()
    return base_dir / settings.default_report_filename(now=now)


def _next_available_path(path: Path) -> Path:
    if not path.exists():
        return path

    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}--{counter:02d}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _resolve_output_path(output_path: Path | None, base_dir: Path, now: datetime | None = None) -> Path:
    if output_path is not None:
        return output_path.expanduser()
    return _next_available_path(_build_default_output_path(base_dir, now=now))


def _find_previous_report(output_path: Path) -> Path | None:
    return ExcelReportProvider.find_previous_report(output_path)


def _load_tickers(args) -> list[str]:
    settings = get_settings()
    if args.tickers:
        args._input_feedback = {
            "source": "explicit_tickers",
            "details": [f"Explicit tickers provided in command: {len(args.tickers)}"],
            "tickers": list(args.tickers),
        }
        return args.tickers
    if getattr(args, "input_excel", None):
        return _load_tickers_from_excel_files(args.input_excel, args)
    if args.preset:
        if args.preset == "nifty50":
            tickers = _load_tickers_from_file(settings.resolved_default_universe)
            args._input_feedback = {
                "source": "preset",
                "details": [f"Preset universe loaded: {args.preset}"],
                "tickers": list(tickers),
            }
            return tickers
        raise ValueError(f"Unsupported preset universe: {args.preset}")
    if args.universe.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        return _load_tickers_from_excel_files([args.universe], args)
    tickers = _load_tickers_from_file(args.universe)
    args._input_feedback = {
        "source": "text_file",
        "details": [f"Universe file loaded: {args.universe}"],
        "tickers": list(tickers),
    }
    return tickers


def _load_tickers_from_file(file_path: Path) -> list[str]:
    if not file_path.exists():
        raise FileNotFoundError(f"Universe file was not found: {file_path}")
    tickers: list[str] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        raw_value = line.split("#", 1)[0].strip()
        if raw_value:
            tickers.append(raw_value)
    if not tickers:
        raise ValueError(f"Universe file is empty after filtering comments and blanks: {file_path}")
    return tickers


def _load_tickers_from_excel_files(file_paths: list[Path], args) -> list[str]:
    preferred_sheets = [
        "All Ranked Stocks",
        "Top Recommendations",
        "Best Buy Opportunities",
        "Best Sell Candidates",
        "Sector Leaders",
    ]
    candidate_columns = ["ticker", "leader_ticker"]
    seen: set[str] = set()
    tickers: list[str] = []
    details: list[str] = []

    for file_path in file_paths:
        resolved = file_path.expanduser()
        if not resolved.exists():
            raise FileNotFoundError(f"Excel input file was not found: {resolved}")

        workbook = pd.ExcelFile(resolved)
        selected_sheet: str | None = None
        selected_column: str | None = None
        selected_values: list[str] = []

        ordered_sheet_names = [name for name in preferred_sheets if name in workbook.sheet_names]
        ordered_sheet_names.extend(name for name in workbook.sheet_names if name not in ordered_sheet_names)
        for sheet_name in ordered_sheet_names:
            frame = pd.read_excel(resolved, sheet_name=sheet_name)
            normalized_columns = {str(column).strip().lower(): column for column in frame.columns}
            for candidate in candidate_columns:
                if candidate in normalized_columns:
                    selected_sheet = sheet_name
                    selected_column = str(normalized_columns[candidate])
                    selected_values = [
                        str(value).strip()
                        for value in frame[normalized_columns[candidate]].tolist()
                        if pd.notna(value) and str(value).strip()
                    ]
                    break
            if selected_sheet is not None:
                break

        if selected_sheet is None or selected_column is None:
            raise ValueError(
                f"Could not find a ticker column in Excel input: {resolved}. "
                "Expected columns like 'ticker' or 'leader_ticker'."
            )

        added_count = 0
        for ticker in selected_values:
            if ticker not in seen:
                seen.add(ticker)
                tickers.append(ticker)
                added_count += 1
        details.append(
            f"{resolved.name} -> sheet '{selected_sheet}' column '{selected_column}' "
            f"({added_count} tickers understood)"
        )

    if not tickers:
        raise ValueError("Excel input did not contain any usable tickers.")

    args._input_feedback = {
        "source": "excel",
        "details": details,
        "tickers": list(tickers),
    }
    return tickers


def _print_input_feedback(input_feedback: dict | None, output_path: Path, settings) -> None:
    if input_feedback is None:
        return

    tickers = list(input_feedback.get("tickers", []))
    preview = ", ".join(tickers[:5]) if tickers else "None"
    if len(tickers) > 5:
        preview = f"{preview}, ..."

    print("========== INPUT UNDERSTANDING ==========")
    print(f"Source            : {str(input_feedback.get('source', 'unknown')).replace('_', ' ').title()}")
    for detail in input_feedback.get("details", []):
        print(f"Understood        : {detail}")
    print(f"Tickers loaded    : {len(tickers)}")
    print(f"Ticker preview    : {preview}")
    print(f"Market provider   : {settings.market_provider}")
    print(f"News provider     : {settings.news_provider}")
    print(f"Output report     : {output_path}")
    print("=========================================")


def main() -> int:
    logger_to_use = logging.getLogger(__name__)
    try:
        settings = get_settings()
        parser = build_parser()
        args = parser.parse_args()
        require_universe = (
            args.command in {"run", "watch"}
            and not bool(getattr(args, "tickers", None))
            and not bool(getattr(args, "input_excel", None))
        )
        settings.validate_startup_files(require_universe=require_universe)
        setup_logging(settings.resolved_log_dir, settings.log_file, settings.log_level)
    except ValidationError as exc:
        print(f"Configuration validation failed:\n{exc}")
        return CONFIG_ERROR
    except Exception as exc:
        print(f"Startup validation failed: {exc}")
        return CONFIG_ERROR

    if args.command == "healthcheck":
        print(HealthcheckService().run())
        return SUCCESS

    if args.command == "history":
        if not settings.enable_sqlite_history:
            print("SQLite run history is disabled in configuration.")
            return FAILED
        init_db()
        run_repository = SQLiteRunRepository()
        for run in run_repository.get_recent_runs(limit=args.limit):
            print(
                f"{run['run_id']} | {run['status']} | "
                f"{run['successful_tickers']} success | "
                f"{run['failed_tickers']} failed | "
                f"{run['skipped_tickers']} skipped"
            )
        return SUCCESS

    try:
        if args.command == "watch":
            if args.no_lock:
                return _execute_watch(args, settings)
            with run_lock(
                lock_file=settings.resolved_lock_file,
                stale_after_seconds=settings.lock_stale_after_seconds,
            ):
                return _execute_watch(args, settings)

        if args.no_lock:
            return _execute_run(args, settings)

        with run_lock(
            lock_file=settings.resolved_lock_file,
            stale_after_seconds=settings.lock_stale_after_seconds,
        ):
            return _execute_run(args, settings)
    except RunLockError as exc:
        logger_to_use.warning(
            "run_skipped_lock_exists",
            extra={"event": "run_skipped_lock_exists", "failure_reason": str(exc)},
        )
        print(str(exc))
        return LOCK_EXISTS
    except Exception as exc:
        logger_to_use.exception(
            "unexpected_cli_failure",
            extra={
                "event": "unexpected_cli_failure",
                "error_type": type(exc).__name__,
                "failure_reason": str(exc),
            },
        )
        print(f"Unexpected failure: {exc}")
        return UNEXPECTED_ERROR


def _execute_run(args, settings) -> int:
    output_base_dir = args.output_dir.expanduser() if args.output_dir else settings.resolved_report_output_dir
    output_base_dir.mkdir(parents=True, exist_ok=True)
    output_path = _resolve_output_path(args.output, output_base_dir)
    tickers = _load_tickers(args)
    _print_input_feedback(getattr(args, "_input_feedback", None), output_path, settings)
    print("Starting analysis...")
    if settings.enable_sqlite_history:
        init_db()
    ticker_analysis_service = StockAnalysisService(
        market_data_provider=get_market_data_provider(),
        news_provider=get_news_provider(),
    )
    report_provider = ExcelReportProvider() if settings.enable_excel_report else None
    run_repository = SQLiteRunRepository() if settings.enable_sqlite_history else None
    orchestrator = StockAnalysisRunOrchestrator(
        ticker_analysis_service=ticker_analysis_service,
        report_provider=report_provider,
        run_repository=run_repository,
        run_report_service=RunReportService(),
        lookback_days=settings.news_lookback_days,
        top_n=args.top,
        enable_excel_report=settings.enable_excel_report,
        enable_sqlite_history=settings.enable_sqlite_history,
    )

    report = orchestrator.run(tickers=tickers, output_path=output_path)
    print(format_run_summary(report))

    if report.status == "SUCCESS":
        return SUCCESS
    if report.status == "PARTIAL_SUCCESS":
        return PARTIAL_SUCCESS
    return FAILED


def _execute_watch(args, settings) -> int:
    interval_seconds = max(1, int(args.interval_seconds))
    max_cycles = args.max_cycles
    cycle_number = 0
    last_exit_code = SUCCESS

    print("========== WATCH MODE ==========")
    print("Mode              : Continuous stock monitoring")
    print(f"Interval seconds  : {interval_seconds}")
    print(f"Max cycles        : {max_cycles if max_cycles is not None else 'Until stopped'}")
    print("Stop              : Press Ctrl+C anytime")
    print("================================")

    try:
        while True:
            cycle_number += 1
            print(f"\n----- Watch cycle {cycle_number} started -----")
            last_exit_code = _execute_run(args, settings)
            print(f"----- Watch cycle {cycle_number} finished with exit code {last_exit_code} -----")

            if max_cycles is not None and cycle_number >= max_cycles:
                print("Watch mode finished because max cycles was reached.")
                return last_exit_code

            print(f"Sleeping for {interval_seconds} seconds before the next cycle...")
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nWatch mode stopped by user.")
        return last_exit_code
