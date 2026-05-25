from pathlib import Path

import pytest

from stock_agent.core.run_lock import RunLockError, run_lock


def test_run_lock_blocks_overlapping_active_lock(tmp_path: Path):
    lock_file = tmp_path / "stock_agent.lock"

    with run_lock(lock_file):
        with pytest.raises(RunLockError):
            with run_lock(lock_file):
                pass


def test_run_lock_removes_stale_lock(tmp_path: Path):
    lock_file = tmp_path / "stock_agent.lock"
    lock_file.write_text('{"created_at": 1}', encoding="utf-8")

    with run_lock(lock_file, stale_after_seconds=1):
        assert lock_file.exists()

    assert not lock_file.exists()
