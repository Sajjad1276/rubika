from ad_network.bots.common import _SEEN_UPDATES, button_id, inline_keyboard, is_duplicate_update, quick_keyboard, update_user_id


class FakeAux:
    def __init__(self, button_id):
        self.button_id = button_id


class FakeEvent:
    def __init__(self, *, message_id="m1", user_guid="u0abc", button_id=None, aux_button_id=None):
        self.message_id = message_id
        self.user_guid = user_guid
        self.button_id = button_id
        self.chat_id = "b0bot"
        self.aux_data = FakeAux(aux_button_id) if aux_button_id else None


def test_keyboard_builders_keep_rows_and_root_without_back_button():
    inline = inline_keyboard((("a", "A"), ("b", "B")), (("c", "C"),))
    quick = quick_keyboard((("a", "A"),))
    assert len(inline["rows"]) == 3
    assert inline["rows"][-1]["buttons"][0]["id"] == "back"
    assert inline["rows"][-1]["buttons"][0]["button_text"] == "🔙 بازگشت"
    assert len(quick["rows"]) == 1
    assert quick["rows"][-1]["buttons"][0]["button_text"] == "A"


def test_callback_identity_prefers_user_guid():
    event = FakeEvent()
    assert update_user_id(event) == "u0abc"


def test_button_id_reads_aux_data():
    event = FakeEvent(aux_button_id="settings:lists:status")
    assert button_id(event) == "settings:lists:status"


def test_duplicate_update_window_is_idempotent():
    _SEEN_UPDATES.clear()
    event = FakeEvent(message_id="same")
    assert is_duplicate_update(event) is False
    assert is_duplicate_update(event) is True
    _SEEN_UPDATES.clear()
