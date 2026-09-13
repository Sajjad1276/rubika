import pytest

from ad_network.adapters.rubika import FastRubikaGateway


class FakeClient:
    async def get_channel_info(self, guid):
        return {"channel": {"title": "Demo", "username": "demo", "members_count": 321}}

    async def get_channel_admin_members(self, guid):
        return {
            "in_chat_members": [
                {
                    "member_guid": "u-1",
                    "permissions": ["write", "edit", "delete"],
                }
            ]
        }


@pytest.mark.asyncio
async def test_channel_snapshot_and_real_permissions():
    gateway = FastRubikaGateway(FakeClient())

    snapshot = await gateway.get_channel("c-1")
    assert snapshot.member_count == 321
    assert snapshot.title == "Demo"

    access = await gateway.verify_channel_access("c-1", "u-1")
    assert access.is_admin is True
    assert access.can_send is True
    assert access.can_edit is True
    assert access.can_delete is True


@pytest.mark.asyncio
async def test_permission_check_fails_closed_for_unknown_user():
    gateway = FastRubikaGateway(FakeClient())
    access = await gateway.verify_channel_access("c-1", "unknown")
    assert access.is_admin is False
    assert access.can_send is False
    assert access.can_edit is False
    assert access.can_delete is False
