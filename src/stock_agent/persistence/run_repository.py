from __future__ import annotations

from datetime import datetime, timezone

from stock_agent.persistence.database import get_connection, qualify_table


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunRepository:
    def create_run(self, run_id: str, total_tickers: int = 0) -> None:
        with get_connection() as conn:
            conn.execute(
                f"""
                INSERT INTO {qualify_table("analysis_runs")} (
                    run_id,
                    started_at,
                    status,
                    total_tickers
                ) VALUES (?, ?, ?, ?);
                """,
                (run_id, utc_now(), "IN_PROGRESS", total_tickers),
            )
            conn.commit()

    def complete_run(
        self,
        run_id: str,
        status: str,
        successful_tickers: int,
        failed_tickers: int,
        skipped_tickers: int,
        total_tickers: int,
        output_file_path: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                f"""
                UPDATE {qualify_table("analysis_runs")}
                SET
                    ended_at = ?,
                    status = ?,
                    total_tickers = ?,
                    successful_tickers = ?,
                    failed_tickers = ?,
                    skipped_tickers = ?,
                    output_file_path = ?,
                    error_summary = ?
                WHERE run_id = ?;
                """,
                (
                    utc_now(),
                    status,
                    total_tickers,
                    successful_tickers,
                    failed_tickers,
                    skipped_tickers,
                    output_file_path,
                    error_summary,
                    run_id,
                ),
            )
            conn.commit()

    def add_ticker_result(
        self,
        run_id: str,
        ticker: str,
        status: str,
        provider: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                f"""
                INSERT INTO {qualify_table("run_ticker_results")} (
                    run_id,
                    ticker,
                    status,
                    provider,
                    error_type,
                    error_message
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (run_id, ticker, status, provider, error_type, error_message),
            )
            conn.commit()

    def add_provider_error(
        self,
        run_id: str,
        provider: str,
        error_type: str,
        error_message: str,
        ticker: str | None = None,
        operation: str | None = None,
        retry_attempt: int | None = None,
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                f"""
                INSERT INTO {qualify_table("provider_errors")} (
                    run_id,
                    ticker,
                    provider,
                    operation,
                    error_type,
                    error_message,
                    retry_attempt
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (run_id, ticker, provider, operation, error_type, error_message, retry_attempt),
            )
            conn.commit()

    def get_recent_runs(self, limit: int = 10) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    run_id,
                    started_at,
                    ended_at,
                    status,
                    total_tickers,
                    successful_tickers,
                    failed_tickers,
                    skipped_tickers,
                    output_file_path,
                    error_summary
                FROM {qualify_table("analysis_runs")}
                ORDER BY id DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_run_details(self, run_id: str) -> dict:
        with get_connection() as conn:
            run = conn.execute(
                f"SELECT * FROM {qualify_table('analysis_runs')} WHERE run_id = ?;",
                (run_id,),
            ).fetchone()
            ticker_results = conn.execute(
                f"SELECT * FROM {qualify_table('run_ticker_results')} WHERE run_id = ? ORDER BY id ASC;",
                (run_id,),
            ).fetchall()
            provider_errors = conn.execute(
                f"SELECT * FROM {qualify_table('provider_errors')} WHERE run_id = ? ORDER BY id ASC;",
                (run_id,),
            ).fetchall()
            return {
                "run": dict(run) if run else None,
                "ticker_results": [dict(row) for row in ticker_results],
                "provider_errors": [dict(row) for row in provider_errors],
            }
