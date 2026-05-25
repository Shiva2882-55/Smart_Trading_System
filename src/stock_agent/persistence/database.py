from __future__ import annotations

import sqlite3
from typing import Any

from stock_agent.config import get_settings


class DatabaseConnection:
    def __init__(self, connection: Any, backend: str) -> None:
        self._connection = connection
        self._backend = backend

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self._connection.__exit__(exc_type, exc, tb)

    def execute(self, query: str, params: tuple | list = ()):
        if self._backend == "postgres":
            query = query.replace("?", "%s")
        return self._connection.execute(query, params)

    def commit(self) -> None:
        self._connection.commit()


def get_schema_name() -> str:
    settings = get_settings()
    if settings.database_backend == "sqlite":
        return ""
    return settings.database_schema


def qualify_table(table_name: str) -> str:
    schema_name = get_schema_name()
    if not schema_name:
        return table_name
    return f"{schema_name}.{table_name}"


def get_connection() -> DatabaseConnection:
    settings = get_settings()
    if settings.database_backend == "sqlite":
        db_path = settings.resolved_database_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return DatabaseConnection(connection, backend="sqlite")

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL support requires 'psycopg'. Install project dependencies before using DATABASE_BACKEND=postgres."
        ) from exc

    connection = psycopg.connect(settings.postgres_dsn, row_factory=dict_row)
    return DatabaseConnection(connection, backend="postgres")


def init_db() -> None:
    settings = get_settings()
    with get_connection() as conn:
        if settings.database_backend == "postgres":
            analysis_runs_table = qualify_table("analysis_runs")
            ticker_results_table = qualify_table("run_ticker_results")
            provider_errors_table = qualify_table("provider_errors")
            conn.execute(f"CREATE SCHEMA IF NOT EXISTS {settings.database_schema};")
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {analysis_runs_table} (
                    id BIGSERIAL PRIMARY KEY,
                    run_id TEXT UNIQUE NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT NOT NULL,
                    total_tickers INTEGER DEFAULT 0,
                    successful_tickers INTEGER DEFAULT 0,
                    failed_tickers INTEGER DEFAULT 0,
                    skipped_tickers INTEGER DEFAULT 0,
                    output_file_path TEXT,
                    error_summary TEXT,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {ticker_results_table} (
                    id BIGSERIAL PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES {analysis_runs_table}(run_id)
                );
                """
            )
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {provider_errors_table} (
                    id BIGSERIAL PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    ticker TEXT,
                    provider TEXT NOT NULL,
                    operation TEXT,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    retry_attempt INTEGER,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES {analysis_runs_table}(run_id)
                );
                """
            )
            conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_analysis_runs_run_id
                ON {analysis_runs_table} (run_id);
                """
            )
            conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_run_ticker_results_run_id
                ON {ticker_results_table} (run_id);
                """
            )
            conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_provider_errors_run_id
                ON {provider_errors_table} (run_id);
                """
            )
        else:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT UNIQUE NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT NOT NULL,
                    total_tickers INTEGER DEFAULT 0,
                    successful_tickers INTEGER DEFAULT 0,
                    failed_tickers INTEGER DEFAULT 0,
                    skipped_tickers INTEGER DEFAULT 0,
                    output_file_path TEXT,
                    error_summary TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_ticker_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id)
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    ticker TEXT,
                    provider TEXT NOT NULL,
                    operation TEXT,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    retry_attempt INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES analysis_runs(run_id)
                );
                """
            )
        conn.commit()
