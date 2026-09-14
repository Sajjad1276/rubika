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

BOT_RETRY_DELAY_SECONDS = 5
POLL_INTERVAL_SECONDS = 0.05


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


async def run_bot_isolated(name: str, bot, stop: asyncio.Event) -> None:
    """Run one MAXRubika bot with isolated restart handling."""
    while not stop.is_set():
        try:
            logging.info("[%s] MAXRubika polling loop started", name)
            await bot.start(poll_interval=POLL_INTERVAL_SECONDS)
            if not stop.is_set():
                logging.warning("[%s] polling loop stopped; restarting", name)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("[%s] polling loop failed; retrying in %ss", name, BOT_RETRY_DELAY_SECONDS)
        if not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=BOT_RETRY_DELAY_SECONDS)
            except asyncio.TimeoutError:
                pass


async def main() -> None:
    configure_logging()
    settings = get_settings()
    await init_database()
    logging.info("[BOOT] Database ready")

    if not all((settings.user_bot_token, settings.admin_bot_token, settings.owner_bot_token)):
        raise RuntimeError("USER_BOT_TOKEN, ADMIN_BOT_TOKEN and OWNER_BOT_TOKEN must all be configured")
    if not settings.owner_username or not settings.admin_username:
        raise RuntimeError("OWNER_USERNAME and ADMIN_USERNAME must be configured")

    logging.info("Starting three-bot Rubika advertising network with MAXRubika")

    account_resolver = ListAccountResolver()
    account_runtime = ListAccountRuntime(account_resolver)
    worker = NetworkWorker(account_resolver)
    stop = asyncio.Event()

    active_list_accounts = await load_active_list_accounts()
    logging.info("[BOOT] Loaded %d active List accounts", len(active_list_accounts))
    await account_runtime.sync_active_accounts(active_list_accounts)
    logging.info("[BOOT] List account runtime synchronized")

    logging.info("[BOOT] Building user bot")
    user_bot = await build_user_bot(settings)
    logging.info("[BOOT] Building admin bot")
    admin_bot = await build_admin_bot(settings, account_resolver, account_runtime)
    logging.info("[BOOT] Building owner bot")
    owner_bot = await build_owner_bot(settings)
    logging.info("[BOOT] All bots built")

    tasks = [
        asyncio.create_task(run_bot_isolated("user", user_bot, stop), name="user-bot"),
        asyncio.create_task(run_bot_isolated("admin", admin_bot, stop), name="admin-bot"),
        asyncio.create_task(run_bot_isolated("owner", owner_bot, stop), name="owner-bot"),
        asyncio.create_task(worker.run(), name="network-worker"),
        asyncio.create_task(sync_list_accounts(account_runtime, stop), name="list-account-sync"),
    ]

    try:
        await asyncio.gather(*tasks)
    finally:
        stop.set()
        await worker.stop()
        for bot in (user_bot, admin_bot, owner_bot):
            close = getattr(bot, "close", None)
            if callable(close):
                try:
                    await close()
                except Exception:
                    logging.exception("Failed to close MAXRubika bot")
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
