import asyncio
import logging

from sqlalchemy import select

from ..adapters.rubika import MaxRubikaGateway
from .campaigns import Campaign, CampaignTarget
from .db import SessionFactory
from .list_accounts import ListAccountResolver
from .models import ListAccount
from .publisher import PublicationService, RotationExecutor
from .retention_monitor import RetentionMonitor

logger = logging.getLogger(__name__)


class NetworkWorker:
    """Runs publication, retention and campaign lifecycle checks."""

    def __init__(self, accounts: ListAccountResolver, *, interval_seconds: float = 5.0):
        self.accounts = accounts
        self.interval_seconds = max(1.0, interval_seconds)
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
                logger.exception("network worker tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                pass
        logger.info("Network worker stopped")

    async def tick(self) -> None:
        async with SessionFactory() as db:
            await self._publish_due(db)
            await self._check_retention(db)
            await self._reconcile_campaigns(db)
            await db.commit()

    async def _publish_due(self, db) -> None:
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
                continue
            try:
                source_guid, source_message_id = self._parse_content_ref(campaign.content_ref)
                gateway = MaxRubikaGateway(client)
                await RotationExecutor(db, gateway).execute(
                    target,
                    source_guid=source_guid,
                    source_message_id=source_message_id,
                )
            except Exception:
                logger.exception("Unable to publish target %s", target.id)

    async def _check_retention(self, db) -> None:
        result = await db.scalars(
            select(CampaignTarget).where(
                CampaignTarget.status == "published",
                CampaignTarget.published_message_id.is_not(None),
            ).limit(100)
        )
        for target in result.all():
            account = await self._account_for_list(db, target.list_id)
            if account is None or account.id not in self.accounts.clients:
                continue
            try:
                gateway = MaxRubikaGateway(self.accounts.clients[account.id])
                await RetentionMonitor(db, gateway).check(target)
            except Exception:
                logger.exception("Retention check failed for target %s", target.id)

    async def _reconcile_campaigns(self, db) -> None:
        campaigns = await db.scalars(
            select(Campaign).where(Campaign.status.in_(["scheduled", "active"]))
        )
        for campaign in campaigns.all():
            targets = list((await db.scalars(
                select(CampaignTarget).where(CampaignTarget.campaign_id == campaign.id)
            )).all())
            if not targets:
                continue
            statuses = {target.status for target in targets}
            if statuses == {"retained"}:
                campaign.status = "completed"
            elif any(status in {"published", "retained", "running"} for status in statuses):
                campaign.status = "active"

    async def _account_for_list(self, db, list_id: str) -> ListAccount | None:
        return await db.scalar(
            select(ListAccount)
            .where(ListAccount.list_id == list_id, ListAccount.active.is_(True))
            .order_by(ListAccount.id)
        )

    @staticmethod
    def _parse_content_ref(content_ref: str) -> tuple[str, str]:
        value = content_ref.strip()
        if ":" not in value:
            raise ValueError("campaign content_ref must be '<source_guid>:<source_message_id>'")
        source_guid, source_message_id = value.rsplit(":", 1)
        if not source_guid or not source_message_id:
            raise ValueError("campaign content_ref contains an empty source identifier")
        return source_guid, source_message_id
