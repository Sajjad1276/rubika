from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ListAccount, ListNetwork


@dataclass(frozen=True)
class AccountBinding:
    list_id: str
    account_id: str
    rubika_user_id: str
    session_ref: str | None


class ListAccountService:
    """Persistent mapping between a List and its operational user-bot account."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def bind(self, *, list_id: str, rubika_user_id: str,
                   session_ref: str | None = None) -> ListAccount:
        if await self.db.get(ListNetwork, list_id) is None:
            raise ValueError("List not found")
        existing = await self.get_active(list_id)
        if existing is not None:
            existing.rubika_user_id = rubika_user_id
            existing.session_ref = session_ref
            await self.db.flush()
            return existing
        account = ListAccount(
            list_id=list_id,
            rubika_user_id=rubika_user_id,
            session_ref=session_ref,
            active=True,
        )
        self.db.add(account)
        await self.db.flush()
        return account

    async def get_active(self, list_id: str) -> ListAccount | None:
        return await self.db.scalar(
            select(ListAccount)
            .where(ListAccount.list_id == list_id, ListAccount.active.is_(True))
            .order_by(ListAccount.id)
        )

    async def require_active(self, list_id: str) -> ListAccount:
        account = await self.get_active(list_id)
        if account is None:
            raise ValueError(f"List {list_id} has no active operational account")
        return account

    async def deactivate(self, account_id: str) -> None:
        account = await self.db.get(ListAccount, account_id)
        if account is None:
            raise ValueError("List account not found")
        account.active = False
        await self.db.flush()


class ListAccountResolver:
    """Runtime registry of authenticated FastRub pyrubi clients."""

    def __init__(self, clients: dict[str, Any] | None = None):
        self.clients = clients or {}

    def resolve(self, account: ListAccount) -> Any:
        try:
            return self.clients[account.id]
        except KeyError as exc:
            raise RuntimeError(
                f"No live Rubika client is bound to list account {account.id}"
            ) from exc

    def bind(self, account_id: str, client: Any) -> None:
        self.clients[account_id] = client

    def unbind(self, account_id: str) -> None:
        self.clients.pop(account_id, None)
