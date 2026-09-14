import asyncio
import logging
import subprocess

from .core.config import get_settings


def _run_migrations() -> None:
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Database migration failed: "
            + (result.stderr.strip() or result.stdout.strip() or "unknown error")
        )


async def init_database() -> None:
    await asyncio.to_thread(_run_migrations)


def configure_logging() -> None:
    level_name = get_settings().log_level.upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )
