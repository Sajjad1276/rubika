import logging
from typing import Any

from fast_rub.pyrubi import Client as PyrubiClient

from .list_accounts import ListAccountResolver
from ..adapters.list_account import ListAccountGatewayResolver

logger = logging.getLogger(__name__)


class ListAccountRuntime:
    """Loads authenticated FastRub pyrubi clients for active List accounts.

    Session files are referenced by `session_ref`; credentials are never copied
    into the database. A failed account is kept offline rather than activated.
    """

    def __init__(self, resolver: ListAccountResolver):
        self.resolver = resolver
        self.gateways = ListAccountGatewayResolver(resolver)

    async def connect(self, account: Any) -> Any:
        if not account.session_ref:
            raise RuntimeError(f"List account {account.id} has no session_ref")
        client = PyrubiClient(session=account.session_ref, run_start=False)
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
