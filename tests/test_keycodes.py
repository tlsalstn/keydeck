from server.keycodes import key_name


def test_function_keys():
    assert key_name(122) == "F1"
    assert key_name(120) == "F2"
    assert key_name(111) == "F12"


def test_letters_and_digits():
    assert key_name(0) == "A"
    assert key_name(46) == "M"
    assert key_name(18) == "Digit1"
    assert key_name(29) == "Digit0"


def test_specials():
    assert key_name(49) == "Space"
    assert key_name(36) == "Return"
    assert key_name(53) == "Escape"


def test_unknown_code_returns_none():
    assert key_name(999) is None
    assert key_name(-1) is None
