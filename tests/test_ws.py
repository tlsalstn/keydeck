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


def test_broadcast_survives_dashboard_churn():
    # 브로드캐스트 도중 셋이 변해도 스냅샷 순회라 안전한지: 대시보드 2개 + 키 이벤트
    with client.websocket_connect("/ws/dashboard") as d1:
        d1.receive_json()
        with client.websocket_connect("/ws/dashboard") as d2:
            d2.receive_json()
            with client.websocket_connect("/ws/client?token=test-token") as c:
                d1.receive_json(); d2.receive_json()  # client_status push
                c.send_json({"type": "key", "code": 96, "event": "down", "repeat": False})
                assert d1.receive_json()["type"] == "key"
                assert d2.receive_json()["type"] == "key"


def test_second_client_rejected():
    with client.websocket_connect("/ws/client?token=test-token") as c1:
        c1.send_json({"type": "ping"})
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/client?token=test-token") as c2:
                c2.receive_json()  # 거부 — close 1013


def test_second_client_close_does_not_clobber_first():
    with client.websocket_connect("/ws/dashboard") as dash:
        dash.receive_json()
        with client.websocket_connect("/ws/client?token=test-token") as c1:
            assert dash.receive_json() == {"type": "client_status", "connected": True}
            try:
                with client.websocket_connect("/ws/client?token=test-token") as c2:
                    c2.receive_json()
            except WebSocketDisconnect:
                pass
            # 두 번째 클라이언트 거부 후에도 첫 클라이언트 상태 유지: down 이벤트가 정상 디스패치되는지로 확인
            c1.send_json({"type": "key", "code": 0, "event": "down", "repeat": False})
            msg = dash.receive_json()
            assert msg["type"] == "key" and msg["key"] == "A"


def test_garbage_key_code_ignored(ran):
    with client.websocket_connect("/ws/client?token=test-token") as c:
        c.send_json({"type": "key", "code": "boom", "event": "down", "repeat": False})
        c.send_json({"type": "key", "code": None, "event": "down", "repeat": False})
        c.send_json({"type": "key", "code": 96, "event": "down", "repeat": False})
        c.send_json({"type": "ping"})
    assert ran == ["play-pause"]  # 쓰레기 코드는 무시, 정상 코드는 실행


def test_binary_frame_from_client_dispatches(ran):
    """Hammerspoon hs.websocket:send()는 기본이 binary 프레임 — 서버는 text/binary 모두 수용해야 한다."""
    import json as _json

    with client.websocket_connect("/ws/client?token=test-token") as c:
        c.send_bytes(_json.dumps(
            {"type": "key", "code": 96, "event": "down", "repeat": False}).encode())
        c.send_json({"type": "ping"})
    assert ran == ["play-pause"]


def test_icon_endpoint_serves_configured_app(monkeypatch, tmp_path):
    icon = tmp_path / "fake.png"
    icon.write_bytes(b"\x89PNG-fake")
    monkeypatch.setattr(main, "resolve_icon", lambda app: icon)
    r = client.get("/api/icon/org.kde.konsole")
    assert r.status_code == 200
    assert r.content == b"\x89PNG-fake"


def test_icon_endpoint_unknown_app_404(monkeypatch, tmp_path):
    icon = tmp_path / "fake.png"
    icon.write_bytes(b"x")
    monkeypatch.setattr(main, "resolve_icon", lambda app: icon)
    assert client.get("/api/icon/passwd").status_code == 404  # 설정에 없는 앱 차단


def test_icon_endpoint_unresolvable_404(monkeypatch):
    monkeypatch.setattr(main, "resolve_icon", lambda app: None)
    assert client.get("/api/icon/org.kde.konsole").status_code == 404


def test_mapping_payload_icon_url(monkeypatch, tmp_path):
    icon = tmp_path / "i.svg"
    icon.write_bytes(b"<svg/>")
    monkeypatch.setattr(main, "resolve_icon", lambda app: icon)
    body = client.get("/api/mapping").json()
    assert body["pages"]["default"]["F1"]["icon_url"] == "/api/icon/org.kde.konsole"
    assert "icon_url" not in body["pages"]["default"]["F5"]  # launch 외에는 없음


@pytest.fixture
def on_default_page():
    main.state.active_page = "default"
    yield
    main.state.active_page = "default"


def _connect_pair(dash_ctx, client_ctx):
    pass  # 가독성용 자리 — 각 테스트에서 직접 연결


def test_tab_cycles_next_and_wraps(on_default_page):
    with client.websocket_connect("/ws/dashboard") as dash:
        dash.receive_json()
        with client.websocket_connect("/ws/client?token=test-token") as c:
            dash.receive_json()
            c.send_json({"type": "key", "code": 48, "event": "down", "repeat": False})  # Tab
            assert dash.receive_json()["type"] == "key"
            assert dash.receive_json() == {"type": "page_changed", "page": "second"}
            c.send_json({"type": "key", "code": 48, "event": "down", "repeat": False})
            dash.receive_json()
            assert dash.receive_json() == {"type": "page_changed", "page": "default"}  # 순환


