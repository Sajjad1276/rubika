from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return one canonical, timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)
