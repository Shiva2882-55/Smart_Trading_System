from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_agent.services.analysis_service import StockAnalysisService
from stock_agent.services.run_orchestrator import StockAnalysisRunOrchestrator
from stock_agent.services.run_report_service import RunReportService
from tests.fakes import FakeReportProvider, InMemoryRunRepository


@pytest.fixture
def build_orchestrator(tmp_path):
    def _build_orchestrator(market_provider, news_provider):
        ticker_service = StockAnalysisService(
            market_data_provider=market_provider,
            news_provider=news_provider,
        )
        report_provider = FakeReportProvider(output_dir=tmp_path / "reports")
        run_repository = InMemoryRunRepository()
        orchestrator = StockAnalysisRunOrchestrator(
            ticker_analysis_service=ticker_service,
            report_provider=report_provider,
            run_repository=run_repository,
            run_report_service=RunReportService(),
            lookback_days=7,
            top_n=5,
            enable_excel_report=True,
            enable_sqlite_history=True,
        )
        return orchestrator, report_provider, run_repository

    return _build_orchestrator
