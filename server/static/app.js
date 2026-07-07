// MacBook 물리 배열. 이름은 서버 keycodes.py의 KVK_TO_NAME 값과 일치해야 한다.
const ROWS = [
  ["Escape","F1","F2","F3","F4","F5","F6","F7","F8","F9","F10","F11","F12"],
  ["Grave","Digit1","Digit2","Digit3","Digit4","Digit5","Digit6","Digit7","Digit8","Digit9","Digit0","Minus","Equal","Backspace"],
  ["Tab","Q","W","E","R","T","Y","U","I","O","P","LeftBracket","RightBracket","Backslash"],
  ["CapsLock","A","S","D","F","G","H","J","K","L","Semicolon","Quote","Return"],
  ["LShift","Z","X","C","V","B","N","M","Comma","Period","Slash","RShift"],
  ["Fn","LCtrl","LOpt","LCmd","Space","RCmd","ROpt","Left","Up","Down","Right"],
];
// v1에서 매핑 불가한 자리 (모디파이어 — flagsChanged 이벤트라 캡처 안 됨)
const DEAD = new Set(["CapsLock","LShift","RShift","Fn","LCtrl","LOpt","LCmd","RCmd","ROpt"]);
const FLEX = { Backspace:1.6, Tab:1.6, CapsLock:1.8, Return:1.9, LShift:2.3, RShift:2.3, Space:5.2, Backslash:1.2 };
const KEYCAP = {
  Escape:"esc", Grave:"`", Minus:"-", Equal:"=", Backspace:"⌫", Tab:"⇥",
  LeftBracket:"[", RightBracket:"]", Backslash:"\\", CapsLock:"caps",
  Semicolon:";", Quote:"'", Return:"⏎", LShift:"⇧", RShift:"⇧",
  Comma:",", Period:".", Slash:"/", Fn:"fn", LCtrl:"⌃", LOpt:"⌥",
  LCmd:"⌘", RCmd:"⌘", ROpt:"⌥", Space:"", Left:"◀", Right:"▶", Up:"▲", Down:"▼",
};

let mapping = { active_page: "default", pages: {} };
const tiles = {};

function buildDeck() {
  const deck = document.getElementById("deck");
  for (const row of ROWS) {
    const r = document.createElement("div");
    r.className = "row";
    for (const key of row) {
      const t = document.createElement("div");
      t.className = "tile";
      if (FLEX[key]) t.style.flexGrow = FLEX[key];
      r.appendChild(t);
      tiles[key] = t;
    }
    deck.appendChild(r);
  }
}

function paint() {
  const page = mapping.pages[mapping.active_page] || {};
  const pageNames = Object.keys(mapping.pages);
  document.getElementById("page-name").textContent = mapping.active_page;
  for (const [key, t] of Object.entries(tiles)) {
    const b = page[key];
    t.classList.toggle("dead", DEAD.has(key));
    t.classList.toggle("mapped", !!b);
    t.classList.remove("nav", "nav-active");
    t.innerHTML = "";
    const icon = document.createElement("div");
    icon.className = "icon";
    const label = document.createElement("div");
    label.className = "label";
    if (b) {
      if (b.icon_url) {
        const img = document.createElement("img");
        img.src = b.icon_url;
        img.alt = "";
        img.onerror = () => { img.remove(); icon.textContent = b.icon || ""; };
        icon.append(img);
      } else {
        icon.textContent = b.icon || "";
      }
      label.textContent = b.label;
      t.title = `${key} — ${b.label} (${b.type})`;
    } else if (key === "Tab" && pageNames.length > 1) {
      // 미매핑 Tab/F키는 내장 페이지 내비게이션 (매핑이 항상 우선)
      t.classList.add("nav");
      icon.textContent = "⇆";
      label.textContent = "페이지";
      t.title = "Tab: 다음 페이지 / Shift+Tab: 이전 페이지";
    } else if (/^F([1-9]|1[0-2])$/.test(key) && parseInt(key.slice(1)) <= pageNames.length) {
      const name = pageNames[parseInt(key.slice(1)) - 1];
      t.classList.add("nav");
      if (name === mapping.active_page) t.classList.add("nav-active");
      icon.textContent = "📄";
      label.textContent = name;
      t.title = `${key} — ${name} 페이지로 이동`;
    } else {
      label.textContent = KEYCAP[key] !== undefined ? KEYCAP[key]
        : key.startsWith("Digit") ? key.slice(5) : key;
      t.title = key;
    }
    t.append(icon, label);
  }
}

let toastTimer;
function toast(text, ok = false) {
  const el = document.getElementById("toast");
  el.textContent = text;
  el.className = ok ? "show ok" : "show";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = ""; }, 4000);
}

async function loadMapping() {
  mapping = await (await fetch("/api/mapping")).json();
  paint();
}

function handle(msg) {
  if (msg.type === "key") {
    const t = tiles[msg.key];
    if (t) t.classList.toggle("pressed", msg.event === "down");
  } else if (msg.type === "action_result") {
    const t = tiles[msg.key];
    if (t) {
      t.classList.remove("ok", "fail");
      void t.offsetWidth; // 애니메이션 재시작
      t.classList.add(msg.ok ? "ok" : "fail");
    }
    if (!msg.ok) toast(`${msg.label}: ${msg.error}`);
  } else if (msg.type === "client_status") {
    const b = document.getElementById("client-badge");
    b.className = "badge " + (msg.connected ? "on" : "off");
    b.textContent = msg.connected ? "MAC 연결됨" : "MAC 연결 끊김";
  } else if (msg.type === "page_changed") {
    mapping.active_page = msg.page;
    paint();
  } else if (msg.type === "mapping_updated") {
    loadMapping();
    toast("매핑 리로드됨", true);
  } else if (msg.type === "config_error") {
    toast("설정 오류: " + msg.message);
  }
}

function connectWS() {
  const ws = new WebSocket(`ws://${location.host}/ws/dashboard`);
  ws.onopen = loadMapping;
  ws.onmessage = (ev) => handle(JSON.parse(ev.data));
  ws.onclose = () => setTimeout(connectWS, 2000);
}

buildDeck();
loadMapping();
connectWS();
