import asyncio

from .bootstrap import configure_logging, init_database


async def main() -> None:
    configure_logging()
    await init_database()
    # Interface adapters (user bot/admin bot/dashboard) are attached here.
    # Business logic remains in application/domain services.


if __name__ == "__main__":
    asyncio.run(main())
