# keydeck

여분의 노트북 키보드 → KDE Wayland 매크로 덱 (Stream Deck 대체)

클라이언트(macOS 또는 리눅스) 노트북의 키보드를 백그라운드에서 캡처해 네트워크로 전송하고, 호스트(Fedora·Kubuntu 등 KDE Plasma Wayland)가 매핑된 동작 — 앱 실행/포커스, 단축키 주입, 미디어 제어, 텍스트 스니펫, URL, 페이지 전환 — 을 실행합니다. 호스트가 서빙하는 웹 대시보드에서 Stream Deck LCD 스타일로 매핑과 실시간 키 입력을 확인합니다.

## 구조

```
클라이언트 (둘 중 하나)                          호스트 (KDE Plasma Wayland)
┌─────────────────────────────┐               ┌─────────────────────────────────┐
│ macOS: Hammerspoon (Lua)    │               │ Python FastAPI 서버 (:8787)      │
│  · eventtap 캡처, ⌘⌥⌃M 토글  │──WebSocket──▶ │  · 키 이벤트 → 페이지·매핑 조회    │
│─────────────────────────────│  /ws/client   │  · 액션 실행: shell/D-Bus/       │
│ Linux: evdev 클라이언트       │ {key|code,…}  │    ydotool/wl-copy/KWin 포커스   │
│  · grab 캡처, Ctrl+Alt+M 토글 │◀───────────── │  · 웹 대시보드 서빙 + 실시간 push │
└─────────────────────────────┘               └─────────────────────────────────┘
        클라이언트 브라우저 ── HTTP + /ws/dashboard ──▶ 대시보드 (뷰어 전용)
```

- **매핑의 단일 소스는 호스트의 `config/mapping.yaml`.** 클라이언트에는 매핑 해석·실행 로직이 없습니다 — 키를 보내기만 합니다.
- **보안 불변식**: 네트워크로 오가는 것은 키 식별자(물리 키 이름 또는 macOS kVK 코드)뿐. 무엇을 실행할지는 전부 호스트 로컬 설정에서만 정해집니다. `/ws/client`는 공유 토큰 인증.
- 매크로 모드 ON이면 클라이언트 키보드 전체가 패드가 되어 로컬 OS에 키가 전달되지 않고, OFF·연결 끊김·크래시 시 즉시 정상 키보드로 복귀합니다(페일오픈).

## 지원 플랫폼

| 역할 | 지원 | 비고 |
|---|---|---|
| 호스트 | Fedora, Kubuntu 등 **KDE Plasma Wayland** | 창 포커스·`kde` 액션이 KWin/kglobalaccel 기반. GNOME 미지원 |
| 클라이언트 | macOS (Hammerspoon), 리눅스 (evdev — 데스크톱 환경 무관) | |

## 의존성 설치 (공식 패키지만)

| 역할 | Fedora (dnf) | Kubuntu (apt) |
|---|---|---|
| 호스트 서버 | `python3-fastapi python3-uvicorn python3-websockets python3-pyyaml playerctl ydotool` | `python3-fastapi python3-uvicorn python3-websockets python3-yaml playerctl ydotool` |
| 호스트 개발(테스트) | `python3-pytest python3-httpx` | `python3-pytest python3-httpx` |
| 리눅스 클라이언트 | `python3-evdev python3-websockets libnotify` | `python3-evdev python3-websockets libnotify` |

- 패키지명 차이: PyYAML이 Fedora는 `python3-pyyaml`, Kubuntu는 `python3-yaml`.
- 오디오 볼륨 액션은 **PipeWire(`wpctl`)와 PulseAudio(`pactl`)를 자동 감지**합니다. 재생 제어는 `playerctl`(MPRIS)로 백엔드 무관.
- pip/venv를 사용하지 않습니다. 실행은 항상 `/usr/bin/python3` 절대 경로.

## 호스트 셋업

### 1. ydotool, 방화벽

`hotkey`/`text` 액션은 uinput 가상 키보드(ydotool)로 키를 주입합니다:

```bash
sudo systemctl enable --now ydotool
YDOTOOL_SOCKET=/tmp/.ydotool_socket ydotool key 29:1 29:0 && echo "ydotool ok"
```

소켓이 `root:root`라 Permission denied가 나면 데몬을 사용자 소유 소켓으로 override 합니다:

```bash
sudo mkdir -p /etc/systemd/system/ydotool.service.d
printf '[Service]\nExecStart=\nExecStart=/usr/bin/ydotoold --socket-own=%s:%s\n' "$(id -u)" "$(id -g)" \
  | sudo tee /etc/systemd/system/ydotool.service.d/override.conf
sudo systemctl daemon-reload && sudo systemctl restart ydotool
```

