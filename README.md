# MacPad

MacBook 키보드 → Fedora KDE Wayland 매크로 패드

MacBook Pro의 키보드를 백그라운드에서 캡처해 LAN으로 전송하고, Fedora 호스트가 매핑된 동작(앱 실행, 단축키 주입, 미디어 제어, 텍스트 스니펫 등)을 실행합니다. 호스트가 서빙하는 웹 대시보드에서 Stream Deck LCD 스타일로 매핑과 실시간 키 입력을 확인할 수 있습니다.

## 구조

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

매핑의 단일 소스는 호스트의 `config/mapping.yaml`입니다. Hammerspoon과 대시보드 모두 서버 API에서 매핑을 받아가며, 클라이언트에는 매핑 해석·실행 로직이 없습니다 — 키 코드를 보내기만 합니다. 네트워크로 오가는 것은 키 코드뿐이고, 실제로 무엇을 실행할지는 전부 호스트 로컬 설정 파일(`config/mapping.yaml`)에서만 정해집니다.

## 호스트 셋업 (Fedora)

### 1. 의존성 설치

전부 Fedora 공식 저장소 RPM으로 설치합니다 (pip/venv 사용 안 함):

```bash
sudo dnf install -y python3-fastapi python3-uvicorn python3-websockets python3-pyyaml python3-pytest python3-httpx playerctl
```

확인: `/usr/bin/python3 -c "import fastapi, uvicorn, yaml, websockets; print('ok')"` → `ok`

### 2. ydotool, firewalld, systemd 서비스

`hotkey`/`text` 액션은 uinput 가상 키보드(ydotool)를 통해 키를 주입합니다. ydotool 데몬을 켜야 합니다:

```bash
sudo systemctl enable --now ydotool
YDOTOOL_SOCKET=/tmp/.ydotool_socket ydotool key 29:1 29:0 && echo "ydotool ok"
```

방화벽에서 LAN 접근을 위해 8787/tcp를 엽니다:

```bash
sudo firewall-cmd --add-port=8787/tcp --permanent && sudo firewall-cmd --reload
```

`cp config/mapping.example.yaml config/mapping.yaml` 후 토큰 생성해 기입합니다(클라이언트 `client/init.lua`의 `TOKEN`과 반드시 동일해야 함). `config/mapping.yaml`은 실제 토큰을 담으므로 git에 추적되지 않습니다(`.gitignore`). 이후 systemd user 서비스로 등록합니다:

```bash
/usr/bin/python3 -c "import secrets; print(secrets.token_urlsafe(32))"  # → config/mapping.yaml의 token에 반영

mkdir -p ~/.config/systemd/user
cp systemd/macpad.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now macpad
systemctl --user status macpad --no-pager | head -5
```

기대 결과: `Active: active (running)`. LAN 접근 확인:

```bash
curl -s http://192.168.0.127:8787/api/mapping | head -c 80
```

### 3. `config/mapping.yaml` 편집

```yaml
server:
  port: 8787
  token: "<공유 토큰>"

pages:
  default:
    F1: { label: "터미널", icon: "🖥️", action: { type: launch, app: org.kde.konsole } }
    F2: { label: "알림 테스트", icon: "🔔", action: { type: shell, cmd: "notify-send MacPad 눌림" } }
    F3: { label: "붙여넣기", icon: "📋", action: { type: hotkey, keys: [ctrl, shift, v] } }
    F4: { label: "인사말", icon: "✉️", action: { type: text, text: "안녕하세요." } }
    F5: { label: "재생/정지", icon: "⏯️", action: { type: media, op: play-pause } }
    F6: { label: "볼륨 +", icon: "🔊", action: { type: media, op: volume-up }, repeat: true }
    F7: { label: "오버뷰", icon: "🗂️", action: { type: kde, component: kwin, shortcut: Overview } }
    F8: { label: "문서", icon: "🌐", action: { type: url, url: "https://kde.org" } }
```

`server.port` 필드는 현재 참고용이며 실제 리스닝 포트는 systemd 유닛의 `--port 8787`이 결정합니다.

- `label`: 대시보드에 표시할 이름 (필수)
- `icon`: emoji 문자열 (선택, 없으면 라벨만 표시)
- `repeat: true`: 키를 누르고 있을 때 auto-repeat 이벤트에도 액션을 재실행 (볼륨 조절 등)
- 키 이름은 물리 키 이름(`F1`…`F12`, `A`…`Z`, `Digit1`…, `Space` 등, ANSI US MacBook 기준)이며 `server/keycodes.py`의 kVK→이름 테이블 기준입니다.
- 파일은 2초 간격으로 폴링되어 변경 시 자동 리로드됩니다. 검증 실패 시 이전 유효 설정이 유지되고 대시보드에 오류가 표시됩니다.

**액션 7종:**

| 타입 | 필수 필드 | 실행 방법 | 비고 |
|---|---|---|---|
| `shell` | `cmd` | `subprocess` exec (셸 경유 없음) | 임의 명령·스크립트 |
| `launch` | `app` | 실행 중이면 KWin 스크립팅으로 창 포커스, 아니면 `gio launch <app>.desktop` | 선택 필드 `class`(KWin 창 클래스 부분일치)·`process`(pgrep -f 패턴), 기본값은 둘 다 `app`. .desktop은 `/usr/share/applications`, `~/.local/share/applications`에서 탐색 |
| `url` | `url` | `xdg-open` | 브라우저/URL 열기 |
| `hotkey` | `keys` | ydotool `key` (evdev 키코드 시퀀스) | 포커스된 창에 키 조합 주입, 예: `[ctrl, shift, v]` |
| `text` | `text` | 클립보드 백업 → `wl-copy` → ydotool Ctrl+V 주입 → 클립보드 복원 | 한글 등 레이아웃 무관 |
| `media` | `op` | `playerctl`(재생 제어) / `wpctl`(볼륨) | op: `play-pause`, `next`, `previous`, `volume-up`, `volume-down`, `mute` |
| `kde` | `component`, `shortcut` | `gdbus call` → `org.kde.kglobalaccel` invokeShortcut | KDE 전역 단축키 직접 호출 (오버뷰, 스크린샷 등) |

