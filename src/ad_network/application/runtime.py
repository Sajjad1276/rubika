from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select

from ..core.db import SessionFactory
from ..core.list_accounts import ListAccountResolver
from ..core.models import ListAccount
from ..core.network_worker import NetworkWorker

logger = logging.getLogger(__name__)

BOT_RETRY_DELAY_SECONDS = 5.0
POLL_INTERVAL_SECONDS = 0.05


async def load_active_list_accounts() -> list[ListAccount]:
    async with SessionFactory() as db:
        result = await db.scalars(
            select(ListAccount)
            .where(ListAccount.active.is_(True))
            .order_by(ListAccount.id)
        )
        return list(result.all())


class BotSupervisor:
    """Own lifecycle, restart policy and shutdown for one long-running bot."""

    def __init__(
        self,
        name: str,
        bot: Any,
        stop: asyncio.Event,
        *,
        retry_delay: float = BOT_RETRY_DELAY_SECONDS,
        poll_interval: float = POLL_INTERVAL_SECONDS,
    ):
        self.name = name
        self.bot = bot
        self.stop = stop
        self.retry_delay = max(0.1, retry_delay)
        self.poll_interval = max(0.01, poll_interval)

    async def run(self) -> None:
        while not self.stop.is_set():
            try:
                logger.info("[%s] MAXRubika polling loop started", self.name)
                await self.bot.start(poll_interval=self.poll_interval)
                if not self.stop.is_set():
                    logger.warning("[%s] polling loop stopped; restarting", self.name)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "[%s] polling failed; retrying in %.1fs",
                    self.name,
                    self.retry_delay,
                )
            await self._sleep_or_stop()

    async def _sleep_or_stop(self) -> None:
        if self.stop.is_set():
            return
        try:
            await asyncio.wait_for(self.stop.wait(), timeout=self.retry_delay)
        except asyncio.TimeoutError:
            pass


class ApplicationRuntime:
    """Composition root for bots, account runtime and background workers."""

    def __init__(
        self,
        *,
        user_bot: Any,
        admin_bot: Any,
        owner_bot: Any,
        account_resolver: ListAccountResolver,
        account_runtime: Any,
        worker: NetworkWorker,
        account_sync_seconds: float,
    ):
        self.user_bot = user_bot
        self.admin_bot = admin_bot
        self.owner_bot = owner_bot
        self.account_resolver = account_resolver
        self.account_runtime = account_runtime
        self.worker = worker
        self.account_sync_seconds = max(5.0, account_sync_seconds)
        self.stop = asyncio.Event()
        self._tasks: list[asyncio.Task[Any]] = []

    async def run(self) -> None:
        await self._sync_accounts_once()
        self._tasks = [
            asyncio.create_task(BotSupervisor("user", self.user_bot, self.stop).run(), name="user-bot"),
            asyncio.create_task(BotSupervisor("admin", self.admin_bot, self.stop).run(), name="admin-bot"),
            asyncio.create_task(BotSupervisor("owner", self.owner_bot, self.stop).run(), name="owner-bot"),
            asyncio.create_task(self.worker.run(), name="network-worker"),
            asyncio.create_task(self._sync_accounts_loop(), name="list-account-sync"),
        ]
        await asyncio.gather(*self._tasks)

    async def _sync_accounts_once(self) -> None:
        accounts = await load_active_list_accounts()
        logger.info("[BOOT] Loaded %d active List accounts", len(accounts))
        await self.account_runtime.sync_active_accounts(accounts)
        logger.info("[BOOT] List account runtime synchronized")

    async def _sync_accounts_loop(self) -> None:
        while not self.stop.is_set():
            try:
                await self._sync_accounts_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("List account reconciliation failed")
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=self.account_sync_seconds)
            except asyncio.TimeoutError:
                pass

    async def shutdown(self) -> None:
        self.stop.set()
        await self.worker.stop()
        for bot in (self.user_bot, self.admin_bot, self.owner_bot):
            close = getattr(bot, "close", None)
            if not callable(close):
                continue
            try:
                await close()
            except Exception:
                logger.exception("Failed to close MAXRubika bot")

        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        for account_id in list(self.account_resolver.clients):
            try:
                await self.account_runtime.disconnect(account_id)
            except Exception:
                logger.exception("Failed to disconnect List account %s", account_id)
