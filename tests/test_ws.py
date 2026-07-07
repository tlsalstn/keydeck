import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from server import actions
import server.main as main

client = TestClient(main.app)


def test_mapping_api():
    r = client.get("/api/mapping")
    assert r.status_code == 200
    body = r.json()
    assert body["active_page"] == "default"
    assert body["pages"]["default"]["F5"] == {
        "label": "재생", "icon": "⏯️", "type": "media", "repeat": False}


def test_bad_token_rejected():
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/client?token=wrong"):
            pass


@pytest.fixture
def ran(monkeypatch):
    recorded = []

    async def fake(action):
        recorded.append(action["op"])

    monkeypatch.setitem(actions.EXECUTORS, "media", fake)
    return recorded


def test_key_dispatch_and_dashboard_push(ran):
    with client.websocket_connect("/ws/dashboard") as dash:
        assert dash.receive_json()["type"] == "client_status"
        with client.websocket_connect("/ws/client?token=test-token") as c:
            assert dash.receive_json() == {"type": "client_status", "connected": True}
            c.send_json({"type": "key", "code": 96, "event": "down", "repeat": False})
            assert dash.receive_json() == {
                "type": "key", "key": "F5", "event": "down", "mapped": True}
            result = dash.receive_json()
            assert result["type"] == "action_result" and result["ok"] is True
            assert result["key"] == "F5" and result["label"] == "재생"
    assert ran == ["play-pause"]


def test_repeat_suppressed_unless_flagged(ran):
    with client.websocket_connect("/ws/client?token=test-token") as c:
        c.send_json({"type": "key", "code": 96, "event": "down", "repeat": True})   # F5: 무시
        c.send_json({"type": "key", "code": 97, "event": "down", "repeat": True})   # F6: 실행
        c.send_json({"type": "key", "code": 96, "event": "up", "repeat": False})    # up: 무시
        c.send_json({"type": "ping"})  # 플러시 겸 무해한 메시지
    assert ran == ["volume-up"]


def test_unmapped_key_no_action(ran):
    with client.websocket_connect("/ws/dashboard") as dash:
        dash.receive_json()
        with client.websocket_connect("/ws/client?token=test-token") as c:
            dash.receive_json()
            c.send_json({"type": "key", "code": 0, "event": "down", "repeat": False})
            assert dash.receive_json() == {
                "type": "key", "key": "A", "event": "down", "mapped": False}
    assert ran == []


def test_action_failure_pushed(monkeypatch):
    async def boom(action):
        raise actions.ActionError("고장")

    monkeypatch.setitem(actions.EXECUTORS, "media", boom)
    with client.websocket_connect("/ws/dashboard") as dash:
        dash.receive_json()
        with client.websocket_connect("/ws/client?token=test-token") as c:
            dash.receive_json()
            c.send_json({"type": "key", "code": 96, "event": "down", "repeat": False})
            dash.receive_json()  # key push
            result = dash.receive_json()
            assert result["ok"] is False and "고장" in result["error"]
