import asyncio
import logging

from sqlalchemy import select

from .bootstrap import configure_logging, init_database
from .bots import build_admin_bot, build_owner_bot, build_user_bot
from .core.account_runtime import ListAccountRuntime
from .core.config import get_settings
from .core.db import SessionFactory
from .core.list_accounts import ListAccountResolver
from .core.models import ListAccount
from .core.network_worker import NetworkWorker


async def connect_active_list_accounts(runtime: ListAccountRuntime) -> None:
    async with SessionFactory() as db:
        accounts = (
            await db.scalars(
                select(ListAccount)
                .where(ListAccount.active.is_(True))
                .order_by(ListAccount.id)
            )
        ).all()

    for account in accounts:
        try:
            await runtime.connect(account)
        except Exception:
            logging.exception("Failed to connect List account %s", account.id)


async def main() -> None:
    configure_logging()
    settings = get_settings()

    if not all((settings.user_bot_token, settings.admin_bot_token, settings.owner_bot_token)):
        raise RuntimeError(
            "USER_BOT_TOKEN, ADMIN_BOT_TOKEN and OWNER_BOT_TOKEN must all be configured"
        )
    if not settings.owner_id:
        raise RuntimeError("OWNER_ID must be configured")

    await init_database()
    logging.info("Starting three-bot Rubika advertising network")

    account_resolver = ListAccountResolver()
    account_runtime = ListAccountRuntime(account_resolver)
    await connect_active_list_accounts(account_runtime)
    worker = NetworkWorker(account_resolver)

    user_bot = await build_user_bot(settings)
    admin_bot = await build_admin_bot(settings, account_resolver)
    owner_bot = await build_owner_bot(settings)

    tasks = [
        asyncio.create_task(user_bot.run(), name="user-bot"),
        asyncio.create_task(admin_bot.run(), name="admin-bot"),
        asyncio.create_task(owner_bot.run(), name="owner-bot"),
        asyncio.create_task(worker.run(), name="network-worker"),
    ]

    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        for task in done:
            exc = task.exception()
            if exc is not None:
                raise exc
        await asyncio.gather(*pending)
    finally:
        await worker.stop()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        for account_id in list(account_resolver.clients):
            try:
                await account_runtime.disconnect(account_id)
            except Exception:
                logging.exception("Failed to disconnect List account %s", account_id)


if __name__ == "__main__":
    asyncio.run(main())
