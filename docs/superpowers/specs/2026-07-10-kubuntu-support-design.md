# keydeck Kubuntu 지원 — 설계 스펙

날짜: 2026-07-10
상태: 사용자 리뷰 대기

## 1. 개요

keydeck을 **클라이언트·호스트 양쪽에서 Kubuntu(KDE Plasma)** 를 선택지로 지원하도록 확장한다. 기존 조합(클라이언트 macOS / 호스트 Fedora)은 그대로 유지하면서, 다음 두 조각을 추가한다:

1. **호스트 이식성** — Fedora ↔ Kubuntu. KDE 결합 코드(KWin 스크립팅·kglobalaccel)는 양쪽에서 동일하게 동작하므로 손대지 않는다. 실제 차이는 오디오 백엔드(PipeWire↔PulseAudio)와 패키징뿐이다.
2. **리눅스 클라이언트 신규 개발** — evdev 기반으로 Kubuntu를 매크로 패드 클라이언트로 사용. macOS Hammerspoon 클라이언트와 동일한 역할.

### 확정된 결정 (사용자 승인)

| 항목 | 결정 |
|---|---|
| 대상 DE | Kubuntu (KDE Plasma). GNOME은 범위 밖 |
| 지원 범위 | 문서/패키징 + 런타임 코드 견고성(오디오 폴백) + 리눅스 클라이언트 |
| 키 프로토콜 | 접근 A — 클라이언트가 물리 키 **이름** 전송, 서버는 `key`(이름) 또는 `code`(kVK) 모두 수용 |
| 상태 표시 | 알림만 (`notify-send`), 지속 상태는 웹 대시보드 배지. 트레이 아이콘 없음 |
| 토글 키 | Ctrl+Alt+M (리눅스엔 Cmd 없음) |
| grab 범위 | 모든 키보드 장치 |
| 검증 | Kubuntu 실기기 보유 — 통합 검증 가능 |
| 진행 | 호스트 이식성 + 리눅스 클라이언트를 한 스펙으로 |

## 2. 아키텍처

```
클라이언트: macOS(Hammerspoon)  또는  Kubuntu(evdev 클라이언트, 신규)
                   │  WebSocket  {key | code, event, repeat, shift}
                   ▼
호스트:     Fedora  또는  Kubuntu (FastAPI, :8787)
            · KWin 스크립팅 창 포커스 (양 배포판 동일)
            · kglobalaccel kde 액션 (양 배포판 동일)
            · 오디오: wpctl(PipeWire) 또는 pactl(PulseAudio) — 신규 폴백
```

서버가 아는 계약은 "물리 키 이름 + 액션"뿐이다. 플랫폼별 키코드 변환 책임은 각 클라이언트가 가진다.

## 3. 키 프로토콜 (접근 A)

- 리눅스 클라이언트는 evdev 코드를 읽어 로컬에서 keydeck 이름(`"F1"`, `"Grave"`, `"Digit1"`, `"A"`, `"Comma"` 등 — `server/keycodes.py`의 `KVK_TO_NAME` 값과 동일한 이름 공간)으로 변환해 `{"type":"key","key":"F1","event":"down"|"up","repeat":bool,"shift":bool}`를 전송한다.
- 서버 `handle_key`: 메시지에 `key`(문자열)가 있으면 그대로 이름으로 사용하고, 없으면 기존처럼 `code`(정수 kVK)→`key_name()`으로 변환한다. **Mac 클라이언트(코드 전송)는 무손상.**
- 그 외 디스패치 규칙(매핑 우선, 페이지 내비게이션, repeat 억제, page 액션)은 이름이 정해진 뒤 동일하게 적용된다.

## 4. 리눅스 클라이언트 (`client/linux/`)

역할은 macOS 클라이언트와 동일: **키 캡처·차단·전송만. 매핑 해석·실행은 서버.**

