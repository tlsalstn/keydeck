# MacPad — MacBook 키보드를 Fedora 매크로 패드로 (설계 스펙)

날짜: 2026-07-07
상태: 사용자 리뷰 대기

## 1. 개요

MacBook Pro(M1, macOS Tahoe 26.x)의 키보드를 Fedora Linux 44(KDE Plasma 6.7, Wayland) 데스크톱의 매크로 패드로 사용한다. Mac에서 백그라운드로 키를 캡처해 호스트로 전송하고, 호스트는 키에 매핑된 동작을 실행한다. 호스트가 서빙하는 웹 대시보드(뷰어 전용)에서 매핑과 실시간 키 입력을 확인할 수 있다.

### 확정된 요구사항 (사용자 결정)

| 항목 | 결정 |
|---|---|
| 캡처 방식 | Mac 네이티브 도구 (브라우저 아님). 브라우저는 매핑 확인용 뷰어 전용 |
| 사용 모드 | 토글 모드 + 전체 키보드 — 매크로 모드 ON이면 전체 키보드가 패드가 되고 macOS에 키가 전달되지 않음 |
| 동작 종류 | 앱/스크립트 실행, 단축키 주입, 미디어/시스템 제어, 텍스트 스니펫. 장기적으로 Elgato Stream Deck 기능 전체 커버 |
| 진행 방식 | 단계적 — v1: 코어 액션 7종 + 대시보드, v2: sequence·toggle·page |
| 키 단위 | 단일 물리 키 = 버튼 1개 (모디파이어 조합 없음, Stream Deck 방식) |
| 웹 기능 | 뷰어 전용 (매핑 편집은 호스트 설정 파일로) |
| 네트워크 | LAN (호스트 `<host-ip>`), 포트 8787, 공유 토큰 인증 |
| 서버 스택 | Python + FastAPI |
| 토글 단축키 | ⌘⌥⌃M |

## 2. 아키텍처

```
MacBook (client)                         Fedora (host)
┌────────────────────────┐              ┌─────────────────────────────────┐
│ Hammerspoon (Lua)      │              │ Python FastAPI 서버 (:8787)      │
│  · eventtap 전역 캡처   │──WebSocket──▶│  · 키 이벤트 → 매핑 조회          │
│  · 토글 ⌘⌥⌃M / 메뉴바   │  /ws/client  │  · 액션 실행                     │
│  · 매핑 JSON 다운로드    │◀─────────────│    shell/D-Bus/ydotool/wl-copy  │
└────────────────────────┘   LAN        │  · 웹 대시보드 서빙 + 실시간 push  │
                                        └─────────────────────────────────┘
       MacBook 브라우저 ── HTTP + /ws/dashboard ──▶ 대시보드 (뷰어)
```

**매핑의 단일 소스는 호스트의 `config/mapping.yaml`.** Hammerspoon(메뉴바 표시용)과 대시보드 모두 서버 API에서 받아간다. 클라이언트에는 매핑 로직이 없다 — 키 코드를 보내기만 하고, 해석·실행은 전부 서버가 한다.

### 리서치 근거 (핵심 결정 이유)

- **wtype 불가**: KWin은 가상 키보드 프로토콜(zwp_virtual_keyboard_v1) 미구현.
- **ydotool 채택**: uinput 커널 레벨 주입이라 컴포지터 무관하게 동작. 호스트에 이미 설치됨(1.0.4). 포털 RemoteDesktop/libei는 개인 LAN 서버에는 과잉.
- **주입 최소화**: 앱 실행·미디어·KDE 제어는 명령/D-Bus(`gio launch`, `playerctl`/`wpctl`, `kglobalaccel invokeShortcut`)로 주입 없이 실행 — 매크로 용도 대부분을 커버하고 포커스 의존성이 없다.
- **Hammerspoon 채택**: eventtap으로 키를 삼킬 수 있고(`return true`), 영구 WebSocket으로 키당 1–5ms 전송(Karabiner shell_command는 키당 프로세스 포크로 100–200ms), TCC 권한이 Accessibility 1개(Karabiner는 3개 + Tahoe 26.1+ 승인 버그 다수), 메뉴바·알림 UX 내장.

## 3. 매핑 설정 스키마 (`config/mapping.yaml`)

