"""리눅스 evdev 키코드 → keydeck 물리 키 이름. input-event-codes.h 기준, 하드코딩(안정 ABI).

반환 이름은 server/keycodes.py의 KVK_TO_NAME 값과 동일 이름 공간. 모디파이어는
좌우 구분 없이 Ctrl/Alt/Shift/Meta로 접어 mode.py가 상태/토글 감지에 쓴다."""

EVDEV_TO_NAME: dict[int, str] = {
    1: "Escape",
    2: "Digit1", 3: "Digit2", 4: "Digit3", 5: "Digit4", 6: "Digit5",
    7: "Digit6", 8: "Digit7", 9: "Digit8", 10: "Digit9", 11: "Digit0",
    12: "Minus", 13: "Equal", 14: "Backspace", 15: "Tab",
    16: "Q", 17: "W", 18: "E", 19: "R", 20: "T", 21: "Y", 22: "U",
    23: "I", 24: "O", 25: "P", 26: "LeftBracket", 27: "RightBracket",
    28: "Return", 29: "Ctrl",
    30: "A", 31: "S", 32: "D", 33: "F", 34: "G", 35: "H", 36: "J",
    37: "K", 38: "L", 39: "Semicolon", 40: "Quote", 41: "Grave",
    42: "Shift", 43: "Backslash",
    44: "Z", 45: "X", 46: "C", 47: "V", 48: "B", 49: "N", 50: "M",
    51: "Comma", 52: "Period", 53: "Slash", 54: "Shift", 56: "Alt",
    57: "Space",
    59: "F1", 60: "F2", 61: "F3", 62: "F4", 63: "F5", 64: "F6",
    65: "F7", 66: "F8", 67: "F9", 68: "F10", 87: "F11", 88: "F12",
    97: "Ctrl", 100: "Alt",
    102: "Home", 103: "Up", 104: "PageUp", 105: "Left", 106: "Right",
    107: "End", 108: "Down", 109: "PageDown", 111: "ForwardDelete",
    125: "Meta", 126: "Meta",
}


def key_name(code: int) -> str | None:
    return EVDEV_TO_NAME.get(code)
