"""macOS 가상 키코드(kVK) → 물리 키 이름. ANSI US MacBook 기준, 레이아웃 무관."""

KVK_TO_NAME: dict[int, str] = {
    0: "A", 1: "S", 2: "D", 3: "F", 4: "H", 5: "G", 6: "Z", 7: "X",
    8: "C", 9: "V", 11: "B", 12: "Q", 13: "W", 14: "E", 15: "R",
    16: "Y", 17: "T", 18: "Digit1", 19: "Digit2", 20: "Digit3",
    21: "Digit4", 22: "Digit6", 23: "Digit5", 24: "Equal", 25: "Digit9",
    26: "Digit7", 27: "Minus", 28: "Digit8", 29: "Digit0",
    30: "RightBracket", 31: "O", 32: "U", 33: "LeftBracket", 34: "I",
    35: "P", 36: "Return", 37: "L", 38: "J", 39: "Quote", 40: "K",
    41: "Semicolon", 42: "Backslash", 43: "Comma", 44: "Slash", 45: "N",
    46: "M", 47: "Period", 48: "Tab", 49: "Space", 50: "Grave",
    51: "Backspace", 53: "Escape",
    96: "F5", 97: "F6", 98: "F7", 99: "F3", 100: "F8", 101: "F9",
    103: "F11", 109: "F10", 111: "F12", 118: "F4", 120: "F2", 122: "F1",
    115: "Home", 116: "PageUp", 117: "ForwardDelete", 119: "End",
    121: "PageDown", 123: "Left", 124: "Right", 125: "Down", 126: "Up",
}


def key_name(code: int) -> str | None:
    return KVK_TO_NAME.get(code)
