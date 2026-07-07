"""MacPad 서버: 키 이벤트 수신 → 매핑 조회 → 액션 실행 → 대시보드 push."""
import asyncio
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .actions import EXECUTORS, ActionError
from .config import ConfigError, load_config
from .keycodes import key_name

log = logging.getLogger("macpad")
BASE = Path(__file__).parent
CONFIG_PATH = Path(os.environ.get("MACPAD_CONFIG", BASE.parent / "config" / "mapping.yaml"))


class State:
    def __init__(self):
        self.config = load_config(CONFIG_PATH)
        self.active_page = "default"
        self.client_ws: WebSocket | None = None
        self.dashboards: set[WebSocket] = set()


state = State()
app = FastAPI()


async def broadcast(msg: dict) -> None:
    dead = []
    for ws in list(state.dashboards):
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        state.dashboards.discard(ws)


def mapping_payload() -> dict:
    return {
        "active_page": state.active_page,
        "pages": {
            name: {
                k: {"label": b.label, "icon": b.icon, "type": b.action["type"], "repeat": b.repeat}
                for k, b in page.items()
            }
            for name, page in state.config.pages.items()
        },
    }


@app.get("/api/mapping")
async def get_mapping():
    return mapping_payload()


@app.get("/")
async def index():
    return FileResponse(BASE / "static" / "index.html")


app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


async def run_action(key: str, binding) -> None:
    try:
        await EXECUTORS[binding.action["type"]](binding.action)
        await broadcast({"type": "action_result", "key": key, "label": binding.label,
                         "ok": True, "error": None})
    except ActionError as e:
        await broadcast({"type": "action_result", "key": key, "label": binding.label,
                         "ok": False, "error": str(e)})
    except Exception as e:  # 실행기 버그도 서버를 죽이지 않고 대시보드에 표시
        log.exception("action failed: %s", key)
        await broadcast({"type": "action_result", "key": key, "label": binding.label,
                         "ok": False, "error": f"internal: {e}"})


async def handle_key(msg: dict) -> None:
    try:
        code = int(msg.get("code", -1))
    except (TypeError, ValueError):
        return
    name = key_name(code)
    binding = state.config.pages[state.active_page].get(name) if name else None
    await broadcast({"type": "key", "key": name, "event": msg.get("event"),
                     "mapped": binding is not None})
    if binding is None or msg.get("event") != "down":
        return
    if msg.get("repeat") and not binding.repeat:
        return
    asyncio.create_task(run_action(name, binding))


@app.websocket("/ws/client")
async def ws_client(ws: WebSocket):
    if ws.query_params.get("token") != state.config.token:
        await ws.close(code=1008)
        return
    await ws.accept()
    state.client_ws = ws
    await broadcast({"type": "client_status", "connected": True})
    try:
        while True:
            try:
                msg = json.loads(await ws.receive_text())
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "key":
                await handle_key(msg)
            # hello/ping: 연결 유지용, 무시
    except WebSocketDisconnect:
        pass
    finally:
        state.client_ws = None
        await broadcast({"type": "client_status", "connected": False})


@app.websocket("/ws/dashboard")
async def ws_dashboard(ws: WebSocket):
    await ws.accept()
    state.dashboards.add(ws)
    await ws.send_json({"type": "client_status", "connected": state.client_ws is not None})
    try:
        while True:
            await ws.receive_text()  # 뷰어 전용 — 수신 내용은 전부 무시
    except WebSocketDisconnect:
        pass
    finally:
        state.dashboards.discard(ws)
