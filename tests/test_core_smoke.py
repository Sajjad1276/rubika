from ad_network.core.db import normalize_database_url
from ad_network.core.list_accounts import ListAccountResolver
from ad_network.core.network_worker import NetworkWorker


def test_database_url_normalization():
    assert normalize_database_url("postgres://user:pass@host/db") == "postgresql+asyncpg://user:pass@host/db"
    assert normalize_database_url("postgresql://user:pass@host/db") == "postgresql+asyncpg://user:pass@host/db"
    assert normalize_database_url("sqlite+aiosqlite:///./rubika.db") == "sqlite+aiosqlite:///./rubika.db"


def test_list_account_resolver_keeps_injected_empty_registry():
    registry = {}
    resolver = ListAccountResolver(registry)
    resolver.bind("account-1", object())
    assert "account-1" in registry
    assert resolver.clients is registry


def test_content_ref_parser():
    assert NetworkWorker._parse_content_ref("c123:m456") == ("c123", "m456")


def test_content_ref_parser_rejects_invalid_value():
    try:
        NetworkWorker._parse_content_ref("invalid")
    except ValueError as exc:
        assert "content_ref" in str(exc)
    else:
        raise AssertionError("invalid content_ref must raise ValueError")
