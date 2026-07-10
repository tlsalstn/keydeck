from client.linux.keymap import key_name


def test_letter_and_digit():
    assert key_name(30) == "A"      # KEY_A
    assert key_name(50) == "M"      # KEY_M
    assert key_name(2) == "Digit1"  # KEY_1
    assert key_name(11) == "Digit0" # KEY_0


def test_function_keys():
    assert key_name(59) == "F1"
    assert key_name(88) == "F12"


def test_punctuation_and_specials():
    assert key_name(41) == "Grave"     # KEY_GRAVE
    assert key_name(51) == "Comma"     # KEY_COMMA
    assert key_name(52) == "Period"    # KEY_DOT
    assert key_name(28) == "Return"    # KEY_ENTER
    assert key_name(40) == "Quote"     # KEY_APOSTROPHE
    assert key_name(15) == "Tab"
    assert key_name(57) == "Space"
    assert key_name(1) == "Escape"


def test_modifiers_side_collapsed():
    assert key_name(29) == "Ctrl"   # KEY_LEFTCTRL
    assert key_name(97) == "Ctrl"   # KEY_RIGHTCTRL
    assert key_name(42) == "Shift"  # KEY_LEFTSHIFT
    assert key_name(54) == "Shift"  # KEY_RIGHTSHIFT
    assert key_name(56) == "Alt"    # KEY_LEFTALT
    assert key_name(100) == "Alt"   # KEY_RIGHTALT


def test_unknown_code_none():
    assert key_name(9999) is None
