from ad_network.bots.owner_list_grid import list_management_keyboard


def test_owner_list_grid_has_expected_sections_and_two_column_rows():
    keyboard = list_management_keyboard()
    rows = keyboard["rows"]

    assert [row["buttons"][0]["button_text"] for row in rows if row["buttons"]] == [
        "12H",
        "100",
        "500",
        "6H",
        "1K",
        "3K",
        "5K",
        "VIEW",
        "50V",
        "200V",
        "500V",
        "🔙 بازگشت",
    ]

    assert [
        [button["button_text"] for button in row["buttons"]]
        for row in rows
    ] == [
        ["12H"],
        ["100", "300"],
        ["500", "700"],
        ["6H"],
        ["1K", "2K"],
        ["3K", "4K"],
        ["5K"],
        ["VIEW"],
        ["50V", "100V"],
        ["200V", "300V"],
        ["500V", "600V"],
        ["🔙 بازگشت"],
    ]


def test_owner_list_grid_callbacks_match_owner_router_contract():
    keyboard = list_management_keyboard()
    callbacks = [
        button["id"]
        for row in keyboard["rows"]
        for button in row["buttons"]
    ]

    assert "lists:12h:100" in callbacks
    assert "lists:12h:700" in callbacks
    assert "lists:6h:1000" in callbacks
    assert "lists:6h:5000" in callbacks
    assert "lists:view:50" in callbacks
    assert "lists:view:600" in callbacks
    assert callbacks[-1] == "lists"
    assert "home" not in callbacks