## Mac 셋업

1. `brew install --cask hammerspoon`
2. `client/init.lua`를 `~/.hammerspoon/init.lua`로 복사, 파일 상단의 `HOST`/`TOKEN`을 호스트 IP와 `config/mapping.yaml`의 토큰에 맞춰 수정
3. 시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용 → Hammerspoon 허용
4. (F열을 매크로 키로 사용 시) 키보드 설정에서 "F1, F2 등의 키를 표준 기능 키로 사용" ON
5. Hammerspoon 메뉴 → Launch at Login (로그인 시 시작) 켜기

## 사용법

- **⌘⌥⌃M**: 매크로 모드 토글. 메뉴바 아이콘: `⌨` 대기 / `🟢⌨` ON / `⚠️⌨` 연결 끊김
- 매크로 모드 ON이면 전체 키보드가 패드가 되어 macOS로 키가 전달되지 않습니다 (모디파이어 조합 없이 단일 물리 키 = 버튼 1개, Stream Deck 방식). 다시 ⌘⌥⌃M을 누르면 OFF되고 키보드가 즉시 정상 복귀합니다.
- 대시보드: `http://192.168.0.127:8787` (Mac 브라우저에서 접속, 뷰어 전용 — 매핑 편집은 웹에서 불가, `config/mapping.yaml`을 직접 수정)

## 트러블슈팅

- **hotkey/text 액션 무반응** → `systemctl status ydotool`로 데몬 구동 확인, `YDOTOOL_SOCKET=/tmp/.ydotool_socket` 환경 변수가 서버(`macpad.service`)와 수동 테스트 양쪽에 설정되어 있는지 확인
- **Mac에서 키가 안 잡힘** → 손쉬운 사용(Accessibility) 권한이 Hammerspoon에 부여되어 있는지 확인, Secure Input(암호 필드 등) 활성화 중에는 eventtap이 키를 보지 못하는 macOS 한계이므로 정상 동작
- **LAN에서 연결 안 됨** → `firewall-cmd --list-ports`에 `8787/tcp`가 있는지, `client/init.lua`의 `TOKEN`이 `config/mapping.yaml`의 `server.token`과 정확히 일치하는지 확인
- **서비스가 안 뜸** → `systemctl --user status macpad --no-pager`로 로그 확인, `WorkingDirectory`가 실제 저장소 경로(`%h/Documents/macpad`)와 일치하는지 확인
- **매핑 리로드가 반영 안 됨** → 대시보드 상단 상태 바에 `config_error`가 표시되는지 확인 — YAML 문법 오류나 필수 필드 누락 시 이전 설정이 유지됨

## 테스트

```bash
/usr/bin/python3 -m pytest tests/ -v
```

서버 단위 테스트(설정 검증, kVK 변환, 액션 디스패치, WS 인증) 외에 Mac 없이 전체 경로를 검증하는 E2E 스크립트가 있습니다:

```bash
/usr/bin/python3 scripts/fake_client.py F1 --token <config/mapping.yaml의 토큰>
```

### Mac 실기기 체크리스트 (사용자와 함께 진행)

1. Mac에서 Hammerspoon 설치·권한·`init.lua` 배치 → 메뉴바에 `⌨` 표시
2. ⌘⌥⌃M → "MACRO MODE ON" 알림 표시, 대시보드에 "MAC 연결됨" 배지
3. F1 → 호스트에서 Konsole 실행 + 대시보드 F1 타일 발광
4. F4 → 포커스된 창에 "안녕하세요." 입력 + 기존 클립보드 내용 복원 확인
5. F6 길게 누름 → 볼륨이 auto-repeat로 연속 증가
6. 매크로 모드 중 A 등 미매핑 키 입력 → Mac 앱에는 입력 안 됨(키 삼킴 확인) + 대시보드에 unmapped 표시
7. 호스트 서버 중지 → Mac 메뉴바 `⚠️` 표시 + 매크로 모드 자동 OFF + 키보드 정상 복귀 확인, 서버 재시작 → 2초 백오프 후 자동 재연결
8. ⌘⌥⌃M → OFF, 이후 키보드가 macOS에 정상적으로 전달되는지 확인
9. 매크로 모드 ON 상태에서 암호 입력 필드(Secure Input) 포커스 → eventtap이 키를 보지 못해 캡처가 중단되는 것을 확인 (macOS Secure Input 한계로 수용된 동작 — 서버/대시보드에는 영향 없어야 함)
10. 토글 단축키(⌘⌥⌃M)를 길게 눌러 auto-repeat 이벤트를 유발 → 모드가 여러 번 깜빡이지 않고 최초 1회만 토글되는지 확인 (`keyboardEventAutorepeat` 필터링)

이 항목들은 실제 MacBook + Fedora 호스트가 모두 준비된 상태에서만 실행 가능하며, 이 저장소의 자동화 테스트로는 커버되지 않습니다.