### 4.1 `keymap.py` — 순수 변환 테이블
- `EVDEV_TO_NAME: dict[int, str]` — 리눅스 `input-event-codes.h`의 `KEY_*` 코드 → keydeck 이름.
- `key_name(evdev_code: int) -> str | None`.
- 매핑에 실제 쓰이는 키를 모두 포함: `Grave`(KEY_GRAVE=41), `Digit1`~`Digit0`(KEY_1..KEY_0), `Minus`/`Equal`, `Q`~`P` 행, `LeftBracket`/`RightBracket`/`Backslash`, `A`~`L` 행, `Semicolon`/`Quote`, `Z`~`M` 행, `Comma`(KEY_COMMA=51)/`Period`(KEY_DOT=52)/`Slash`, `Space`, `Tab`, `Return`(KEY_ENTER=28), `Escape`, `F1`~`F12`, 방향키/Home/End 등.
- 모디파이어 키도 이름을 갖되(예: `LeftShift`, `LeftCtrl`, `LeftAlt`), 이들은 mode.py가 매크로 키가 아니라 상태/토글 감지용으로 소비한다.

### 4.2 `mode.py` — 순수 상태 머신
evdev·WS I/O 없이 테스트 가능한 결정 로직.

- 입력: `process(name: str | None, event: str)` — `event`는 `"down"|"up"|"repeat"`, `name`은 keymap이 변환한 이름(미지원 코드면 None).
- 내부 상태: 현재 눌린 모디파이어 집합(Ctrl/Alt/Shift), 매크로 모드 on/off.
- 토글 감지: Ctrl+Alt 가 눌린 상태에서 `M` down → 토글. 오토리피트(`repeat`)로 인한 연속 토글 방지(첫 down만). 토글 시 해당 M의 up도 전송하지 않도록 삼킴 플래그 관리(macOS 클라이언트의 `swallowToggleUp`과 동일 개념).
- 반환(결정): 다음 중 하나 이상 — `toggle`(grab/ungrab 필요), `send`(WS 메시지 dict 생성: `{type:"key", key, event, repeat, shift}`), `none`.
- OFF 상태: 매크로 키 전송 안 함(토글 조합만 감시). ON 상태: 토글 키를 제외한 모든 키를 send.
- `shift` 플래그: 현재 Shift 눌림 여부를 send 메시지에 실어 서버의 Shift+Tab 역방향 페이지 이동을 지원.

### 4.3 `keydeck_client.py` — I/O 배선
- **장치 검색**: `evdev.list_devices()`에서 `EV_KEY`+`KEY_A` 등 키보드 능력을 가진 장치를 모두 선택.
- **비동기 read**: 각 장치를 asyncio 태스크로 `async_read_loop()`. 이벤트를 keymap→mode에 넘겨 결정을 실행.
- **grab/ungrab**: mode가 토글 ON 결정 → 모든 대상 장치 `device.grab()`(로컬 세션 차단). OFF → `device.ungrab()`.
- **WS**: `ws://<host>:<port>/ws/client?token=<token>`, 텍스트 프레임 전송, 2초 백오프 재연결, 30초 ping.
- **알림**: 모드 전환·연결 끊김 시 `notify-send`.
- **페일세이프**: WS 끊김 → 즉시 ungrab + OFF + 알림. SIGTERM/SIGINT → ungrab 후 종료. 크래시 → 커널이 fd 닫힘으로 grab 자동 해제.
- **설정**: 파일 상단 상수 또는 환경변수로 `HOST`/`PORT`/`TOKEN`(플레이스홀더 `CHANGE-ME-*`). macOS `init.lua`와 동일한 관례.

## 5. 호스트 오디오 폴백 (`server/actions.py`)

- `playerctl` 기반(play-pause/next/previous, MPRIS)은 백엔드 무관 — 변경 없음.
- 볼륨/음소거만 백엔드 분기. 모듈 로드 시 1회 감지:
  - `shutil.which("wpctl")` 존재 → PipeWire 명령 세트 (기존 `wpctl ...`).
  - 아니면 `shutil.which("pactl")` → PulseAudio 세트:
    - volume-up: `pactl set-sink-volume @DEFAULT_SINK@ +5%`
    - volume-down: `pactl set-sink-volume @DEFAULT_SINK@ -5%`
    - mute: `pactl set-sink-mute @DEFAULT_SINK@ toggle`
  - 둘 다 없으면 볼륨 op 실행 시 `ActionError`.
