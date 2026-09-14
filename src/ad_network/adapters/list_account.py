from typing import Any

from ..core.list_accounts import ListAccountResolver
from .rubika import MaxRubikaGateway, RubikaGateway


class ListAccountGatewayResolver:
    """Resolves a persisted ListAccount into its live MAXRubika gateway."""

    def __init__(self, accounts: ListAccountResolver):
        self.accounts = accounts

    def resolve(self, account: Any) -> RubikaGateway:
        client = self.accounts.resolve(account)
        if isinstance(client, MaxRubikaGateway):
            return client
        return MaxRubikaGateway(client)

    def bind(self, account_id: str, client: Any) -> None:
        self.accounts.bind(account_id, client)

    def unbind(self, account_id: str) -> None:
        self.accounts.unbind(account_id)
