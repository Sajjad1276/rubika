from ad_network.bots.common import _SEEN_UPDATES, inline_keyboard, is_duplicate_update, quick_keyboard, update_user_id


class FakeEvent:
    def __init__(self, *, message_id="m1", user_guid="u0abc", button_id=None):
        self.message_id = message_id
        self.user_guid = user_guid
        self.button_id = button_id
        self.chat_id = "b0bot"


def test_keyboard_builders_keep_rows_and_root_without_back_button():
    inline = inline_keyboard((("a", "A"), ("b", "B")), (("c", "C"),))
    quick = quick_keyboard((("a", "A"),))
    assert len(inline["rows"]) == 3
    assert inline["rows"][-1]["buttons"][0]["id"] == "home"
    assert len(quick["rows"]) == 1
    assert quick["rows"][-1]["buttons"][0]["button_text"] == "A"


def test_callback_identity_prefers_user_guid():
    event = FakeEvent()
    assert update_user_id(event) == "u0abc"


def test_duplicate_update_window_is_idempotent():
    _SEEN_UPDATES.clear()
    event = FakeEvent(message_id="same")
    assert is_duplicate_update(event) is False
    assert is_duplicate_update(event) is True
    _SEEN_UPDATES.clear()
