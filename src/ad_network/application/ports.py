from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class MessageGateway(Protocol):
    async def forward(self, source_guid: str, target_guid: str, message_id: str) -> object: ...

    async def get_message(self, chat_guid: str, message_id: str) -> object: ...


class RuntimeClientResolver(Protocol):
    def resolve(self, account_id: str) -> object: ...


class TargetRepository(Protocol):
    async def due_targets(self, now: datetime, limit: int) -> Sequence[object]: ...

    async def claim(self, target_id: str) -> bool: ...
