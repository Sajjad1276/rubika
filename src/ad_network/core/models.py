from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def new_id() -> str:
    return str(uuid4())


class RegistrationSource(StrEnum):
    SELF = "user_self_registered"
    ADMIN_RECRUITED = "admin_recruited"


class RegistrationStatus(StrEnum):
    DRAFT = "draft"
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    ACTIVE = "active"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ChannelStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rubika_user_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(128))
    display_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ListNetwork(Base):
    __tablename__ = "lists"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    min_channels: Mapped[int] = mapped_column(Integer, default=20)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    channels: Mapped[list["Channel"]] = relationship(back_populates="list")


class ListAccount(Base):
    __tablename__ = "list_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    list_id: Mapped[str] = mapped_column(ForeignKey("lists.id"), index=True)
    rubika_user_id: Mapped[str] = mapped_column(String(128), index=True)
    session_ref: Mapped[str | None] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(default=True)


class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rubika_guid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str | None] = mapped_column(String(255))
    member_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[ChannelStatus] = mapped_column(default=ChannelStatus.PENDING)
    list_id: Mapped[str | None] = mapped_column(ForeignKey("lists.id"), index=True)
    list_code: Mapped[str | None] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    list: Mapped[ListNetwork | None] = relationship(back_populates="channels")


class RegistrationRequest(Base):
    __tablename__ = "registration_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), index=True)
    applicant_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[RegistrationSource] = mapped_column()
    recruited_by_admin_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    assigned_admin_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    list_id: Mapped[str | None] = mapped_column(ForeignKey("lists.id"))
    status: Mapped[RegistrationStatus] = mapped_column(default=RegistrationStatus.DRAFT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    assignee_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    payload: Mapped[str] = mapped_column(Text, default="{}")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Operation(Base):
    __tablename__ = "operations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    list_id: Mapped[str] = mapped_column(ForeignKey("lists.id"), index=True)
    operation_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="planned")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Violation(Base):
    __tablename__ = "violations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), index=True)
    admin_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    violation_type: Mapped[str] = mapped_column(String(64))
    severity: Mapped[int] = mapped_column(Integer, default=1)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(128), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
