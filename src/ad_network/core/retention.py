from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Channel, Violation


class RetentionService:
    """Evaluates whether a published ad is still present after its retention window."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def due_at(published_at: datetime, retention_hours: int) -> datetime:
        return published_at + timedelta(hours=retention_hours)

    async def record_early_deletion(
        self,
        *,
        channel_id: str,
        admin_id: str | None,
        note: str | None = None,
    ) -> Violation:
        violation = Violation(
            channel_id=channel_id,
            admin_id=admin_id,
            violation_type="early_ad_deletion",
            severity=2,
            note=note,
        )
        self.db.add(violation)
        await self.db.flush()
        return violation

    async def should_be_retained(self, published_at: datetime, retention_hours: int) -> bool:
        now = datetime.now(timezone.utc)
        return now < self.due_at(published_at, retention_hours)

    async def channel_is_active(self, channel_id: str) -> bool:
        channel = await self.db.scalar(select(Channel).where(Channel.id == channel_id))
        return bool(channel and channel.status.value == "active")