```yaml
server:
  port: 8787
  token: "<공유 토큰>"

pages:
  default:                # v1은 default 페이지만 사용, 스키마는 v2 페이지 전환 대비
    F1:
      label: "터미널"
      action: { type: launch, app: org.kde.konsole }
    F2:
      label: "빌드"
      action: { type: shell, cmd: "~/scripts/build.sh" }
    F3:
      label: "붙여넣기"
      action: { type: hotkey, keys: [ctrl, shift, v] }
    F4:
      label: "인사말"
      action: { type: text, text: "안녕하세요. 팀오투 마일즈입니다." }
    F5:
      label: "재생/정지"
      action: { type: media, op: play-pause }
    F6:
      label: "볼륨 +"
      action: { type: media, op: volume-up }
      repeat: true         # 키를 누르고 있으면 auto-repeat 이벤트에도 재실행
    F7:
      label: "오버뷰"
      action: { type: kde, component: kwin, shortcut: Overview }
    F8:
      label: "문서"
      action: { type: url, url: "https://docs.example.com" }
```

### v1 액션 타입 (7종)

| 타입 | 실행 방법 | 비고 |
|---|---|---|
| `shell` | `subprocess` (사용자 셸 경유 없이 exec) | 임의 명령·스크립트 |
| `launch` | `gio launch <.desktop>` | 데스크톱 앱 실행 |
| `url` | `xdg-open` | 브라우저/URL 열기 |
| `hotkey` | ydotool `key` (evdev 키코드 시퀀스) | 포커스된 창에 키 조합 주입 |
| `text` | 기존 클립보드 백업 → `wl-copy` → ydotool Ctrl+V 주입 → 클립보드 복원 | 한글 포함 임의 텍스트, 레이아웃 무관 |
| `media` | `playerctl` (재생 제어) / `wpctl` (볼륨) | op: play-pause, next, previous, volume-up, volume-down, mute |
| `kde` | `gdbus call` → `org.kde.kglobalaccel` invokeShortcut | KDE 전역 단축키 직접 호출 (가상 데스크톱, 스크린샷 등) |

### v2 예약 (이번 구현 범위 아님)

- `sequence` — 멀티 액션: steps 배열 + delay(ms)
- `toggle` — 상태 순환 키 (상태별 label/action, 대시보드에 상태 표시)
- `page` — 페이지 전환 (Stream Deck 프로필/폴더 대응)
- 액션 실행기는 레지스트리(dict[type → executor]) 구조로 만들어 타입 추가만으로 확장 가능해야 한다.

### 키 이름

- 매핑 키는 물리 키 이름(`F1`…`F12`, `A`…`Z`, `Digit1`…, `Space` 등, ANSI US MacBook 기준).
- 클라이언트는 macOS 가상 키코드(kVK, 숫자)를 그대로 전송하고, 서버가 정적 kVK→이름 테이블(`server/keycodes.py`)로 변환한다. 레이아웃 변경에 영향받지 않는다.
- 모디파이어 키 자체(⌘⇧⌥⌃, fn)는 v1에서 매핑 불가 (macOS에서 flagsChanged 이벤트로 별도 처리 필요 — v2 검토).
- MacBook 상단 F열을 쓰려면 macOS "F1, F2 등의 키를 표준 기능 키로 사용" 설정 필요 (셋업 문서에 포함).

## 4. 클라이언트 — Hammerspoon (`client/init.lua`)

**역할: 키 캡처와 전송만. 매핑 해석 없음.**

- **연결**: 시작 시 `ws://<host>:8787/ws/client?token=<token>`에 영구 WebSocket 연결. 끊기면 2초 백오프로 재연결. 30초 간격 ping.
- **캡처**: `hs.eventtap`으로 keyDown/keyUp 구독. 매크로 모드 ON일 때:
  - 토글 단축키(⌘⌥⌃M)는 eventtap 콜백 안에서 먼저 검사해 항상 동작하게 한다 (모드 진입 후에도 빠져나올 수 있어야 함).
  - 그 외 모든 키: `{"type":"key","code":<kVK>,"event":"down"|"up","repeat":bool}` 전송 후 `return true`로 이벤트 삼킴.
  - 모드 OFF면 `return false` — 키가 macOS로 정상 전달.
- **토글 UX**: 메뉴바 아이콘(⌨️ ON / 회색 OFF / ⚠️ 연결 끊김), 모드 전환 시 `hs.alert` 화면 표시.
- **페일세이프 (설계 원칙: 실패 시 키보드는 항상 사용자에게 돌아간다)**:
  - WebSocket 끊김 → 매크로 모드 자동 OFF + 메뉴바 경고. Mac 키보드가 먹통이 되는 상황 방지.
  - eventtap 워치독: 5초마다 `tap:isEnabled()` 확인, 꺼져 있으면 재시작 (macOS가 조용히 끄는 알려진 문제 대응).
  - eventtap 콜백은 논블로킹 유지 — 이미 열린 WS로 send만 하고, 콜백 안에서 동기 HTTP 호출 금지.
