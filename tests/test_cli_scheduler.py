from pathlib import Path

from stock_agent.cli import _execute_run, _execute_watch
from stock_agent.core.exit_codes import PARTIAL_SUCCESS
from stock_agent.domain.run_report import RunReport


class DummySettings:
    enable_sqlite_history = False
    enable_excel_report = False
    news_lookback_days = 7
    resolved_report_output_dir = Path(".")


class DummyArgs:
    output = None
    output_dir = None
    top = 5
    tickers = ["TCS.NS"]
    preset = None
    universe = Path("unused.txt")
    interval_seconds = 1
    max_cycles = None


def test_execute_run_returns_partial_success_code(monkeypatch):
    class DummyOrchestrator:
        def run(self, tickers, output_path):
            return RunReport(
                run_id="RUN-123",
                total_requested=1,
                succeeded=0,
                failed=1,
                skipped=0,
                degraded_sources=[],
                provider_issues=[],
                ticker_results=[],
                status="PARTIAL_SUCCESS",
                warning_severity="LOW",
                output_file_path=None,
            )

    monkeypatch.setattr("stock_agent.cli._load_tickers", lambda _args: ["TCS.NS"])
    monkeypatch.setattr("stock_agent.cli.StockAnalysisService", lambda market_data_provider, news_provider: object())
    monkeypatch.setattr("stock_agent.cli.get_market_data_provider", lambda: object())
    monkeypatch.setattr("stock_agent.cli.get_news_provider", lambda: object())
    monkeypatch.setattr("stock_agent.cli.StockAnalysisRunOrchestrator", lambda **kwargs: DummyOrchestrator())
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: None)

    exit_code = _execute_run(DummyArgs(), DummySettings())

    assert exit_code == PARTIAL_SUCCESS


def test_execute_watch_stops_after_max_cycles(monkeypatch):
    args = DummyArgs()
    args.max_cycles = 2

    calls = []
    monkeypatch.setattr("stock_agent.cli._execute_run", lambda _args, _settings: calls.append("run") or PARTIAL_SUCCESS)
    monkeypatch.setattr("stock_agent.cli.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: None)

    exit_code = _execute_watch(args, DummySettings())

    assert exit_code == PARTIAL_SUCCESS
    assert calls == ["run", "run"]
