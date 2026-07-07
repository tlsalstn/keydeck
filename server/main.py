"""MacPad 서버: 키 이벤트 수신 → 매핑 조회 → 액션 실행 → 대시보드 push."""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .actions import EXECUTORS, ActionError
from .config import ConfigError, load_config
from .icons import resolve_icon
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


async def broadcast(msg: dict) -> None:
    dead = []
    for ws in list(state.dashboards):
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        state.dashboards.discard(ws)


_reload_mtime = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else 0.0


async def check_reload() -> str | None:
    """설정 파일 mtime 변경 시 리로드. 검증 실패면 이전 설정 유지 + 오류 push."""
    global _reload_mtime
    try:
        mtime = CONFIG_PATH.stat().st_mtime
    except FileNotFoundError:
        return None
    if mtime == _reload_mtime:
        return None
    _reload_mtime = mtime
    try:
        state.config = load_config(CONFIG_PATH)
    except ConfigError as e:
        log.error("설정 리로드 실패: %s", e)
        await broadcast({"type": "config_error", "message": str(e)})
        return "error"
    except OSError as e:
        log.error("설정 파일 읽기 실패: %s", e)
        await broadcast({"type": "config_error", "message": f"설정 파일 읽기 실패: {e}"})
        return "error"
    log.info("설정 리로드됨")
    await broadcast({"type": "mapping_updated"})
    if state.client_ws is not None:
        try:
            await state.client_ws.send_json({"type": "mapping_updated"})
        except Exception:
            pass
    return "reloaded"


async def _watch_config() -> None:
    while True:
        await asyncio.sleep(2)
        try:
            await check_reload()
        except Exception:
            log.exception("설정 감시 오류 — 폴링 계속")


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(_watch_config())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(lifespan=lifespan)


def _binding_payload(b) -> dict:
    d = {"label": b.label, "icon": b.icon, "type": b.action["type"], "repeat": b.repeat}
    # launch 앱은 호스트의 실제 테마 아이콘을 서빙 — 해석 가능할 때만 icon_url 포함
    if b.action["type"] == "launch" and resolve_icon(b.action["app"]) is not None:
        d["icon_url"] = f"/api/icon/{b.action['app']}"
    return d


def mapping_payload() -> dict:
    return {
        "active_page": state.active_page,
        "pages": {
            name: {k: _binding_payload(b) for k, b in page.items()}
            for name, page in state.config.pages.items()
        },
    }


@app.get("/api/mapping")
async def get_mapping():
    return mapping_payload()


@app.get("/api/icon/{app}")
async def get_icon(app: str):
    configured = {
        b.action["app"]
        for page in state.config.pages.values()
        for b in page.values()
        if b.action["type"] == "launch"
    }
    if app not in configured:  # 설정된 launch 앱 외에는 파일 접근 자체를 차단
        raise HTTPException(status_code=404)
    path = resolve_icon(app)
    if path is None:
        raise HTTPException(status_code=404)
    return FileResponse(path)


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
    if state.client_ws is not None:
        await ws.close(code=1013)  # Try Again Later — 이미 클라이언트가 연결됨
        return
    await ws.accept()
    state.client_ws = ws
    await broadcast({"type": "client_status", "connected": True})
    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break
            # Hammerspoon hs.websocket:send()는 기본이 binary 프레임 — text/binary 모두 수용
            raw = message.get("text")
            if raw is None:
                data = message.get("bytes")
                if data is None:
                    continue
                raw = data.decode("utf-8", errors="replace")
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "key":
                await handle_key(msg)
            # hello/ping: 연결 유지용, 무시
    except WebSocketDisconnect:
        pass
    finally:
        if state.client_ws is ws:
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
