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


async def load_active_list_accounts() -> list[ListAccount]:
    async with SessionFactory() as db:
        return list((await db.scalars(
            select(ListAccount).where(ListAccount.active.is_(True)).order_by(ListAccount.id)
        )).all())


async def sync_list_accounts(runtime: ListAccountRuntime, stop: asyncio.Event) -> None:
    interval = max(5.0, get_settings().list_account_sync_seconds)
    while not stop.is_set():
        try:
            await runtime.sync_active_accounts(await load_active_list_accounts())
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("List account reconciliation failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


async def prepare_bot(bot) -> None:
    """Initialize FastRub before enabling decorators registered by the builders.

    FastRub initializes its update flags during start(). The project builders
    register handlers before run(), so run() would otherwise reset those flags
    and raise "No update types selected". Starting here preserves the already
    registered handlers and explicitly enables the polling/button update loops.
    """
    await bot.start()
    bot._fetch_messages_polling = True
    bot._fetch_buttons = True


async def main() -> None:
    configure_logging()
    settings = get_settings()
    await init_database()

    if not all((settings.user_bot_token, settings.admin_bot_token, settings.owner_bot_token)):
        raise RuntimeError("USER_BOT_TOKEN, ADMIN_BOT_TOKEN and OWNER_BOT_TOKEN must all be configured")
    if not settings.owner_id:
        raise RuntimeError("OWNER_ID must be configured")

    logging.info("Starting three-bot Rubika advertising network")

    account_resolver = ListAccountResolver()
    account_runtime = ListAccountRuntime(account_resolver)
    worker = NetworkWorker(account_resolver)
    stop = asyncio.Event()

    await account_runtime.sync_active_accounts(await load_active_list_accounts())

    user_bot = await build_user_bot(settings)
    admin_bot = await build_admin_bot(settings, account_resolver, account_runtime)
    owner_bot = await build_owner_bot(settings)

    await asyncio.gather(
        prepare_bot(user_bot),
        prepare_bot(admin_bot),
        prepare_bot(owner_bot),
    )

    tasks = [
        asyncio.create_task(user_bot.run(), name="user-bot"),
        asyncio.create_task(admin_bot.run(), name="admin-bot"),
        asyncio.create_task(owner_bot.run(), name="owner-bot"),
        asyncio.create_task(worker.run(), name="network-worker"),
        asyncio.create_task(sync_list_accounts(account_runtime, stop), name="list-account-sync"),
    ]

    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        for task in done:
            error = task.exception()
            if error is not None:
                raise error
        await asyncio.gather(*pending)
    finally:
        stop.set()
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
