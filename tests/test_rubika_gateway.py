import pytest

from ad_network.adapters.rubika import MaxRubikaGateway


class FakeClient:
    async def get_channel_info(self, guid):
        return {"channel": {"channel_title": "Demo", "username": "demo", "count_members": 321}}

    async def get_channel_admins(self, guid):
        return {
            "admins": [
                {"member_guid": "u-1", "join_type": "Admin"},
                {"member_guid": "u-2", "join_type": "Member"},
            ]
        }

    async def get_channel_admin_access(self, guid, user_id):
        return {"access_list": ["SendMessages", "EditMessages", "DeleteMessages"]}

    async def forward_messages(self, source_guid, message_ids, target_guid):
        return {"message_id": "m-2"}

    async def edit_message(self, chat, message_id, text):
        return {"message_id": message_id, "text": text}

    async def delete_messages(self, chat, message_ids):
        return {"deleted": message_ids}

    async def get_messages_by_id(self, chat, message_ids):
        return {"messages": [{"message_id": message_ids[0]}]}


@pytest.mark.asyncio
async def test_channel_snapshot_and_real_permissions():
    gateway = MaxRubikaGateway(FakeClient())

    snapshot = await gateway.get_channel("c-1")
    assert snapshot.member_count == 321
    assert snapshot.title == "Demo"
    assert snapshot.username == "demo"

    access = await gateway.verify_channel_access("c-1", "u-1")
    assert access.is_admin is True
    assert access.can_send is True
    assert access.can_edit is True
    assert access.can_delete is True


@pytest.mark.asyncio
async def test_non_admin_member_fails_closed():
    gateway = MaxRubikaGateway(FakeClient())
    access = await gateway.verify_channel_access("c-1", "u-2")
    assert access.is_admin is False
    assert access.can_send is False
    assert access.can_edit is False
    assert access.can_delete is False


@pytest.mark.asyncio
async def test_permission_check_fails_closed_for_unknown_user():
    gateway = MaxRubikaGateway(FakeClient())
    access = await gateway.verify_channel_access("c-1", "unknown")
    assert access.is_admin is False
    assert access.can_send is False
    assert access.can_edit is False
    assert access.can_delete is False


@pytest.mark.asyncio
async def test_message_mutation_methods_use_maxrubika_argument_order():
    gateway = MaxRubikaGateway(FakeClient())
    assert await gateway.forward("c-source", "c-target", "m-1") == {"message_id": "m-2"}
    assert await gateway.edit("c-target", "m-1", "updated") == {"message_id": "m-1", "text": "updated"}
    assert await gateway.delete("c-target", "m-1") == {"deleted": ["m-1"]}
    assert await gateway.get_message("c-target", "m-1") == {"messages": [{"message_id": "m-1"}]}
