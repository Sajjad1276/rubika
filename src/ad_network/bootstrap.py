import logging

from sqlalchemy import text

from .core.db import engine
from .core.models import Base


async def init_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
