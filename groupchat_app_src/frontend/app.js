const $ = (id) => document.getElementById(id);

const authPanel = $("auth");
const chatPanel = $("chat");
const messagesDiv = $("messages");
const usernameInput = $("username");
const passwordInput = $("password");
const authMsg = $("authMsg");

const signupBtn = $("signupBtn");
const loginBtn = $("loginBtn");
const logoutBtn = $("logoutBtn");
const chatInput = $("chatInput");
const sendBtn = $("sendBtn");

const API = location.origin + "/api";
let token = localStorage.getItem("token") || "";
let ws;
let reconnectTimer;
const displayedMessageIds = new Set();
let waitingAfterMessageId = null;

function showAuth() {
  authPanel.classList.remove("hidden");
  chatPanel.classList.add("hidden");
}

function showChat() {
  authPanel.classList.add("hidden");
  chatPanel.classList.remove("hidden");
}

async function callAPI(path, method = "GET", body) {
  const headers = {"Content-Type": "application/json"};
  if (token) headers["Authorization"] = "Bearer " + token;
  const res = await fetch(API + path, {
    method, headers, body: body ? JSON.stringify(body) : undefined
  });
  if (!res.ok) throw new Error((await res.json()).detail || ("HTTP "+res.status));
  return res.json();
}

function addMessage(m) {
  if (displayedMessageIds.has(m.id)) return;
  displayedMessageIds.add(m.id);
  const el = document.createElement("div");
  el.className = "message" + (m.is_bot ? " bot" : "");
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = `${m.username || "unknown"} • ${new Date(m.created_at).toLocaleString("en-US")}`;
  const body = document.createElement("div");
  body.textContent = m.content;
  el.appendChild(meta);
  el.appendChild(body);
  messagesDiv.appendChild(el);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
  if (m.is_bot && waitingAfterMessageId !== null && m.id > waitingAfterMessageId) {
    waitingAfterMessageId = null;
    $("chatMsg").textContent = "";
  }
}

async function loadMessages() {
  const data = await callAPI("/messages");
  messagesDiv.innerHTML = "";
  displayedMessageIds.clear();
  for (const m of data.messages) addMessage(m);
}

function connectWS() {
  clearTimeout(reconnectTimer);
  if (!token) return;
  if (ws && ws.readyState < 2) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => ws.send(JSON.stringify({token}));
  ws.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      if (data.type === "message") addMessage(data.message);
      if (data.type === "ready") {
        loadMessages().catch((e) => { $("chatMsg").textContent = e.message; });
      }
      if (data.type === "error") {
        waitingAfterMessageId = null;
        $("chatMsg").textContent = data.detail;
      }
    } catch (e) {}
  };
  ws.onclose = (event) => {
    if (event.code === 1008) {
      token = "";
      localStorage.removeItem("token");
      showAuth();
      authMsg.textContent = "Session expired. Please log in again.";
      return;
    }
    // try to reconnect after a delay
    if (token) reconnectTimer = setTimeout(connectWS, 2000);
  };
}

signupBtn.onclick = async () => {
  try {
    const out = await callAPI("/signup", "POST", {
      username: usernameInput.value.trim(),
      password: passwordInput.value
    });
    token = out.token;
    localStorage.setItem("token", token);
    await loadMessages();
    connectWS();
    showChat();
  } catch (e) {
    authMsg.textContent = e.message;
  }
};

loginBtn.onclick = async () => {
  try {
    const out = await callAPI("/login", "POST", {
      username: usernameInput.value.trim(),
      password: passwordInput.value
    });
    token = out.token;
    localStorage.setItem("token", token);
    await loadMessages();
    connectWS();
    showChat();
  } catch (e) {
    authMsg.textContent = e.message;
  }
};

logoutBtn.onclick = () => {
  token = "";
  localStorage.removeItem("token");
  clearTimeout(reconnectTimer);
  waitingAfterMessageId = null;
  if (ws) ws.close();
  showAuth();
};

sendBtn.onclick = async () => {
  const text = chatInput.value.trim();
  if (!text) return;
  sendBtn.disabled = true;
  const triggersBot = /[?？]/.test(text);
  if (triggersBot) $("chatMsg").textContent = "Sending your question...";
  try {
    const message = await callAPI("/messages", "POST", {content: text});
    addMessage(message);
    if (triggersBot) {
      waitingAfterMessageId = message.id;
      $("chatMsg").textContent = "The model is generating a reply. CPU inference may take about a minute. Please wait...";
    } else if (waitingAfterMessageId === null) {
      $("chatMsg").textContent = "Message sent. Include a question mark (?) to get a bot reply.";
    }
    chatInput.value = "";
  } catch (e) {
    $("chatMsg").textContent = e.message;
  } finally {
    sendBtn.disabled = false;
  }
};

chatInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.isComposing && !sendBtn.disabled) sendBtn.click();
});

if (token) {
  loadMessages().then(()=>{
    connectWS();
    showChat();
  }).catch(()=>showAuth());
} else {
  showAuth();
}