def test_shift_tab_cycles_prev(on_default_page):
    with client.websocket_connect("/ws/dashboard") as dash:
        dash.receive_json()
        with client.websocket_connect("/ws/client?token=test-token") as c:
            dash.receive_json()
            c.send_json({"type": "key", "code": 48, "event": "down",
                         "repeat": False, "shift": True})
            dash.receive_json()
            assert dash.receive_json() == {"type": "page_changed", "page": "second"}  # 역방향 순환


def test_fkey_direct_select(on_default_page):
    with client.websocket_connect("/ws/dashboard") as dash:
        dash.receive_json()
        with client.websocket_connect("/ws/client?token=test-token") as c:
            dash.receive_json()
            c.send_json({"type": "key", "code": 120, "event": "down", "repeat": False})  # F2
            dash.receive_json()
            assert dash.receive_json() == {"type": "page_changed", "page": "second"}
            # second 페이지에서 F1(미매핑) → 1번째 페이지(default)로 직접 이동
            c.send_json({"type": "key", "code": 122, "event": "down", "repeat": False})
            dash.receive_json()
            assert dash.receive_json() == {"type": "page_changed", "page": "default"}
    r = client.get("/api/mapping")
    assert r.json()["active_page"] == "default"


def test_mapped_key_beats_navigation(ran, on_default_page):
    """default 페이지의 F5는 매핑(media)이 우선 — 페이지 5 이동 아님."""
    with client.websocket_connect("/ws/client?token=test-token") as c:
        c.send_json({"type": "key", "code": 96, "event": "down", "repeat": False})
        c.send_json({"type": "ping"})
    assert ran == ["play-pause"]
    assert main.state.active_page == "default"


def test_fkey_without_page_noop(on_default_page):
    with client.websocket_connect("/ws/client?token=test-token") as c:
        c.send_json({"type": "key", "code": 101, "event": "down", "repeat": False})  # F9
        c.send_json({"type": "ping"})
    assert main.state.active_page == "default"


def test_page_action_binding(ran, on_default_page):
    """second 페이지의 E 키 = page 액션 → default로 복귀, 실행기 호출 없음."""
    main.state.active_page = "second"
    with client.websocket_connect("/ws/dashboard") as dash:
        dash.receive_json()
        with client.websocket_connect("/ws/client?token=test-token") as c:
            dash.receive_json()
            c.send_json({"type": "key", "code": 14, "event": "down", "repeat": False})  # E
            assert dash.receive_json()["mapped"] is True
            assert dash.receive_json() == {"type": "page_changed", "page": "default"}
    assert ran == []


def test_per_page_dispatch(ran, on_default_page):
    """같은 F5라도 페이지에 따라 다른 액션."""
    main.state.active_page = "second"
    with client.websocket_connect("/ws/client?token=test-token") as c:
        c.send_json({"type": "key", "code": 96, "event": "down", "repeat": False})
        c.send_json({"type": "ping"})
    assert ran == ["next"]


def test_key_by_name_dispatches(ran):
    """key 이름 직접 전송 경로 (리눅스 클라이언트)."""
    with client.websocket_connect("/ws/client?token=test-token") as c:
        c.send_json({"type": "key", "key": "F5", "event": "down", "repeat": False})
        c.send_json({"type": "ping"})
    assert ran == ["play-pause"]


def test_key_by_name_navigation(on_default_page):
    """이름 경로에서도 Tab 페이지 내비게이션 동작."""
    with client.websocket_connect("/ws/dashboard") as dash:
        dash.receive_json()
        with client.websocket_connect("/ws/client?token=test-token") as c:
            dash.receive_json()
            c.send_json({"type": "key", "key": "Tab", "event": "down", "repeat": False})
            assert dash.receive_json()["type"] == "key"
            assert dash.receive_json() == {"type": "page_changed", "page": "second"}


def test_code_path_still_works(ran):
    """기존 kVK code 경로 회귀 (Mac 클라이언트)."""
    with client.websocket_connect("/ws/client?token=test-token") as c:
        c.send_json({"type": "key", "code": 96, "event": "down", "repeat": False})
        c.send_json({"type": "ping"})
    assert ran == ["play-pause"]


def test_invalid_key_name_ignored(ran, on_default_page):
    """이름 공간 밖 key는 무시 — 실행도, 대시보드 push도 없음."""
    with client.websocket_connect("/ws/dashboard") as dash:
        dash.receive_json()
        with client.websocket_connect("/ws/client?token=test-token") as c:
            dash.receive_json()  # client_status
            c.send_json({"type": "key", "key": "__proto__", "event": "down", "repeat": False})
            c.send_json({"type": "key", "key": "NotAKey", "event": "down", "repeat": False})
            c.send_json({"type": "key", "key": "F5", "event": "down", "repeat": False})
            first = dash.receive_json()  # 무효 이름 2개는 push가 없어야 하므로 첫 push는 F5
            assert first == {"type": "key", "key": "F5", "event": "down", "mapped": True}
    assert ran == ["play-pause"]
