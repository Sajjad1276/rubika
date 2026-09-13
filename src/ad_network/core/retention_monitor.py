from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..adapters.rubika import RubikaGateway
from .campaigns import Campaign, CampaignTarget
from .models import Channel, ChannelStatus, Violation


class RetentionMonitor:
    """Checks published messages after the campaign retention window."""

    def __init__(self, db: AsyncSession, gateway: RubikaGateway):
        self.db = db
        self.gateway = gateway

    async def due_targets(self, limit: int = 100) -> list[CampaignTarget]:
        now = datetime.now(timezone.utc)
        result = await self.db.scalars(
            select(CampaignTarget).where(
                CampaignTarget.status == "published",
                CampaignTarget.published_at.is_not(None),
            ).order_by(CampaignTarget.published_at).limit(limit)
        )
        due: list[CampaignTarget] = []
        for target in result.all():
            campaign = await self.db.get(Campaign, target.campaign_id)
            if not campaign or not target.published_at:
                continue
            published = target.published_at
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if now >= published + timedelta(hours=campaign.retention_hours):
                due.append(target)
        return due

    @staticmethod
    def message_exists(raw: object) -> bool:
        if raw is None:
            return False
        if isinstance(raw, list):
            return bool(raw)
        if isinstance(raw, dict):
            return bool(raw.get("messages") or raw.get("message") or raw.get("data"))
        return True

    async def check(self, target: CampaignTarget) -> bool:
        channel = await self.db.get(Channel, target.channel_id)
        if channel is None or not target.published_message_id:
            return False
        raw = await self.gateway.get_message(channel.rubika_guid, target.published_message_id)
        if self.message_exists(raw):
            target.status = "retained"
            await self.db.flush()
            return True

        self.db.add(Violation(
            channel_id=channel.id,
            violation_type="early_ad_deletion",
            severity=2,
            note=f"message {target.published_message_id} missing during retention check",
        ))
        await self.db.flush()
        strikes = await self.db.scalar(select(func.count(Violation.id)).where(
            Violation.channel_id == channel.id,
            Violation.violation_type == "early_ad_deletion",
        ))
        if int(strikes or 0) >= 3:
            channel.status = ChannelStatus.REMOVED
            channel.list_id = None
        return False
