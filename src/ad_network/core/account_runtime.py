import logging
from pathlib import Path
from typing import Any

from maxrubika import Messenger

from .config import get_settings
from .list_accounts import ListAccountResolver
from ..adapters.list_account import ListAccountGatewayResolver

logger = logging.getLogger(__name__)


class ListAccountRuntime:
    """Runtime registry for active List accounts using MAXRubika Messenger."""

    def __init__(self, resolver: ListAccountResolver):
        self.resolver = resolver
        self.gateways = ListAccountGatewayResolver(resolver)
        self._session_refs: dict[str, str] = {}

    @staticmethod
    def _resolve_session(session_ref: str) -> Path:
        path = Path(session_ref).expanduser()
        if not path.is_absolute():
            path = Path(get_settings().rubika_session_dir).expanduser() / path
        if path.exists():
            return path
        if path.suffix != ".max":
            candidate = path.with_name(path.name + ".max")
            if candidate.exists():
                return candidate
        return path

    async def connect(self, account: Any) -> Any:
        if not account.session_ref:
            raise RuntimeError(f"List account {account.id} has no session_ref")
        session = self._resolve_session(account.session_ref)
        if not session.is_file():
            raise RuntimeError(f"List account session does not exist: {session}")

        existing = self.resolver.clients.get(account.id)
        if existing is not None and self._session_refs.get(account.id) == str(session):
            return existing
        if existing is not None:
            await self.disconnect(account.id)

        client = Messenger(session=str(session), api_version=6, max_retries=5)
        await client.start()
        self.resolver.bind(account.id, client)
        self._session_refs[account.id] = str(session)
        logger.info("List account connected: %s (%s)", account.id, account.rubika_user_id)
        return client

    async def sync_active_accounts(self, accounts: list[Any]) -> None:
        active = {account.id: account for account in accounts}
        for account_id in list(self.resolver.clients):
            if account_id not in active:
                await self.disconnect(account_id)
                logger.info("List account disconnected: %s", account_id)
        for account in accounts:
            try:
                await self.connect(account)
            except Exception:
                logger.exception("Failed to connect List account %s", account.id)

    async def disconnect(self, account_id: str) -> None:
        client = self.resolver.clients.get(account_id)
        if client is not None:
            close = getattr(client, "close", None)
            stop = getattr(client, "stop", None)
            try:
                if callable(close):
                    result = close()
                    if hasattr(result, "__await__"):
                        await result
                elif callable(stop):
                    result = stop()
                    if hasattr(result, "__await__"):
                        await result
            finally:
                self.resolver.unbind(account_id)
                self._session_refs.pop(account_id, None)
        else:
            self.resolver.unbind(account_id)
            self._session_refs.pop(account_id, None)
