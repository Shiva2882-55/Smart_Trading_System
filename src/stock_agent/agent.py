from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from stock_agent.config import settings
from stock_agent.data_sources import fetch_market_context, fetch_stock_snapshot, validate_india_ticker
from stock_agent.models import Recommendation
from stock_agent.scoring import score_stock


class StockResearchAgent:
    def __init__(self, lookback_days: int | None = None) -> None:
        self.lookback_days = lookback_days or settings.news_lookback_days
        self.last_failures: list[str] = []

    def load_universe(self, path: Path) -> list[str]:
        tickers: list[str] = []
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            tickers.append(validate_india_ticker(line))
        return tickers

    def load_preset_universe(self, preset: str) -> list[str]:
        normalized = preset.lower().strip()
        if normalized == "nifty50":
            return self.load_universe(settings.default_universe)
        raise ValueError(f"Unsupported preset universe: {preset}. Only India presets are allowed.")

    def analyze(self, tickers: list[str]) -> tuple[list[Recommendation], dict[str, list[Recommendation]]]:
        market = fetch_market_context()
        self.last_failures = []
        normalized_tickers: list[str] = []
        for ticker in tickers:
            try:
                normalized_tickers.append(validate_india_ticker(ticker))
            except Exception as exc:
                self.last_failures.append(f"{ticker}: {exc}")

        snapshots = []
        for ticker in normalized_tickers:
            try:
                snapshots.append(fetch_stock_snapshot(ticker, self.lookback_days))
            except Exception as exc:
                self.last_failures.append(f"{ticker}: {exc}")

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
