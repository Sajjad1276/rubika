import asyncio
import logging
import subprocess


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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
