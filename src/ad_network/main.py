from __future__ import annotations

import asyncio
import logging

from .application.runtime import ApplicationRuntime
from .bootstrap import configure_logging, init_database
from .bots import build_admin_bot, build_owner_bot, build_user_bot
from .core.account_runtime import ListAccountRuntime
from .core.config import get_settings
from .core.list_accounts import ListAccountResolver
from .core.network_worker import NetworkWorker

logger = logging.getLogger(__name__)


async def create_runtime(settings) -> ApplicationRuntime:
    """Build the complete application graph in one explicit composition root."""
    account_resolver = ListAccountResolver()
    account_runtime = ListAccountRuntime(account_resolver)
    worker = NetworkWorker(account_resolver)

    logger.info("[BOOT] Building user bot")
    user_bot = await build_user_bot(settings)
    logger.info("[BOOT] Building admin bot")
    admin_bot = await build_admin_bot(settings, account_resolver, account_runtime)
    logger.info("[BOOT] Building owner bot")
    owner_bot = await build_owner_bot(settings)
    logger.info("[BOOT] All bots built")

    return ApplicationRuntime(
        user_bot=user_bot,
        admin_bot=admin_bot,
        owner_bot=owner_bot,
        account_resolver=account_resolver,
        account_runtime=account_runtime,
        worker=worker,
        account_sync_seconds=settings.list_account_sync_seconds,
    )


def validate_settings(settings) -> None:
    """Fail fast before opening database connections or creating network clients."""
    required_tokens = {
        "USER_BOT_TOKEN": settings.user_bot_token,
        "ADMIN_BOT_TOKEN": settings.admin_bot_token,
        "OWNER_BOT_TOKEN": settings.owner_bot_token,
    }
    missing = [name for name, value in required_tokens.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    required_usernames = {
        "OWNER_USERNAME": settings.owner_username,
        "ADMIN_USERNAME": settings.admin_username,
    }
    missing = [name for name, value in required_usernames.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


async def main() -> None:
    configure_logging()
    settings = get_settings()
    validate_settings(settings)

    await init_database()
    logger.info("[BOOT] Database ready")
    logger.info("Starting three-bot Rubika advertising network with MAXRubika")

    runtime = await create_runtime(settings)
    try:
        await runtime.run()
    finally:
        await runtime.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
