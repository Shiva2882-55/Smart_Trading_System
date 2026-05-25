from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from stock_agent.config import get_settings
from stock_agent.provider_utils import validate_india_ticker
from stock_agent.models import Recommendation, StockAnalysisResult
from stock_agent.providers.base import MarketDataProvider, NewsProvider
from stock_agent.providers.factory import get_market_data_provider, get_news_provider
from stock_agent.scoring import score_stock
from stock_agent.services.analysis_service import StockAnalysisService


logger = logging.getLogger(__name__)


class StockResearchAgent:
    def __init__(
        self,
        lookback_days: int | None = None,
        market_data_provider: MarketDataProvider | None = None,
        news_provider: NewsProvider | None = None,
    ) -> None:
        settings = get_settings()
        self.lookback_days = lookback_days or settings.news_lookback_days
        self.last_failures: list[str] = []
        self.last_results: list[StockAnalysisResult] = []
        self.analysis_service = StockAnalysisService(
            market_data_provider=market_data_provider or get_market_data_provider(),
            news_provider=news_provider or get_news_provider(),
        )

    def load_universe(self, path: Path) -> list[str]:
        if not path.exists():
            raise FileNotFoundError(f"Universe file was not found: {path}")

        tickers: list[str] = []
        seen: set[str] = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            raw_value = line.split("#", 1)[0].strip()
            if not raw_value:
                continue
            ticker = validate_india_ticker(raw_value)
            if ticker in seen:
                continue
            seen.add(ticker)
            tickers.append(ticker)
        if not tickers:
            raise ValueError(f"Universe file is empty after filtering comments and blanks: {path}")
        return tickers

    def load_preset_universe(self, preset: str) -> list[str]:
        normalized = preset.lower().strip()
        if normalized == "nifty50":
            return self.load_universe(get_settings().resolved_default_universe)
        raise ValueError(f"Unsupported preset universe: {preset}. Only India presets are allowed.")

    def analyze(self, tickers: list[str]) -> tuple[list[Recommendation], dict[str, list[Recommendation]]]:
        market = self.analysis_service.get_market_context()
        self.last_failures = []
        self.last_results = []
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

        snapshots = []
        for ticker in normalized_tickers:
            result = self.analysis_service.analyze_ticker(ticker, self.lookback_days)
            self.last_results.append(result)
            if result.snapshot is None:
                self.last_failures.append(f"{ticker}: {result.error or 'Unknown analysis failure'}")
                continue
            snapshots.append(result.snapshot)

        if not snapshots:
            raise RuntimeError("No stocks could be analyzed. Check internet access, ticker symbols, or data source availability.")
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
