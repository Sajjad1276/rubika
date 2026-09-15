from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.rubika import MaxRubikaGateway
from ..core.campaigns import Campaign, CampaignTarget
from ..core.db import SessionFactory
from ..core.list_accounts import ListAccountResolver
from ..core.models import ListAccount
from ..core.publisher import PublicationService, RotationExecutor
from ..core.retention_monitor import RetentionMonitor

logger = logging.getLogger(__name__)
GatewayFactory = Callable[[object], MaxRubikaGateway]


class NetworkWorker:
    """Infrastructure worker that executes application use cases on a schedule."""

    def __init__(
        self,
        accounts: ListAccountResolver,
        *,
        interval_seconds: float = 5.0,
        gateway_factory: GatewayFactory = MaxRubikaGateway,
    ):
        self.accounts = accounts
        self.interval_seconds = max(1.0, interval_seconds)
        self.gateway_factory = gateway_factory
        self._stop = asyncio.Event()

    async def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        logger.info("Network worker started")
        while not self._stop.is_set():
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Network worker tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue
        logger.info("Network worker stopped")

    async def tick(self) -> None:
        async with SessionFactory() as db:
            await self._publish_due(db)
            await self._check_retention(db)
            await self._reconcile_campaigns(db)
            await db.commit()

    async def _publish_due(self, db: AsyncSession) -> None:
        targets = await PublicationService(db).due_targets(limit=50)
        for target in targets:
            account = await self._account_for_list(db, target.list_id)
            if account is None:
                logger.warning("No active List account for list %s", target.list_id)
                continue
            client = self.accounts.clients.get(account.id)
            if client is None:
                logger.warning("List account %s is offline", account.id)
                continue

            campaign = await db.get(Campaign, target.campaign_id)
            if campaign is None:
                logger.error("Target %s references missing campaign %s", target.id, target.campaign_id)
                await PublicationService(db).mark_failed(target)
                continue

            try:
                source_guid, source_message_id = self._parse_content_ref(campaign.content_ref)
                gateway = self.gateway_factory(client)
                await RotationExecutor(db, gateway).execute(
                    target,
                    source_guid=source_guid,
                    source_message_id=source_message_id,
                )
            except Exception:
                logger.exception("Unable to publish target %s", target.id)

    async def _check_retention(self, db: AsyncSession) -> None:
        result = await db.scalars(
            select(CampaignTarget)
            .where(
                CampaignTarget.status == "published",
                CampaignTarget.published_message_id.is_not(None),
            )
            .order_by(CampaignTarget.published_at, CampaignTarget.id)
            .limit(100)
        )
        for target in result.all():
            account = await self._account_for_list(db, target.list_id)
            if account is None or account.id not in self.accounts.clients:
                continue
            try:
                gateway = self.gateway_factory(self.accounts.clients[account.id])
                await RetentionMonitor(db, gateway).check(target)
            except Exception:
                logger.exception("Retention check failed for target %s", target.id)

    async def _reconcile_campaigns(self, db: AsyncSession) -> None:
        rows = await db.execute(
            select(
                Campaign.id,
                func.count(CampaignTarget.id).label("target_count"),
                func.sum((CampaignTarget.status == "retained").cast(int)).label("retained_count"),
                func.sum((CampaignTarget.status == "failed").cast(int)).label("failed_count"),
                func.sum((CampaignTarget.status.in_(["published", "running"])).cast(int)).label(
                    "active_count"
                ),
            )
            .join(CampaignTarget, CampaignTarget.campaign_id == Campaign.id)
            .where(Campaign.status.in_(["scheduled", "active"]))
            .group_by(Campaign.id)
        )

        for campaign_id, target_count, retained_count, failed_count, active_count in rows:
            campaign = await db.get(Campaign, campaign_id)
            if campaign is None or not target_count:
                continue
            retained_count = int(retained_count or 0)
            failed_count = int(failed_count or 0)
            active_count = int(active_count or 0)
            if retained_count + failed_count == target_count:
                campaign.status = "completed" if retained_count else "failed"
            elif active_count:
                campaign.status = "active"

    async def _account_for_list(self, db: AsyncSession, list_id: str) -> ListAccount | None:
        return await db.scalar(
            select(ListAccount)
            .where(ListAccount.list_id == list_id, ListAccount.active.is_(True))
            .order_by(ListAccount.id)
        )

    @staticmethod
    def _parse_content_ref(content_ref: str) -> tuple[str, str]:
        value = content_ref.strip()
        if not value or ":" not in value:
            raise ValueError("campaign content_ref must be '<source_guid>:<source_message_id>'")
        source_guid, source_message_id = value.rsplit(":", 1)
        if not source_guid or not source_message_id:
            raise ValueError("campaign content_ref contains an empty source identifier")
        return source_guid, source_message_id
