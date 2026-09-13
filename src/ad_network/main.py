import asyncio
from .bootstrap import configure_logging, init_database

async def main() -> None:
    configure_logging()
    await init_database()
    # User bot, admin bot and dashboard adapters attach here.
    # Domain/application services remain independent of interfaces.

if __name__ == "__main__":
    asyncio.run(main())
