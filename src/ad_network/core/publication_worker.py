import asyncio
import logging
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..adapters.rubika import FastRubikaGateway, RubikaGateway
from .list_accounts import ListAccountResolver, ListAccountService
from .models import Channel
from .publisher import PublicationService

logger = logging.getLogger(__name__)


class PublicationWorker:
    """Background publisher that always uses the operational account of each List."""

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
                    gateway: RubikaGateway = (
                        client if isinstance(client, FastRubikaGateway)
                        else FastRubikaGateway(client)
                    )
                    source_guid, source_message_id = await self.source_resolver(target, client)
                    await service.claim(target)
                    channel = await db.get(Channel, target.channel_id)
                    if channel is None:
                        await service.mark_failed(target)
                        continue
                    result = await gateway.forward(source_guid, channel.rubika_guid, source_message_id)
                    message_id = self._message_id(result)
                    if not message_id:
                        raise RuntimeError("Rubika forward response did not contain a message id")
                    await service.mark_published(target, message_id)
                    published += 1
                except Exception:
                    logger.exception("publication target failed: %s", target.id)
                    try:
                        await service.mark_failed(target)
                    except Exception:
                        logger.exception("failed to mark target failed: %s", target.id)
            await db.commit()
        return published

    @staticmethod
    def _message_id(result: object) -> str | None:
        if isinstance(result, dict):
            for key in ("message_id", "id"):
                value = result.get(key)
                if value:
                    return str(value)
            for key in ("messages", "message"):
                value = result.get(key)
                if isinstance(value, list) and value:
                    return PublicationWorker._message_id(value[0])
                if value:
                    return PublicationWorker._message_id(value)
        if isinstance(result, list) and result:
            return PublicationWorker._message_id(result[0])
        for key in ("message_id", "id"):
            value = getattr(result, key, None)
            if value:
                return str(value)
        return None

    async def run_forever(self, *, interval_seconds: float = 5.0, limit: int = 20) -> None:
        while True:
            await self.run_once(limit=limit)
            await asyncio.sleep(interval_seconds)
