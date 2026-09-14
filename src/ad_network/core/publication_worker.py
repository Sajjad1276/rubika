import asyncio
import logging
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..adapters.rubika import MaxRubikaGateway, RubikaGateway
from .list_accounts import ListAccountResolver, ListAccountService
from .models import Channel
from .publisher import PublicationService, RotationExecutor

logger = logging.getLogger(__name__)


class PublicationWorker:
    """Compatibility worker for applications that run publication separately."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        account_resolver: ListAccountResolver,
        source_resolver: Callable[[object, object], Awaitable[tuple[str, str]]],
    ):
        self.session_factory = session_factory
        self.account_resolver = account_resolver
        self.source_resolver = source_resolver

    async def run_once(self, *, limit: int = 20) -> int:
        published = 0
        async with self.session_factory() as db:
            service = PublicationService(db)
            targets = await service.due_targets(limit=limit)
            for target in targets:
                try:
                    account = await ListAccountService(db).require_active(target.list_id)
                    client = self.account_resolver.resolve(account)
                    gateway: RubikaGateway = MaxRubikaGateway(client)
                    source_guid, source_message_id = await self.source_resolver(target, client)
                    channel = await db.get(Channel, target.channel_id)
                    if channel is None:
                        await service.mark_failed(target)
                        continue
                    if await RotationExecutor(db, gateway).execute(
                        target,
                        source_guid=source_guid,
                        source_message_id=source_message_id,
                    ):
                        published += 1
                except Exception:
                    logger.exception("publication target failed: %s", target.id)
                    if target.status == "running":
                        await service.mark_failed(target)
            await db.commit()
        return published

    async def run_forever(self, *, interval_seconds: float = 5.0, limit: int = 20) -> None:
        while True:
            await self.run_once(limit=limit)
            await asyncio.sleep(max(1.0, interval_seconds))
