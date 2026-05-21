from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(slots=True)
class Settings:
    default_universe: Path = ROOT / os.getenv("DEFAULT_UNIVERSE", "watchlists/core_watchlist.txt")
    news_lookback_days: int = int(os.getenv("NEWS_LOOKBACK_DAYS", "7"))
    top_n: int = int(os.getenv("TOP_N", "10"))
    default_exchange_suffix: str = os.getenv("DEFAULT_EXCHANGE_SUFFIX", ".NS")


settings = Settings()
