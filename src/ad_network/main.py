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

STARTUP_TIMEOUT_SECONDS = 45
BOT_RETRY_DELAY_SECONDS = 5


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


def configure_fastrub_http() -> None:
    """Force FastRub's Network transport to HTTP/1.1 before any client starts."""
    from fast_rub.network.network import Network

    if getattr(Network, "_ad_network_http1_patch", False):
        return

    original_build_client_kwargs = Network._build_client_kwargs

    def stable_client_kwargs(self):
        kwargs = original_build_client_kwargs(self)
        kwargs["http1"] = True
        kwargs["http2"] = False
        return kwargs

    Network._build_client_kwargs = stable_client_kwargs
    Network._ad_network_http1_patch = True


async def prepare_bot(name: str, bot) -> None:
    """Start FastRub with a bounded timeout and restore polling flags."""
    logging.info("[%s] starting FastRub client", name)
    try:
        await asyncio.wait_for(bot.start(), timeout=STARTUP_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        logging.error(
            "[%s] FastRub client.start() timed out after %.0fs",
            name,
            STARTUP_TIMEOUT_SECONDS,
        )
        raise RuntimeError(
            f"{name} bot startup timed out after {STARTUP_TIMEOUT_SECONDS}s"
        ) from exc
    bot._fetch_messages_polling = True
    bot._fetch_buttons = True
    logging.info("[%s] FastRub client started; polling flags restored", name)


async def run_bot_isolated(name: str, bot) -> None:
    """Keep one bot's polling failures isolated from the other bots."""
    while True:
        try:
            logging.info("[%s] polling loop started", name)
            await bot.run()
            logging.warning("[%s] polling loop stopped; restarting", name)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("[%s] polling loop failed; retrying in %ss", name, BOT_RETRY_DELAY_SECONDS)
        await asyncio.sleep(BOT_RETRY_DELAY_SECONDS)


async def main() -> None:
    configure_logging()
    settings = get_settings()
    await init_database()
    logging.info("[BOOT] Database ready")

    if not all((settings.user_bot_token, settings.admin_bot_token, settings.owner_bot_token)):
        raise RuntimeError("USER_BOT_TOKEN, ADMIN_BOT_TOKEN and OWNER_BOT_TOKEN must all be configured")
    if not settings.owner_id:
        raise RuntimeError("OWNER_ID must be configured")

    # Patch FastRub before ListAccountRuntime can create any user-bot clients.
    configure_fastrub_http()
    logging.info("[BOOT] FastRub HTTP transport configured")

    logging.info("Starting three-bot Rubika advertising network")

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

    await asyncio.gather(
        prepare_bot("user", user_bot),
        prepare_bot("admin", admin_bot),
        prepare_bot("owner", owner_bot),
    )
    logging.info("[BOOT] All three bots started")

    tasks = [
        asyncio.create_task(run_bot_isolated("user", user_bot), name="user-bot"),
        asyncio.create_task(run_bot_isolated("admin", admin_bot), name="admin-bot"),
        asyncio.create_task(run_bot_isolated("owner", owner_bot), name="owner-bot"),
        asyncio.create_task(worker.run(), name="network-worker"),
        asyncio.create_task(sync_list_accounts(account_runtime, stop), name="list-account-sync"),
    ]

    try:
        await asyncio.gather(*tasks)
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
