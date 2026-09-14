from ad_network.core.network_worker import NetworkWorker
from ad_network.core.retention_monitor import RetentionMonitor


def test_content_ref_parser_supports_colons_in_source_guid():
    assert NetworkWorker._parse_content_ref("chat:source:123") == ("chat:source", "123")


def test_content_ref_parser_rejects_invalid_values():
    for value in ("", "source", "source:", ":message"):
        try:
            NetworkWorker._parse_content_ref(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {value!r}")


def test_retention_message_presence():
    assert RetentionMonitor.message_exists({"messages": [{"message_id": "1"}]})
    assert not RetentionMonitor.message_exists({"messages": []})
    assert not RetentionMonitor.message_exists(None)
