import asyncio
import logging

from .bootstrap import configure_logging, init_database
from .bots import build_admin_bot, build_owner_bot, build_user_bot
from .core.config import get_settings


async def main() -> None:
    configure_logging()
    settings = get_settings()
    await init_database()

    if not all((settings.user_bot_token, settings.admin_bot_token, settings.owner_bot_token)):
        raise RuntimeError(
            "USER_BOT_TOKEN, ADMIN_BOT_TOKEN and OWNER_BOT_TOKEN must all be configured"
        )

    logging.info("Starting three-bot Rubika advertising network")
    user_bot = await build_user_bot(settings)
    admin_bot = await build_admin_bot(settings)
    owner_bot = await build_owner_bot(settings)

    await asyncio.gather(
        user_bot.run(),
        admin_bot.run(),
        owner_bot.run(),
    )


if __name__ == "__main__":
    asyncio.run(main())
