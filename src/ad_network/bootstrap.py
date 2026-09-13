import logging

from .core.db import engine
from .core.models import Base
from .core import campaigns as _campaigns  # noqa: F401
from .core import commerce as _commerce  # noqa: F401


async def init_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
