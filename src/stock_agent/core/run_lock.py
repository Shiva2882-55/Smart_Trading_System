from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path


class RunLockError(Exception):
    pass


@contextmanager
def run_lock(lock_file: Path, stale_after_seconds: int = 6 * 60 * 60):
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()

    if lock_file.exists():
        try:
            lock_data = json.loads(lock_file.read_text(encoding="utf-8"))
            created_at = float(lock_data.get("created_at", 0))
        except Exception:
            created_at = 0

        lock_age = now - created_at
        if lock_age < stale_after_seconds:
            raise RunLockError(f"Another stock-agent run is already active. Lock file: {lock_file}")
        lock_file.unlink(missing_ok=True)

    lock_payload = {
        "pid": os.getpid(),
        "created_at": now,
        "created_at_readable": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    try:
        fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(lock_payload, file, indent=2)
        yield
    except FileExistsError as exc:
        raise RunLockError(f"Another stock-agent run is already active. Lock file: {lock_file}") from exc
    finally:
        lock_file.unlink(missing_ok=True)
