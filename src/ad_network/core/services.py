import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ListNetwork,
    RegistrationRequest,
    RegistrationSource,
    RegistrationStatus,
    Task,
    TaskStatus,
    User,
    Violation,
)


async def audit(
    db: AsyncSession,
    *,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    metadata: dict | None = None,
) -> AuditLog:
    row = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
    )
    db.add(row)
    await db.flush()
    return row


class RegistrationService:
    """Single workflow for both self-registration and admin recruitment."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def start(
        self,
        *,
        rubika_guid: str,
        applicant: User,
        source: RegistrationSource,
        recruited_by_admin_id: str | None = None,
        list_id: str | None = None,
    ) -> RegistrationRequest:
        channel = await self.db.scalar(select(Channel).where(Channel.rubika_guid == rubika_guid))
        if channel is None:
            channel = Channel(
                rubika_guid=rubika_guid,
                status=ChannelStatus.PENDING,
                list_id=list_id,
            )
            self.db.add(channel)
            await self.db.flush()
        elif channel.status == ChannelStatus.REMOVED:
            raise ValueError("Removed channel cannot be re-registered automatically")

        request = RegistrationRequest(
            channel_id=channel.id,
            applicant_id=applicant.id,
            source=source,
            recruited_by_admin_id=recruited_by_admin_id,
            assigned_admin_id=recruited_by_admin_id,
            list_id=list_id,
            status=RegistrationStatus.DRAFT,
        )
        self.db.add(request)
        await self.db.flush()
        await audit(
            self.db,
            actor_id=applicant.id,
            action="registration_started",
            entity_type="registration_request",
            entity_id=request.id,
            metadata={"source": source.value, "channel_id": channel.id},
        )
        return request

    async def submit_for_verification(self, request: RegistrationRequest) -> RegistrationRequest:
        if request.status not in {RegistrationStatus.DRAFT, RegistrationStatus.REJECTED}:
            raise ValueError(f"Cannot submit request from state {request.status}")
        request.status = RegistrationStatus.PENDING_VERIFICATION
        await self.db.flush()
        return request

    async def verify(
        self,
        request: RegistrationRequest,
        *,
        approved: bool,
        verifier_id: str | None = None,
        member_count: int | None = None,
    ) -> RegistrationRequest:
        if request.status != RegistrationStatus.PENDING_VERIFICATION:
            raise ValueError(f"Cannot verify request from state {request.status}")

        channel = await self.db.get(Channel, request.channel_id)
        if channel is None:
            raise ValueError("Channel not found")

        if approved:
            if not request.list_id:
                raise ValueError("Approved registration requires a list")
            channel.list_id = request.list_id
            channel.status = ChannelStatus.ACTIVE
            if member_count is not None:
                channel.member_count = member_count
            list_service = ListService(self.db)
            channel.list_code = await list_service.allocate_channel_code(request.list_id)
            request.status = RegistrationStatus.ACTIVE
            request.completed_at = datetime.now(timezone.utc)
        else:
            channel.status = ChannelStatus.PENDING
            request.status = RegistrationStatus.REJECTED

        await self.db.flush()
        await audit(
            self.db,
            actor_id=verifier_id,
            action="registration_verified" if approved else "registration_rejected",
            entity_type="registration_request",
            entity_id=request.id,
            metadata={"channel_id": channel.id, "list_id": request.list_id},
        )
        return request


class ListService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def allocate_channel_code(self, list_id: str) -> str:
        network_list = await self.db.get(ListNetwork, list_id)
        if network_list is None:
            raise ValueError("List not found")

        # Monotonic allocation: a code is never intentionally recycled.
        number = network_list.next_channel_number
        network_list.next_channel_number = number + 1
        await self.db.flush()
        return f"#{number:03d}"

    async def active_channel_count(self, list_id: str) -> int:
        count = await self.db.scalar(
            select(func.count(Channel.id)).where(
                Channel.list_id == list_id,
                Channel.status == ChannelStatus.ACTIVE,
            )
        )
        return int(count or 0)


class TaskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        assignee_id: str,
        task_type: str,
        payload: dict | None = None,
        due_at: datetime | None = None,
    ) -> Task:
        task = Task(
            assignee_id=assignee_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            payload=json.dumps(payload or {}, ensure_ascii=False),
            due_at=due_at,
        )
        self.db.add(task)
        await self.db.flush()
        return task


class ViolationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def record(
        self,
        *,
        channel_id: str,
        violation_type: str,
        severity: int = 1,
        admin_id: str | None = None,
        note: str | None = None,
    ) -> Violation:
        violation = Violation(
            channel_id=channel_id,
            admin_id=admin_id,
            violation_type=violation_type,
            severity=max(1, severity),
            note=note,
        )
        self.db.add(violation)
        await self.db.flush()
        await audit(
            self.db,
            actor_id=admin_id,
            action="violation_recorded",
            entity_type="channel",
            entity_id=channel_id,
            metadata={"type": violation_type, "severity": severity},
        )
        return violation
