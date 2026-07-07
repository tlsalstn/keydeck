-- MacPad client: 키 캡처+전송만. 매핑 해석·실행은 전부 서버(mapping.yaml)가 한다.
-- 설치: ~/.hammerspoon/init.lua 로 복사(또는 require), HOST/TOKEN 수정.

local HOST = "192.168.0.127"
local PORT = 8787
local TOKEN = "CHANGE-ME-to-a-long-random-string"
local TOGGLE_MODS = { "cmd", "alt", "ctrl" }  -- 토글 단축키 ⌘⌥⌃M
local TOGGLE_KEY = "m"

local macroMode = false
local connected = false
local ws = nil
local menubar = hs.menubar.new()
local swallowToggleUp = false
local reconnectTimer = nil

local function updateMenubar()
  if not connected then
    menubar:setTitle("⚠️⌨")
    menubar:setTooltip("MacPad: 서버 연결 끊김")
  elseif macroMode then
    menubar:setTitle("🟢⌨")
    menubar:setTooltip("MacPad: MACRO MODE ON (⌘⌥⌃M로 해제)")
  else
    menubar:setTitle("⌨")
    menubar:setTooltip("MacPad: 대기 (⌘⌥⌃M로 켜기)")
  end
end

local function setMode(on)
  -- 페일세이프: 연결 없으면 켤 수 없다 — 키보드가 먹통이 되는 상황 방지
  macroMode = on and connected
  hs.alert.closeAll()
  hs.alert.show(macroMode and "MACRO MODE ON" or "MACRO MODE OFF", 1)
  updateMenubar()
end

local function connect()
  local url = string.format("ws://%s:%d/ws/client?token=%s", HOST, PORT, TOKEN)
  ws = hs.websocket.new(url, function(event, message)
    if event == "open" then
      connected = true
      -- 두 번째 인자 false = text 프레임 (기본은 binary — 서버 프로토콜은 text)
      ws:send(hs.json.encode({ type = "hello", client = "hammerspoon", version = 1 }), false)
      updateMenubar()
    elseif event == "closed" or event == "fail" then
      if connected or macroMode then
        connected = false
        if macroMode then setMode(false) end  -- 페일오픈: 끊기면 모드 자동 OFF
        updateMenubar()
      end
      if reconnectTimer then reconnectTimer:stop() end
      reconnectTimer = hs.timer.doAfter(2, connect)
    end
    -- "received": mapping_updated 등 — v1 클라이언트는 매핑을 안 쓰므로 무시
  end)
end

local types = hs.eventtap.event.types
local props = hs.eventtap.event.properties
local toggleKeyCode = hs.keycodes.map[TOGGLE_KEY]

local tap = hs.eventtap.new({ types.keyDown, types.keyUp }, function(e)
  -- 토글 단축키는 모드와 무관하게 항상 여기서 먼저 처리 (탈출로 보장)
  if e:getType() == types.keyDown
      and e:getKeyCode() == toggleKeyCode
      and e:getFlags():containExactly(TOGGLE_MODS) then
    if e:getProperty(props.keyboardEventAutorepeat) ~= 0 then
      return true  -- 오토리피트로 인한 토글 플래핑 방지
    end
    swallowToggleUp = true
    setMode(not macroMode)
    return true
  end
  -- 토글 키의 key-up은 서버로도 macOS 앱으로도 새지 않게 삼킨다
  if e:getType() == types.keyUp
      and e:getKeyCode() == toggleKeyCode
      and swallowToggleUp then
    swallowToggleUp = false
    return true
  end
  if not macroMode then return false end
  if not connected then return false end

  local isRepeat = e:getProperty(props.keyboardEventAutorepeat) ~= 0
  ws:send(hs.json.encode({
    type = "key",
    code = e:getKeyCode(),
    event = (e:getType() == types.keyDown) and "down" or "up",
    ["repeat"] = isRepeat,  -- repeat는 Lua 예약어라 대괄호 표기 필수
    shift = e:getFlags().shift == true,  -- Shift+Tab 페이지 역방향 이동용
  }), false)
  return true  -- 이벤트 삼킴 — macOS 앱에 전달되지 않음
end)
tap:start()

-- 워치독: macOS가 eventtap을 조용히 비활성화하는 알려진 문제 대응
local watchdogTimer = hs.timer.doEvery(5, function()
  if not tap:isEnabled() then tap:start() end
end)

-- 앱레벨 ping (연결 유지 + 사멸 감지)
local pingTimer = hs.timer.doEvery(30, function()
  if connected then ws:send(hs.json.encode({ type = "ping" }), false) end
end)

connect()
updateMenubar()
