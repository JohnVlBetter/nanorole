export const CHAT_HTML = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Nanorole Chat</title>
  <style>
    :root {
      --bg: #f4f6f8;
      --panel: #ffffff;
      --soft: #f8fafc;
      --border: #d6dde7;
      --text: #17202a;
      --muted: #657386;
      --accent: #0f766e;
      --accent-soft: #e6f4f1;
      --user-soft: #e8f0ff;
      --error: #b42318;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; background: var(--bg); color: var(--text); }
    button, textarea { font: inherit; }
    button { border: 1px solid var(--border); border-radius: 6px; background: var(--panel); padding: 8px 12px; cursor: pointer; }
    button.primary { background: var(--accent); border-color: var(--accent); color: white; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    .app { min-height: 100vh; display: grid; grid-template-columns: 320px minmax(0, 1fr); }
    aside { display: grid; grid-template-rows: auto auto minmax(0, 1fr) auto; gap: 12px; padding: 18px; background: var(--panel); border-right: 1px solid var(--border); }
    main { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; min-width: 0; }
    header { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 14px 18px; background: var(--panel); border-bottom: 1px solid var(--border); }
    h1 { margin: 0; font-size: 18px; line-height: 24px; }
    a { color: var(--accent); text-decoration: none; font-size: 13px; }
    .status, .session, .meta { color: var(--muted); font-size: 12px; }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .roles { display: grid; align-content: start; gap: 8px; overflow: auto; }
    .role { display: grid; gap: 4px; text-align: left; border: 1px solid var(--border); border-radius: 6px; background: var(--soft); padding: 10px; }
    .role.active { border-color: var(--accent); background: var(--accent-soft); }
    .role strong { font-size: 13px; }
    .detail { border: 1px solid var(--border); border-radius: 6px; background: var(--soft); padding: 10px; color: var(--muted); font-size: 12px; line-height: 18px; white-space: pre-wrap; overflow-wrap: anywhere; }
    .messages { display: grid; align-content: start; gap: 12px; overflow: auto; padding: 18px; }
    .message { max-width: min(820px, 88%); border: 1px solid var(--border); border-radius: 7px; background: var(--panel); padding: 10px 12px; }
    .message.user { justify-self: end; background: var(--user-soft); }
    .message.assistant { justify-self: start; border-left: 4px solid var(--accent); }
    .message.error { justify-self: center; color: var(--error); }
    .message .label { margin-bottom: 4px; color: var(--muted); font-size: 11px; font-weight: 700; text-transform: uppercase; }
    pre { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; line-height: 21px; }
    form { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: end; padding: 14px 18px; background: var(--panel); border-top: 1px solid var(--border); }
    textarea { min-height: 52px; max-height: 180px; resize: vertical; border: 1px solid var(--border); border-radius: 7px; background: var(--soft); padding: 10px 12px; line-height: 20px; }
    .empty { align-self: center; justify-self: center; max-width: 520px; border: 1px dashed var(--border); border-radius: 7px; background: var(--panel); color: var(--muted); padding: 22px; line-height: 22px; }
    @media (max-width: 860px) { .app { grid-template-columns: 1fr; } aside { border-right: 0; border-bottom: 1px solid var(--border); } form { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <div><h1>Nanorole Chat</h1><div class="status" id="role-status">正在读取角色</div></div>
      <div class="actions"><button class="primary" id="start" disabled>开始会话</button><button id="reset" disabled>重开</button></div>
      <div class="roles" id="roles"></div>
      <div class="detail" id="role-detail">选择一个角色后开始网页对话。</div>
    </aside>
    <main>
      <header>
        <div><h1 id="heading">未开始</h1><div class="session" id="session">选择角色并开始会话</div></div>
        <a href="/logs" target="_blank" rel="noreferrer">打开日志</a>
      </header>
      <section class="messages" id="messages"><div class="empty">网页 demo 由 TS 服务提供，Python 只负责 core runtime。</div></section>
      <form id="composer"><textarea id="input" placeholder="输入消息，Enter 发送，Shift+Enter 换行"></textarea><button class="primary" id="send" disabled>发送</button></form>
    </main>
  </div>
  <script>
    const rolesEl = document.querySelector("#roles");
    const roleStatus = document.querySelector("#role-status");
    const roleDetail = document.querySelector("#role-detail");
    const startButton = document.querySelector("#start");
    const resetButton = document.querySelector("#reset");
    const heading = document.querySelector("#heading");
    const sessionLine = document.querySelector("#session");
    const messagesEl = document.querySelector("#messages");
    const composer = document.querySelector("#composer");
    const input = document.querySelector("#input");
    const send = document.querySelector("#send");
    let roles = [];
    let selectedRole = null;
    let sessionId = null;
    let starting = false;
    let streaming = false;
    function setComposer(enabled) { input.readOnly = !enabled; send.disabled = !enabled; }
    function scroll() { messagesEl.scrollTop = messagesEl.scrollHeight; }
    function addMessage(role, text, kind = role) {
      const item = document.createElement("article");
      item.className = "message " + kind;
      item.innerHTML = '<div class="label"></div><pre></pre>';
      item.querySelector(".label").textContent = role;
      item.querySelector("pre").textContent = text;
      messagesEl.append(item);
      scroll();
      return item.querySelector("pre");
    }
    function renderRoles() {
      rolesEl.replaceChildren();
      for (const role of roles) {
        const button = document.createElement("button");
        button.className = "role" + (selectedRole && selectedRole.id === role.id ? " active" : "");
        button.innerHTML = "<strong></strong><span class='meta'></span>";
        button.querySelector("strong").textContent = role.name || role.id;
        button.querySelector(".meta").textContent = role.id + " · " + (role.version || "-");
        button.onclick = async () => {
          selectedRole = role;
          roleDetail.textContent = ((role.persona || "") + "\\n\\n" + (role.opening || "")).trim();
          startButton.disabled = false;
          renderRoles();
          await startSession();
        };
        rolesEl.append(button);
      }
    }
    async function loadRoles() {
      try {
        const response = await fetch("/api/roles", { cache: "no-store" });
        const data = await response.json();
        roles = Array.isArray(data.roles) ? data.roles : [];
        selectedRole = roles[0] || null;
        roleStatus.textContent = roles.length + " 个角色";
        if (selectedRole) roleDetail.textContent = ((selectedRole.persona || "") + "\\n\\n" + (selectedRole.opening || "")).trim();
        startButton.disabled = !selectedRole;
        renderRoles();
        if (selectedRole) await startSession();
      } catch (error) {
        roleStatus.textContent = "角色读取失败";
        roleDetail.textContent = String(error);
      }
    }
    async function startSession() {
      if (!selectedRole || starting || streaming) return;
      starting = true;
      sessionId = null;
      startButton.disabled = true;
      resetButton.disabled = true;
      setComposer(false);
      try {
        const response = await fetch("/api/sessions", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role_id: selectedRole.id }) });
        if (!response.ok) { addMessage("error", await response.text(), "error"); return; }
        const data = await response.json();
        sessionId = data.sessionId;
        heading.textContent = data.roleName || selectedRole.name || selectedRole.id;
        sessionLine.textContent = "session " + sessionId;
        messagesEl.replaceChildren();
        addMessage("assistant", data.opening || selectedRole.opening || "会话已开始", "assistant");
        resetButton.disabled = false;
        setComposer(true);
        input.focus();
      } catch (error) {
        addMessage("error", String(error), "error");
      } finally {
        starting = false;
        startButton.disabled = !selectedRole;
        resetButton.disabled = !sessionId;
        if (!sessionId) setComposer(false);
      }
    }
    function parseSse(buffer) {
      const events = [];
      const parts = buffer.split("\\n\\n");
      const rest = parts.pop() || "";
      for (const part of parts) {
        let event = "message";
        const data = [];
        for (const line of part.split("\\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
        }
        if (data.length) events.push({ event, data: JSON.parse(data.join("\\n")) });
      }
      return { events, rest };
    }
    async function sendMessage(text) {
      if (!sessionId || streaming) return;
      streaming = true;
      setComposer(false);
      addMessage("user", text, "user");
      const assistant = addMessage("assistant", "", "assistant");
      let buffer = "";
      try {
        const response = await fetch("/api/sessions/" + encodeURIComponent(sessionId) + "/messages:stream", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ message: text }) });
        if (!response.ok || !response.body) throw new Error(await response.text());
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        while (true) {
          const read = await reader.read();
          if (read.done) break;
          const parsed = parseSse(buffer + decoder.decode(read.value, { stream: true }));
          buffer = parsed.rest;
          for (const item of parsed.events) {
            if (item.event === "token") assistant.textContent += item.data.delta || "";
            if (item.event === "final") assistant.textContent = item.data.message || assistant.textContent;
            if (item.event === "error") throw new Error(item.data.message || "runtime error");
          }
          scroll();
        }
      } catch (error) {
        assistant.parentElement.remove();
        addMessage("error", String(error), "error");
      } finally {
        streaming = false;
        setComposer(Boolean(sessionId));
        input.focus();
      }
    }
    startButton.onclick = startSession;
    resetButton.onclick = startSession;
    composer.onsubmit = (event) => { event.preventDefault(); const text = input.value.trim(); if (!text) return; input.value = ""; sendMessage(text); };
    input.onkeydown = (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); composer.requestSubmit(); } };
    loadRoles();
  </script>
