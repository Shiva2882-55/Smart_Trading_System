from __future__ import annotations

from stock_agent.persistence.run_repository import RunRepository as PersistenceRunRepository
from stock_agent.providers.base import RunRepository


class SQLiteRunRepository(PersistenceRunRepository, RunRepository):
    """SQLite-backed run repository adapter."""