방화벽에서 8787/tcp를 엽니다 (firewalld 기준):

```bash
sudo firewall-cmd --add-port=8787/tcp --permanent && sudo firewall-cmd --reload
```

### 2. 설정 파일과 서비스 등록

`cp config/mapping.example.yaml config/mapping.yaml` 후 토큰을 생성해 기입합니다(클라이언트의 `TOKEN`과 반드시 동일). `config/mapping.yaml`은 실제 토큰을 담으므로 git에 추적되지 않습니다(`.gitignore`).

```bash
/usr/bin/python3 -c "import secrets; print(secrets.token_urlsafe(32))"  # → config/mapping.yaml의 token에 기입

mkdir -p ~/.config/systemd/user
cp systemd/macpad.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now macpad
curl -s http://<host-ip>:8787/api/mapping | head -c 80   # LAN 접근 확인
```

### 3. `config/mapping.yaml` 편집

```yaml
server:
  port: 8787
  token: "<공유 토큰>"

pages:
  default:
    F1: { label: "터미널", icon: "🖥️", action: { type: launch, app: org.kde.konsole } }
    F2: { label: "알림 테스트", icon: "🔔", action: { type: shell, cmd: "notify-send keydeck 눌림" } }
    F3: { label: "붙여넣기", icon: "📋", action: { type: hotkey, keys: [ctrl, shift, v] } }
    F4: { label: "인사말", icon: "✉️", action: { type: text, text: "안녕하세요." } }
    F5: { label: "재생/정지", icon: "⏯️", action: { type: media, op: play-pause } }
    F6: { label: "볼륨 +", icon: "🔊", action: { type: media, op: volume-up }, repeat: true }
    F7: { label: "오버뷰", icon: "🗂️", action: { type: kde, component: kwin, shortcut: Overview } }
    F8: { label: "문서", icon: "🌐", action: { type: url, url: "https://kde.org" } }
  gitlab:
    E: { label: "메인으로", icon: "🏠", action: { type: page, to: default } }
```

- `label`(필수): 대시보드 표시 이름. `icon`(선택): emoji — `launch` 앱은 호스트 아이콘 테마의 **실제 앱 아이콘**이 자동 표시되고 emoji는 폴백.
- `repeat: true`: 키를 누르고 있을 때 auto-repeat에도 재실행 (볼륨 등).
- 키 이름은 물리 키 이름(`F1`…`F12`, `A`…`Z`, `Digit1`…, `Grave`, `Comma`, `Space` 등 — `server/keycodes.py`의 이름 공간).
- 파일은 2초 폴링으로 자동 리로드. 검증 실패 시 이전 유효 설정 유지 + 대시보드에 오류 표시.
- `server.port`는 참고용이며 실제 리스닝 포트는 systemd 유닛의 `--port 8787`이 결정.

**페이지 내비게이션 (내장):** 여러 페이지를 정의하면 매핑에 없는 키로 페이지를 이동합니다 — `Tab` 다음, `Shift+Tab` 이전, `F1`~`F12` 직접 선택(정의 순서). **매핑된 키가 항상 우선**이며, 특정 키에 페이지 이동을 명시하려면 `page` 액션을 씁니다.

**액션 8종:**

| 타입 | 필수 필드 | 실행 방법 | 비고 |
|---|---|---|---|
| `shell` | `cmd` | `subprocess` exec (셸 경유 없음) | 임의 명령·스크립트 |
| `launch` | `app` | 실행 중이면 KWin 스크립팅으로 창 포커스, 아니면 `gio launch <app>.desktop` | 선택 `class`(창 클래스 부분일치)·`process`(pgrep -f 패턴), 기본값 둘 다 `app` |
| `url` | `url` | `xdg-open` (기본), `browser` 지정 시 해당 브라우저로 | 선택 `browser`·`class`(열고 나서 그 창 포커스) |
| `hotkey` | `keys` | ydotool `key` (evdev 시퀀스) | 포커스된 창에 키 조합 주입, 예: `[ctrl, shift, v]` |
| `text` | `text` | 클립보드 백업 → `wl-copy` → Ctrl+V 주입 → 복원 | 한글 등 레이아웃 무관 |
| `media` | `op` | `playerctl`(재생) / `wpctl`·`pactl`(볼륨, 자동 감지) | op: `play-pause` `next` `previous` `volume-up` `volume-down` `mute` |
| `kde` | `component`, `shortcut` | `gdbus` → `org.kde.kglobalaccel` invokeShortcut | KDE 전역 단축키 직접 호출 |
| `page` | `to` | 서버 내부 페이지 전환 | `to`는 존재하는 페이지명 (설정 검증) |

## 클라이언트 셋업 — macOS