- **매핑 표시**: 시작 시와 서버의 `mapping_updated` push 수신 시 `GET /api/mapping` 로드 — 메뉴바 메뉴에 키 목록 표시용 (선택 기능).
- **알려진 한계 (수용)**: Secure Input 활성화 중(암호 필드 포커스)에는 eventtap이 키를 보지 못함. 매크로 모드 사용 중 암호 입력을 하지 않는 한 영향 없음.

설치: `brew install --cask hammerspoon` + Accessibility 권한 1회 승인 + 로그인 시 시작 설정.

## 5. 호스트 서버 — Python FastAPI (`server/`)

의존성: 전부 Fedora 공식 RPM으로 설치 — `python3-fastapi`, `python3-uvicorn`, `python3-websockets`, `python3-pyyaml`. pip/PyPI/venv를 사용하지 않는다. 인터프리터는 Fedora 공식 `/usr/bin/python3`(3.14)을 절대 경로로 사용한다 (PATH의 linuxbrew python3이 아님 — systemd 서비스에 절대 경로 명시).

### 엔드포인트

| 경로 | 용도 | 인증 |
|---|---|---|
| `GET /` + `/static/*` | 대시보드 (정적 파일) | 없음 (LAN, 뷰어 전용) |
| `GET /api/mapping` | 현재 매핑 + 활성 페이지 JSON | 없음 (읽기 전용) |
| `WS /ws/client` | Mac 키 이벤트 수신 | `?token=` 필수 — 불일치 시 연결 거부 |
| `WS /ws/dashboard` | 대시보드 실시간 push | 없음 (송신 전용, 수신 명령 무시) |

### 처리 흐름

1. `/ws/client`에서 key 이벤트 수신 (`down`/`up`, kVK 코드).
2. kVK → 키 이름 변환 → 활성 페이지 매핑 조회.
3. `down`(repeat 아님) → 액션 실행. `repeat: true`로 표시된 키만 auto-repeat 이벤트에도 재실행. `up`은 v1에서 무시(대시보드 하이라이트 해제용으로만 push).
4. 실행 결과(성공/실패, 소요 시간)를 `/ws/dashboard`로 push.
5. 매핑에 없는 키 → 실행 없이 대시보드에 "unmapped" 표시.

### 액션 실행기

- 레지스트리 구조: `EXECUTORS: dict[str, Callable]` — v2 타입은 항목 추가만으로 확장.
- **보안 불변식: 네트워크에서 오는 것은 키 코드뿐. 명령·키코드·경로 등 실행 내용은 전부 호스트 로컬 설정 파일에서만 온다.** 클라이언트가 임의 명령을 실행시킬 수 있는 경로는 존재하지 않는다.
- 액션 실행은 비동기(asyncio) — 오래 걸리는 shell 액션이 후속 키 처리를 막지 않는다.
- `hotkey`: 사람이 읽는 키 이름(`[ctrl, shift, v]`)을 evdev 키코드로 변환하는 테이블 포함, `ydotool key <code>:1 ... <code>:0` 호출. `YDOTOOL_SOCKET=/tmp/.ydotool_socket` 환경 변수 필요.
- `text`: `wl-paste`로 기존 클립보드 백업 → `wl-copy`로 스니펫 설정 → ydotool Ctrl+V → 300ms 후 클립보드 복원.

### 설정 관리

- 시작 시 `config/mapping.yaml` 로드 + 스키마 검증 (알 수 없는 액션 타입, 필수 필드 누락, 잘못된 키 이름은 명확한 오류 메시지).
- 파일 변경 감지(mtime 폴링, 2초) → 리로드. 검증 실패 시 이전 유효 설정 유지 + 대시보드에 오류 표시.
- 리로드 성공 시 `mapping_updated`를 클라이언트·대시보드에 push.

### 배포

- systemd user 서비스(`macpad.service`)로 상시 구동. `Environment=YDOTOOL_SOCKET=/tmp/.ydotool_socket`.
- `0.0.0.0:8787` 바인드 (LAN 접속), firewalld 포트 개방은 셋업 문서에 포함.

## 6. 웹 대시보드 (`server/static/`)

빌드 스텝 없는 정적 HTML/CSS/JS 단일 페이지.

**비주얼: Elgato Stream Deck의 LCD 화면처럼 보여야 한다.**

