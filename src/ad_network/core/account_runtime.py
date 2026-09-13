import logging
from pathlib import Path
from typing import Any

from fast_rub.pyrubi import Client as PyrubiClient

from .list_accounts import ListAccountResolver
from ..adapters.list_account import ListAccountGatewayResolver

logger = logging.getLogger(__name__)


class ListAccountRuntime:
    """Loads authenticated FastRub pyrubi clients for active List accounts."""

    def __init__(self, resolver: ListAccountResolver):
        self.resolver = resolver
        self.gateways = ListAccountGatewayResolver(resolver)

    async def connect(self, account: Any) -> Any:
        if not account.session_ref:
            raise RuntimeError(f"List account {account.id} has no session_ref")
        session = Path(account.session_ref)
        if not session.exists():
            raise RuntimeError(f"List account session does not exist: {session}")
        client = PyrubiClient(session=str(session), run_start=False)
        await client.start()
        self.resolver.bind(account.id, client)
        logger.info("List account connected: %s", account.id)
        return client

    async def disconnect(self, account_id: str) -> None:
        client = self.resolver.clients.get(account_id)
        if client is not None:
            close = getattr(client, "close", None)
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result
        self.resolver.unbind(account_id)