1. `brew install --cask hammerspoon`
2. `client/init.lua`를 `~/.hammerspoon/init.lua`로 복사, 상단 `HOST`/`TOKEN` 수정
3. 시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용 → Hammerspoon 허용
4. (F열 사용 시) 키보드 설정 "F1, F2 등의 키를 표준 기능 키로 사용" ON
5. Hammerspoon 메뉴 → Launch at Login

**토글: ⌘⌥⌃M.** 메뉴바 아이콘: `⌨` 대기 / `🟢⌨` ON / `⚠️⌨` 연결 끊김.

## 클라이언트 셋업 — 리눅스 (Kubuntu 등)

데스크톱 환경 무관(evdev 커널 레벨 캡처). Wayland/X11 모두 동작.

1. 의존성 설치 (위 표 참조)
2. 사용자를 `input` 그룹에 추가(최초 1회): `sudo usermod -aG input $USER` 후 재로그인
3. 리포를 `~/Documents/macpad`에 클론
4. systemd user 서비스 등록:
   ```bash
   mkdir -p ~/.config/systemd/user
   cp systemd/keydeck-client.service ~/.config/systemd/user/
   # 유닛 파일의 KEYDECK_HOST / KEYDECK_TOKEN 을 실제 값으로 편집
   systemctl --user daemon-reload && systemctl --user enable --now keydeck-client
   ```

**토글: Ctrl+Alt+M.** 상태는 `notify-send` 알림과 대시보드 배지로 표시됩니다. ON이면 모든 키보드 장치를 grab하여 로컬 세션에 키가 전달되지 않고, OFF·서버 연결 끊김·프로세스 종료 시 즉시 ungrab됩니다 (크래시 시에도 커널이 grab을 자동 해제 — 키보드가 먹통이 될 수 없는 구조).

## 사용법

- 매크로 모드 ON → 클라이언트 키보드 전체가 패드 (단일 물리 키 = 버튼 1개, Stream Deck 방식)
- 대시보드: `http://<host-ip>:8787` — 키 그리드에 실제 앱 아이콘·라벨·물리 키 배지 표시, 키 누름 실시간 발광, 성공/실패 글로우, 페이지 배지, 클라이언트 연결 상태. 뷰어 전용(매핑 편집은 `config/mapping.yaml` 직접 수정)

## 트러블슈팅

- **hotkey/text 무반응** → `systemctl status ydotool`, 소켓 권한(위 override), `YDOTOOL_SOCKET=/tmp/.ydotool_socket` 확인
- **볼륨 액션 실패** → `wpctl`(PipeWire) 또는 `pactl`(PulseAudio) 중 하나가 설치되어 있어야 함. 서버 시작 시 감지하므로 설치 후 서비스 재시작
- **macOS에서 키가 안 잡힘** → 손쉬운 사용 권한 확인. Secure Input(암호 필드) 중 캡처 중단은 macOS 한계로 정상
- **리눅스 클라이언트가 장치를 못 찾음** → `input` 그룹 소속 확인(`groups`), 재로그인 필요
- **연결 안 됨** → 방화벽 8787/tcp, 클라이언트 `TOKEN` = `config/mapping.yaml`의 `server.token` 일치 확인. 서버 로그(`journalctl --user -u macpad`)에 403이 찍히면 토큰 불일치
- **매핑 리로드가 반영 안 됨** → 대시보드에 `config_error` 토스트 확인 — YAML 오류 시 이전 설정 유지
- **창 포커스가 안 됨** → 호스트가 KDE Plasma(KWin)인지 확인. GNOME은 미지원

## 테스트

```bash
/usr/bin/python3 -m pytest tests/ -v
```

클라이언트 실기기 없이 전체 경로를 검증하는 E2E 스크립트:

```bash
/usr/bin/python3 scripts/fake_client.py F1 --token <config/mapping.yaml의 토큰>
```

### 실기기 체크리스트

**macOS 클라이언트**: ⌘⌥⌃M 토글·메뉴바 상태, 매핑 키 실행, 미매핑 키 삼킴, 서버 중지 시 자동 OFF·키보드 복귀·재연결, Secure Input 경계, 토글 longpress 플래핑 없음.

**리눅스 클라이언트 (Kubuntu)**: 서비스 시작 → "서버 연결됨" 알림, Ctrl+Alt+M 토글·알림, 매크로 모드 중 로컬 세션에 키 미전달(grab), 서버 중지 → 알림 + 즉시 키보드 복귀(ungrab) + 재연결, 프로세스 kill → 커널 grab 자동 해제.

**호스트를 Kubuntu로 운영 시**: 볼륨(pactl 경로), 창 포커스(KWin), `kde` 액션 동작 확인.
