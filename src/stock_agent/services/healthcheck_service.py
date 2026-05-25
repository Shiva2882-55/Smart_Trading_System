from __future__ import annotations

from stock_agent.config import get_settings
from stock_agent.persistence.database import init_db


class HealthcheckService:
    def run(self) -> str:
        settings = get_settings()
        settings.validate_startup_files(require_universe=False)
        if settings.enable_sqlite_history:
            init_db()
        return "Healthcheck passed"
