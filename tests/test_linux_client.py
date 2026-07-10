import asyncio

import pytest

pytest.importorskip("evdev")  # 클라이언트 모듈은 evdev 필요 — 없는 환경에선 스킵

from client.linux import keydeck_client
from client.linux.keydeck_client import Client


class FakeDev:
    def __init__(self):
        self.ungrabbed = False

    def grab(self):
        pass

    def ungrab(self):
        self.ungrabbed = True

    async def async_read_loop(self):
        raise OSError("transient")
        yield  # pragma: no cover — async generator로 만들기 위한 도달 불가 코드


def test_reader_error_fails_open(monkeypatch):
    """grab 중 장치 리더가 죽으면 전체 fail-open — 키보드 먹통 방지."""
    monkeypatch.setattr(keydeck_client, "notify", lambda *a, **k: None)
    dev = FakeDev()
    c = Client([dev])
    c.grabbed = True
    c.mode.macro_on = True
    asyncio.run(c._read(dev))
    assert c.grabbed is False
    assert dev.ungrabbed is True
    assert c.mode.macro_on is False


def test_reader_error_without_grab_is_silent(monkeypatch):
    notified = []
    monkeypatch.setattr(keydeck_client, "notify", lambda *a, **k: notified.append(a))
    dev = FakeDev()
    c = Client([dev])
    asyncio.run(c._read(dev))
    assert c.grabbed is False and notified == []
