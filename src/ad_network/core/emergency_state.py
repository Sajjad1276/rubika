from __future__ import annotations

_worker_paused = False


def set_worker_paused(value: bool) -> None:
    global _worker_paused
    _worker_paused = bool(value)


def worker_paused() -> bool:
    return _worker_paused
