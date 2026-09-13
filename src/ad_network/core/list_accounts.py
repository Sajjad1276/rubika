from dataclasses import dataclass

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
    """Owns the mapping between a List and its operational Rubika account.

    Session secrets are deliberately not stored here. `session_ref` is only a
    reference to an external/secure session store.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def bind(self, *, list_id: str, rubika_user_id: str,
                   session_ref: str | None = None) -> ListAccount:
        network_list = await self.db.get(ListNetwork, list_id)
        if network_list is None:
            raise ValueError("List not found")

        existing = await self.db.scalar(
            select(ListAccount).where(
                ListAccount.list_id == list_id,
                ListAccount.active.is_(True),
            )
        )
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
            select(ListAccount).where(
                ListAccount.list_id == list_id,
                ListAccount.active.is_(True),
            ).order_by(ListAccount.id)
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
    """Runtime seam between DB account records and live Rubika clients."""

    def __init__(self, clients: dict[str, object]):
        self.clients = clients

    def resolve(self, account: ListAccount) -> object:
        try:
            return self.clients[account.id]
        except KeyError as exc:
            raise RuntimeError(
                f"No live Rubika client is bound to list account {account.id}"
            ) from exc

    def bind(self, account_id: str, client: object) -> None:
        self.clients[account_id] = client