- `MEDIA_OPS`를 백엔드별로 구성하는 팩토리로 리팩터. 선택 로직은 `which`를 mock해 단위 테스트.

## 6. 배포·패키징

**공식 패키지만 사용.** README에 배포판별 표를 추가:

| 역할 | Fedora (dnf) | Kubuntu (apt) |
|---|---|---|
| 서버 | python3-fastapi python3-uvicorn python3-websockets python3-pyyaml playerctl wireplumber ydotool | python3-fastapi python3-uvicorn python3-websockets **python3-yaml** playerctl wireplumber ydotool |
| 리눅스 클라이언트 | python3-evdev python3-websockets libnotify | python3-evdev python3-websockets libnotify-bin |

- 클라이언트 사용자는 `input` 그룹 소속 필요(이미 충족 확인).
- 클라이언트 상시 구동: systemd **user** 서비스 `keydeck-client.service`(`ExecStart=/usr/bin/python3 -m client.linux.keydeck_client` 또는 절대 경로 스크립트).
- ydotool은 호스트 전용(클라이언트 불필요). Ubuntu의 ydotool 버전/소켓 차이는 셋업 문서에 주의로 명시.

## 7. 에러 처리 요약

| 상황 | 동작 |
|---|---|
| 클라이언트 WS 끊김 | ungrab + 매크로 OFF + 알림, 2초 백오프 재연결 |
| 클라이언트 프로세스 크래시 | 커널이 grab 자동 해제 → 로컬 키보드 복귀 |
| SIGTERM/SIGINT | ungrab 후 정상 종료 |
| 매크로 ON 중 토글 조합 | 항상 클라이언트가 먼저 처리 → 탈출 보장 |
| 호스트 오디오 백엔드 없음 | 볼륨 op 실패(ActionError) + 대시보드 토스트 |

## 8. 테스트 전략

- **단위(Fedora에서 실행, `/usr/bin/python3 -m pytest`)**:
  - `test_linux_keymap.py`: evdev 코드→이름 대표 키 + 미지원 코드 None.
  - `test_linux_mode.py`: 토글 진입/탈출, 오토리피트 연속 토글 방지, 매크로 ON 중 키→send 메시지 정확성, `shift` 플래그, OFF 중 전송 안 함, 토글 키 up 삼킴.
  - `test_ws.py`(추가): `key` 이름 직접 수신 경로 + 기존 `code` 경로 회귀.
  - `test_actions.py`(추가): 오디오 백엔드 선택(wpctl/pactl `which` mock), pactl 명령 형태.
- **통합(Kubuntu 실기기 체크리스트)**:
  - 클라이언트: grab로 로컬 세션 키 차단 확인, Ctrl+Alt+M 토글·알림, 실제 매크로가 호스트에서 실행, WS 끊김 시 키보드 즉시 복귀, systemd user 서비스 자동 시작.
  - 호스트-Kubuntu: 볼륨(pactl 경로) 동작, 창 포커스(KWin 동일) 동작, kde 액션 동작.

## 9. 파일 구조

**신규**
- `client/linux/__init__.py`
- `client/linux/keymap.py`
- `client/linux/mode.py`
- `client/linux/keydeck_client.py`
- `systemd/keydeck-client.service`
- `tests/test_linux_keymap.py`
- `tests/test_linux_mode.py`

**수정**
- `server/main.py` — `handle_key`에 `key` 이름 직접 수용
- `server/actions.py` — `exec_media` 오디오 백엔드 폴백
- `tests/test_ws.py`, `tests/test_actions.py` — 위 경로 커버
- `README.md` — 배포판별 설치 표 + 리눅스 클라이언트 셋업 절차

## 10. 범위 밖 (명시)

- GNOME 데스크톱 지원 (KWin/kglobalaccel 결합 유지)
- 트레이 아이콘 (알림으로 대체)
- 키보드 핫플러그 시 장치 재검색 (시작 시 1회 검색)
- 클라이언트에서 매핑 편집
- 클라이언트 측 실제 키 주입/실행 (서버 책임 유지)
