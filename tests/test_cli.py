from datetime import datetime
from pathlib import Path

import pandas as pd

from stock_agent.agent import StockResearchAgent
from stock_agent.cli import _find_previous_report, _load_tickers, _resolve_output_path


def test_resolve_output_path_uses_timestamped_name_when_output_is_omitted(tmp_path: Path):
    resolved = _resolve_output_path(None, tmp_path, now=datetime(2026, 5, 25, 9, 7))

    assert resolved == tmp_path / "stock_analysis_25-05-26--09-07.xlsx"


def test_resolve_output_path_avoids_overwriting_existing_timestamped_report(tmp_path: Path):
    existing = tmp_path / "stock_analysis_25-05-26--09-07.xlsx"
    existing.write_text("placeholder", encoding="utf-8")

    resolved = _resolve_output_path(None, tmp_path, now=datetime(2026, 5, 25, 9, 7))

    assert resolved == tmp_path / "stock_analysis_25-05-26--09-07--01.xlsx"


def test_find_previous_report_ignores_current_output_and_uses_latest_available_report(tmp_path: Path):
    older = tmp_path / "stock_analysis_24-05-26--09-00.xlsx"
    older.write_text("older", encoding="utf-8")
    newer = tmp_path / "stock_analysis_25-05-26--08-45.xlsx"
    newer.write_text("newer", encoding="utf-8")
    current_target = tmp_path / "stock_analysis_25-05-26--09-07.xlsx"

    previous = _find_previous_report(current_target)

    assert previous == newer


def test_load_universe_filters_comments_and_duplicate_tickers(tmp_path: Path):
    universe_file = tmp_path / "watchlist.txt"
    universe_file.write_text("RELIANCE\n# comment\nTCS\nRELIANCE\n \nINFY # note\n", encoding="utf-8")

    agent = StockResearchAgent()
    tickers = agent.load_universe(universe_file)

    assert tickers == ["RELIANCE", "TCS", "INFY"]


class DummyArgs:
    def __init__(self, *, tickers=None, input_excel=None, preset=None, universe=None):
        self.tickers = tickers
        self.input_excel = input_excel
        self.preset = preset
        self.universe = universe


def test_load_tickers_understands_excel_report_input(tmp_path: Path):
    excel_path = tmp_path / "report.xlsx"
    pd.DataFrame(
        {
            "ticker": ["TCS.NS", "INFY.NS", "TCS.NS"],
            "company_name": ["TCS", "INFY", "TCS"],
        }
    ).to_excel(excel_path, sheet_name="All Ranked Stocks", index=False)

    args = DummyArgs(input_excel=[excel_path], universe=tmp_path / "unused.txt")

    tickers = _load_tickers(args)

    assert tickers == ["TCS.NS", "INFY.NS"]
    assert args._input_feedback["source"] == "excel"
    assert "All Ranked Stocks" in args._input_feedback["details"][0]


def test_load_tickers_uses_excel_universe_path_when_xlsx_is_passed(tmp_path: Path):
    excel_path = tmp_path / "leaders.xlsx"
    pd.DataFrame(
        {
            "leader_ticker": ["RELIANCE.NS", "HDFCBANK.NS"],
            "sector": ["Energy", "Financials"],
        }
    ).to_excel(excel_path, sheet_name="Sector Leaders", index=False)

    args = DummyArgs(input_excel=None, universe=excel_path)

    tickers = _load_tickers(args)

    assert tickers == ["RELIANCE.NS", "HDFCBANK.NS"]
    assert args._input_feedback["source"] == "excel"