</body>
</html>`;

export const LOGS_HTML = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Nanorole Logs</title>
  <style>
    :root { --bg: #f4f6f8; --panel: #fff; --soft: #f8fafc; --border: #d6dde7; --text: #17202a; --muted: #657386; --accent: #0f766e; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); }
    header { position: sticky; top: 0; display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 14px 20px; background: var(--panel); border-bottom: 1px solid var(--border); }
    h1 { margin: 0; font-size: 18px; }
    main { max-width: 1180px; margin: 0 auto; padding: 18px 20px 32px; display: grid; gap: 10px; }
    button { border: 1px solid var(--border); border-radius: 6px; background: var(--panel); padding: 8px 12px; cursor: pointer; }
    a { color: var(--accent); text-decoration: none; font-size: 13px; }
    .status { color: var(--muted); font-size: 13px; }
    details { border: 1px solid var(--border); border-left: 4px solid var(--accent); border-radius: 6px; background: var(--panel); overflow: hidden; }
    summary { cursor: pointer; display: grid; grid-template-columns: 180px 180px minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 11px 14px; }
    .pill { color: var(--accent); font-weight: 700; font-size: 12px; }
    .muted { color: var(--muted); font-size: 12px; }
    .body { display: grid; gap: 10px; padding: 12px 14px 14px; border-top: 1px solid var(--border); background: var(--soft); }
    .io { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }
    .box { border: 1px solid var(--border); border-radius: 6px; background: var(--panel); padding: 10px; min-width: 0; }
    .box h2 { margin: 0 0 8px; font-size: 12px; }
    pre { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; font-family: Consolas, monospace; font-size: 12px; line-height: 18px; }
    .raw { background: #0f172a; color: #e5edf7; }
    @media (max-width: 760px) { summary { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <div><h1>Nanorole Logs</h1><div class="status" id="status">未加载</div></div>
    <div><a href="/chat">返回聊天</a> <button id="refresh">刷新</button></div>
  </header>
  <main id="app"></main>
  <script>
    const app = document.querySelector("#app");
    const status = document.querySelector("#status");
    function text(value) { return value === undefined || value === null || value === "" ? "-" : String(value); }
    function section(title, value) {
      if (value === undefined || value === null || value === "" || (Array.isArray(value) && !value.length)) return "";
      return '<div class="box"><h2>' + title + '</h2><pre>' + escapeHtml(typeof value === "string" ? value : JSON.stringify(value, null, 2)) + '</pre></div>';
    }
    function escapeHtml(value) { return String(value).replace(/[&<>]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[char])); }
    function render(logs) {
      app.innerHTML = "";
      status.textContent = logs.length + " 条日志，上次更新 " + new Date().toLocaleTimeString("zh-CN", { hour12: false });
      for (const entry of logs.slice().reverse()) {
        const detail = document.createElement("details");
        const output = entry.output || {};
        const input = entry.input || {};
        detail.innerHTML =
      '<summary><span class="muted">' + escapeHtml(text(entry.ts)) + '</span><span class="pill">' + escapeHtml(text(entry.type)) + '</span><span>' + escapeHtml(text(entry.error || output.message || entry.raw || entry.session_id)) + '</span><span class="muted">' + escapeHtml(text(entry.duration_ms ? entry.duration_ms + " ms" : "")) + '</span><span class="muted">' + escapeHtml(text(entry.first_chunk_latency_ms ? entry.first_chunk_latency_ms + " ms" : "")) + '</span><span class="muted">' + escapeHtml(text(entry.first_token_latency_ms ? entry.first_token_latency_ms + " ms" : "")) + '</span></summary>' +
          '<div class="body"><div class="io">' +
          section("用户输入", input.user_message) +
          section("LLM 输入", input.messages || entry.messages) +
          section("LLM 输出", output.message) +
          '</div><div class="box raw"><h2>原始 JSON</h2><pre>' + escapeHtml(JSON.stringify(entry, null, 2)) + '</pre></div></div>';
        app.append(detail);
      }
    }
    async function load() {
      const response = await fetch("/api/logs", { cache: "no-store" });
      const data = await response.json();
      render(Array.isArray(data.logs) ? data.logs : []);
    }
    document.querySelector("#refresh").onclick = load;
    load().catch((error) => { status.textContent = "读取失败"; app.textContent = String(error); });
  </script>
</body>
</html>`;
