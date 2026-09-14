from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .account_runtime import ListAccountRuntime
from .config import get_settings
from .list_accounts import ListAccountService
from .models import ListAccount, ListNetwork


class AccountManagementService:
    """Application service for adding, testing, replacing and disabling List accounts."""

    def __init__(self, db: AsyncSession, runtime: ListAccountRuntime | None = None):
        self.db = db
        self.runtime = runtime

    @staticmethod
    def resolve_session_path(session_ref: str) -> Path:
        path = Path(session_ref).expanduser()
        if path.is_absolute():
            return path
        return Path(get_settings().rubika_session_dir).expanduser() / path

    async def get_by_code(self, code: str) -> ListNetwork | None:
        return await self.db.scalar(
            select(ListNetwork).where(ListNetwork.code == code, ListNetwork.active.is_(True))
        )

    async def attach(self, *, list_code: str, rubika_user_id: str, session_ref: str) -> ListAccount:
        if not self.resolve_session_path(session_ref).exists():
            raise ValueError(f"Session file does not exist: {session_ref}")
        network = await self.get_by_code(list_code)
        if network is None:
            raise ValueError("Active List not found")
        account = await ListAccountService(self.db).bind(
            list_id=network.id,
            rubika_user_id=rubika_user_id,
            session_ref=session_ref,
        )
        await self.db.flush()
        return account

    async def replace(self, account_id: str, *, rubika_user_id: str, session_ref: str) -> ListAccount:
        if not self.resolve_session_path(session_ref).exists():
            raise ValueError(f"Session file does not exist: {session_ref}")
        account = await ListAccountService(self.db).replace(
            account_id,
            rubika_user_id=rubika_user_id,
            session_ref=session_ref,
        )
        await self.db.flush()
        return account

    async def test(self, account: ListAccount) -> None:
        if self.runtime is None:
            raise RuntimeError("List account runtime is not available")
        await self.runtime.connect(account)

    async def disable(self, account: ListAccount) -> None:
        await ListAccountService(self.db).deactivate(account.id)
        await self.db.flush()
        if self.runtime is not None:
            await self.runtime.disconnect(account.id)
