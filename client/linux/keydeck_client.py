"""keydeck 리눅스 클라이언트: evdev로 키 캡처+grab, WS로 호스트 전송. 매핑 해석은 서버.

필요: python3-evdev, python3-websockets, libnotify(notify-send). 사용자는 input 그룹.
환경변수: KEYDECK_HOST, KEYDECK_PORT(기본 8787), KEYDECK_TOKEN."""
import asyncio
import json
import os
import signal

import websockets
from evdev import InputDevice, ecodes, list_devices

from .keymap import key_name
from .mode import MacroMode

HOST = os.environ.get("KEYDECK_HOST", "CHANGE-ME-host-ip")
PORT = int(os.environ.get("KEYDECK_PORT", "8787"))
TOKEN = os.environ.get("KEYDECK_TOKEN", "CHANGE-ME-token")

EVENT_NAMES = {0: "up", 1: "down", 2: "repeat"}


def find_keyboards() -> list:
    """A~Z 키를 가진 evdev 장치 = 키보드로 판정, 전부 반환."""
    kbds = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
        except OSError:
            continue
        keys = dev.capabilities().get(ecodes.EV_KEY, [])
        if ecodes.KEY_A in keys and ecodes.KEY_Z in keys:
            kbds.append(dev)
    return kbds


def notify(summary: str, body: str = "") -> None:
    try:
        os.spawnlp(os.P_NOWAIT, "notify-send", "notify-send", "-a", "keydeck", summary, body)
    except OSError:
        pass


class Client:
    def __init__(self, devices):
        self.devices = devices
        self.mode = MacroMode()
        self.ws = None
        self.grabbed = False

    def _set_grab(self, on: bool) -> None:
        if on == self.grabbed:
            return
        for dev in self.devices:
            try:
                dev.grab() if on else dev.ungrab()
            except OSError:
                pass
        self.grabbed = on

    def _fail_open(self) -> None:
        """연결 끊김/종료 시 즉시 로컬 키보드 복구."""
        self.mode.reset()
        self._set_grab(False)

    async def _handle(self, ev) -> None:
        if ev.type != ecodes.EV_KEY:
            return
        event = EVENT_NAMES.get(ev.value)
        if event is None:
            return
        decision = self.mode.process(key_name(ev.code), event)
        if decision["toggle"]:
            self._set_grab(self.mode.macro_on)
            notify("keydeck", "매크로 모드 ON" if self.mode.macro_on else "매크로 모드 OFF")
        msg = decision["message"]
        if msg is not None and self.ws is not None:
            try:
                await self.ws.send(json.dumps(msg))
            except Exception:
                pass

    async def _read(self, dev) -> None:
        try:
            async for ev in dev.async_read_loop():
                await self._handle(ev)
        except OSError:
            # 장치 오류/분리 — grab 중이었다면 전체 fail-open으로 키보드를 되돌린다
            if self.grabbed:
                self._fail_open()
                notify("keydeck", "입력 장치 오류 — 매크로 모드 해제")

    async def run(self) -> None:
        readers = [asyncio.create_task(self._read(d)) for d in self.devices]
        try:
            while True:
                try:
                    uri = f"ws://{HOST}:{PORT}/ws/client?token={TOKEN}"
                    async with websockets.connect(uri) as ws:
                        self.ws = ws
                        await ws.send(json.dumps(
                            {"type": "hello", "client": "linux", "version": 1}))
                        notify("keydeck", "서버 연결됨")
                        async for _ in ws:  # 서버 push는 무시, 연결 유지 (라이브러리가 ping 처리)
                            pass
                except Exception:
                    pass
                self.ws = None
                self._fail_open()
                notify("keydeck", "서버 연결 끊김 — 재연결 중")
                await asyncio.sleep(2)
        finally:
            for r in readers:
                r.cancel()
            self._set_grab(False)


def main() -> None:
    devices = find_keyboards()
    if not devices:
        raise SystemExit("키보드 장치를 찾지 못했습니다 (input 그룹 소속 확인)")
    client = Client(devices)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: [t.cancel() for t in asyncio.all_tasks(loop)])
    try:
        loop.run_until_complete(client.run())
    except asyncio.CancelledError:
        pass
    finally:
        client._set_grab(False)


if __name__ == "__main__":
    main()
