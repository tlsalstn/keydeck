from client.linux.mode import MacroMode


def toggle_on(m):
    m.process("Ctrl", "down")
    m.process("Alt", "down")
    return m.process("M", "down")


def test_starts_off_sends_nothing():
    m = MacroMode()
    assert m.macro_on is False
    d = m.process("F5", "down")
    assert d == {"toggle": False, "grab": None, "message": None}


def test_toggle_on_via_ctrl_alt_m():
    m = MacroMode()
    d = toggle_on(m)
    assert d["toggle"] is True
    assert m.macro_on is True


def test_toggle_key_up_and_repeat_swallowed():
    m = MacroMode()
    toggle_on(m)
    assert m.process("M", "repeat") == {"toggle": False, "grab": None, "message": None}
    assert m.process("M", "up") == {"toggle": False, "grab": None, "message": None}
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
    assert m.process("F5", "down") == {"toggle": False, "grab": None, "message": None}


def test_none_name_noop():
    m = MacroMode()
    toggle_on(m); m.process("M", "up"); m.process("Ctrl", "up"); m.process("Alt", "up")
    assert m.process(None, "down") == {"toggle": False, "grab": None, "message": None}


def test_reset_clears_ghost_state():
    m = MacroMode()
    m.process("Ctrl", "down")
    m.process("Alt", "down")
    m.process("M", "down")          # 토글 ON, _toggling=True
    m.reset()                        # fail-open (M up 유실 가정)
    assert m.macro_on is False
    # 유령 Ctrl+Alt가 제거되어 일반 M이 토글로 오인되지 않는다
    d = m.process("M", "down")
    assert d == {"toggle": False, "grab": None, "message": None}
    # 정상 조합은 다시 동작
    m.process("Ctrl", "down"); m.process("Alt", "down")
    assert m.process("M", "down")["toggle"] is True


def test_grab_deferred_until_combo_released():
    m = MacroMode()
    m.process("Ctrl", "down"); m.process("Alt", "down")
    d = m.process("M", "down")
    assert d["toggle"] is True and d["grab"] is None       # 아직 grab 금지
    assert m.process("M", "up")["grab"] is None            # M 풀림, Ctrl+Alt 유지
    assert m.process("Ctrl", "up")["grab"] is None
    assert m.process("Alt", "up")["grab"] is True          # 콤보 완전 해제 → grab


def test_no_messages_while_grab_pending():
    m = MacroMode()
    m.process("Ctrl", "down"); m.process("Alt", "down"); m.process("M", "down")
    d = m.process("F5", "down")                            # 아직 로컬 전달 중
    assert d["message"] is None
    m.process("M", "up"); m.process("Ctrl", "up"); m.process("Alt", "up")
    assert m.process("F5", "down")["message"]["key"] == "F5"


def test_toggle_off_ungrabs_immediately():
    m = MacroMode()
    m.process("Ctrl", "down"); m.process("Alt", "down"); m.process("M", "down")
    m.process("M", "up"); m.process("Ctrl", "up"); m.process("Alt", "up")
    m.process("Ctrl", "down"); m.process("Alt", "down")
    d = m.process("M", "down")
    assert d["toggle"] is True and d["grab"] is False      # OFF는 즉시 ungrab


def test_reset_clears_pending_grab():
    m = MacroMode()
    m.process("Ctrl", "down"); m.process("Alt", "down"); m.process("M", "down")
    m.reset()
    # pending이 제거되어 이후 모디파이어 up이 유령 grab을 유발하지 않는다
    assert m.process("Ctrl", "up")["grab"] is None
    assert m.process("Alt", "up")["grab"] is None