- 다크 하드웨어 톤 배경 위에 MacBook 키보드 물리 배열을 유지한 키 그리드. 각 키는 Stream Deck 키를 본뜬 **라운드 사각 LCD 타일** — 매핑된 키는 아이콘(emoji) + 라벨이 점등된 LCD처럼 표시, 미매핑 키는 꺼진 LCD(어두운 타일)로 표시.
- 매핑 스키마에 선택 필드 `icon`(emoji 문자열)을 추가한다. 예: `F5: { label: "재생/정지", icon: "⏯️", action: ... }`. icon이 없으면 라벨만 표시.
- 키 누름(down) 시 해당 타일 발광 하이라이트 + 살짝 눌리는 애니메이션, up에 해제 — 실제 Stream Deck 버튼을 누른 듯한 피드백.
- 액션 실행 결과: 성공 시 타일에 순간 초록 글로우, 실패 시 빨간 글로우 + 오류 토스트.
- 상단 상태 바: Mac 클라이언트 연결 상태 배지, 활성 페이지 이름(v2 대비), 설정 리로드 알림.
- 매핑 데이터는 `GET /api/mapping`, 이후 `mapping_updated` push 시 다시 로드.
- 대시보드 WS는 재연결 로직 포함 (탭 백그라운드 스로틀링 대응은 서버측 ping으로 해결).

## 7. WebSocket 메시지 프로토콜

```jsonc
// client → server (/ws/client)
{"type": "hello", "client": "hammerspoon", "version": 1}
{"type": "key", "code": 122, "event": "down", "repeat": false}   // code = macOS kVK

// server → client (/ws/client)
{"type": "mapping_updated"}

// server → dashboard (/ws/dashboard)
{"type": "key", "key": "F1", "event": "down", "mapped": true}
{"type": "action_result", "key": "F1", "label": "터미널", "ok": true, "error": null}
{"type": "client_status", "connected": true}
{"type": "mapping_updated"}
{"type": "config_error", "message": "..."}
```

## 8. 에러 처리 / 페일세이프 요약

| 상황 | 동작 |
|---|---|
| WS 단절 (Mac 측) | 매크로 모드 자동 OFF, 메뉴바 ⚠️, 2초 백오프 재연결 |
| eventtap 비활성화 | 워치독이 5초 내 재시작 |
| ydotool 소켓 없음/실패 | 해당 액션 실패 처리 + 대시보드 토스트, 서버는 계속 동작 |
| 액션 실행 실패 (비정상 종료코드/예외) | 대시보드에 오류 push + 서버 로그 |
| 설정 파일 오류 | 이전 유효 설정 유지 + config_error push |
| 토큰 불일치 | /ws/client 연결 거부 (401) |

## 9. 셋업 요구사항 (구현 계획에 셋업 스크립트/문서로 포함)

**호스트 (Fedora, 전부 공식 저장소 패키지):**
1. `sudo dnf install python3-fastapi python3-uvicorn python3-websockets python3-pyyaml playerctl` (ydotool은 설치됨)
2. `sudo systemctl enable --now ydotool` (uinput 모듈 로드 포함 — 현재 `/dev/uinput` 없음 확인됨)
3. systemd user 서비스 등록 (`ExecStart=/usr/bin/python3 -m uvicorn ...` 절대 경로)
4. firewalld: 8787/tcp 허용 (LAN zone)

**클라이언트 (Mac):**
1. `brew install --cask hammerspoon`
2. `client/init.lua` 배치 (호스트 IP·토큰 설정)
3. Accessibility 권한 승인, 로그인 시 시작
4. macOS 키보드 설정: "F1, F2 등의 키를 표준 기능 키로 사용" ON (F열을 매크로 키로 쓸 경우)

## 10. 테스트 전략

- **서버 단위 테스트 (pytest)**: 설정 파싱·검증(정상/오류 케이스), kVK→키 이름 변환, 액션 디스패치(실행기는 mock), repeat 억제 로직, 토큰 인증.
- **Mac 없이 E2E**: `scripts/fake_client.py` — 가짜 키 이벤트를 WS로 주입해 호스트 전체 경로(수신→매핑→실행→대시보드 push)를 실기기 없이 검증.
- **실기기 검증 체크리스트**: 토글 UX·키 삼킴 확인, 체감 지연, 한글 스니펫 + 클립보드 복원, WS 단절 시 페일오픈, ydotool 주입 대상 앱 포커스 동작.

## 11. 범위 밖 (명시)

- 웹에서 매핑 편집 (뷰어 전용 확정)
- 모디파이어 조합 키, 모디파이어 키 자체 매핑
- v2 액션 (sequence, toggle, page) — 스키마·레지스트리만 대비
- Tailscale/외부 접속, HTTPS (LAN 전용 확정)
- Secure Input 중 캡처 (Hammerspoon 한계로 수용)
