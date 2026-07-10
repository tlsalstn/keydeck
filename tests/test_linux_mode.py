from client.linux.mode import MacroMode


def toggle_on(m):
    m.process("Ctrl", "down")
    m.process("Alt", "down")
    return m.process("M", "down")


def test_starts_off_sends_nothing():
    m = MacroMode()
    assert m.macro_on is False
    d = m.process("F5", "down")
    assert d == {"toggle": False, "message": None}


def test_toggle_on_via_ctrl_alt_m():
    m = MacroMode()
    d = toggle_on(m)
    assert d["toggle"] is True
    assert m.macro_on is True


def test_toggle_key_up_and_repeat_swallowed():
    m = MacroMode()
    toggle_on(m)
    assert m.process("M", "repeat") == {"toggle": False, "message": None}
    assert m.process("M", "up") == {"toggle": False, "message": None}
    assert m.macro_on is True  # 홀드 중 repeat로 재토글 안 됨


def test_sends_mapped_key_when_on():
    m = MacroMode()
    toggle_on(m)
    m.process("M", "up")            # 토글 키 정리
    m.process("Ctrl", "up")
    m.process("Alt", "up")
    d = m.process("F5", "down")
    assert d["toggle"] is False
    assert d["message"] == {"type": "key", "key": "F5", "event": "down",
                            "repeat": False, "shift": False}


def test_repeat_event_maps_to_down_with_repeat():
    m = MacroMode()
    toggle_on(m); m.process("M", "up"); m.process("Ctrl", "up"); m.process("Alt", "up")
    d = m.process("F6", "repeat")
    assert d["message"]["event"] == "down" and d["message"]["repeat"] is True


def test_shift_flag():
    m = MacroMode()
    toggle_on(m); m.process("M", "up"); m.process("Ctrl", "up"); m.process("Alt", "up")
    m.process("Shift", "down")
    d = m.process("Tab", "down")
    assert d["message"]["shift"] is True


def test_up_event_sent_when_on():
    m = MacroMode()
    toggle_on(m); m.process("M", "up"); m.process("Ctrl", "up"); m.process("Alt", "up")
    d = m.process("F5", "up")
    assert d["message"] == {"type": "key", "key": "F5", "event": "up",
                            "repeat": False, "shift": False}


def test_m_as_normal_key_without_combo():
    m = MacroMode()
    toggle_on(m); m.process("M", "up"); m.process("Ctrl", "up"); m.process("Alt", "up")
    d = m.process("M", "down")  # Ctrl+Alt 없이 M → 일반 매크로 키
    assert d["message"]["key"] == "M"


def test_toggle_off_returns_to_silent():
    m = MacroMode()
    toggle_on(m); m.process("M", "up"); m.process("Ctrl", "up"); m.process("Alt", "up")
    toggle_on(m)  # 다시 Ctrl+Alt+M → OFF
    assert m.macro_on is False
    m.process("M", "up"); m.process("Ctrl", "up"); m.process("Alt", "up")
    assert m.process("F5", "down") == {"toggle": False, "message": None}


def test_none_name_noop():
    m = MacroMode()
    toggle_on(m); m.process("M", "up"); m.process("Ctrl", "up"); m.process("Alt", "up")
    assert m.process(None, "down") == {"toggle": False, "message": None}


def test_reset_clears_ghost_state():
    m = MacroMode()
    m.process("Ctrl", "down")
    m.process("Alt", "down")
    m.process("M", "down")          # 토글 ON, _toggling=True
    m.reset()                        # fail-open (M up 유실 가정)
    assert m.macro_on is False
    # 유령 Ctrl+Alt가 제거되어 일반 M이 토글로 오인되지 않는다
    d = m.process("M", "down")
    assert d == {"toggle": False, "message": None}
    # 정상 조합은 다시 동작
    m.process("Ctrl", "down"); m.process("Alt", "down")
    assert m.process("M", "down")["toggle"] is True
