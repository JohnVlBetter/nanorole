export const CHAT_HTML = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Nanorole Studio</title>
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
    aside { display: grid; grid-template-rows: auto auto minmax(110px, .6fr) minmax(110px, .6fr) minmax(150px, 1fr) auto; gap: 12px; padding: 18px; background: var(--panel); border-right: 1px solid var(--border); }
    main { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; min-width: 0; }
    header { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 14px 18px; background: var(--panel); border-bottom: 1px solid var(--border); }
    h1 { margin: 0; font-size: 18px; line-height: 24px; }
    a { color: var(--accent); text-decoration: none; font-size: 13px; }
    .status, .session, .meta { color: var(--muted); font-size: 12px; }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .roles, .scenarios, .sessions { display: grid; align-content: start; gap: 8px; overflow: auto; }
    .role, .scenario-card, .session-card { display: grid; gap: 4px; text-align: left; border: 1px solid var(--border); border-radius: 6px; background: var(--soft); padding: 10px; }
    .role.active, .scenario-card.active, .session-card.active { border-color: var(--accent); background: var(--accent-soft); }
    .role strong, .scenario-card strong, .session-card strong { font-size: 13px; }
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
      <div><h1>Nanorole Studio</h1><div class="status" id="role-status">正在读取角色</div></div>
      <div class="actions"><button class="primary" id="start" disabled>开始会话</button><button id="reset" disabled>重开</button></div>
      <div class="roles" id="roles"></div>
      <div class="scenarios" id="scenarios"></div>
      <div class="sessions" id="sessions"></div>
      <div class="detail" id="story-detail">选择一个角色或场景后开始网页对话。</div>
      <div class="detail" id="world-detail">World context will appear here.</div>
      <div class="detail" id="relationship-detail">Relationship state will appear here.</div>
      <div class="detail" id="memory-detail">Memory selections will appear here.</div>
      <div class="detail" id="context-detail">Context preview is available after session creation.</div>
    </aside>
    <main>
      <header>
        <div><h1 id="heading">未开始</h1><div class="session" id="session">选择角色并开始会话</div></div>
        <div class="actions"><a id="memory-link" href="/memories" target="_blank" rel="noreferrer">记忆</a><a id="context-link" href="/memories" target="_blank" rel="noreferrer">Context Preview</a><a href="/logs" target="_blank" rel="noreferrer">打开日志</a></div>
      </header>
      <section class="messages" id="messages"><div class="empty">网页 demo 由 TS 服务提供，Python 只负责 core runtime。</div></section>
      <form id="composer"><textarea id="input" placeholder="输入消息，Enter 发送，Shift+Enter 换行"></textarea><button class="primary" id="send" disabled>发送</button></form>
    </main>
  </div>
  <script>
    const rolesEl = document.querySelector("#roles");
    const scenariosEl = document.querySelector("#scenarios");
    const sessionsEl = document.querySelector("#sessions");
    const roleStatus = document.querySelector("#role-status");
    const storyDetail = document.querySelector("#story-detail");
    const worldDetail = document.querySelector("#world-detail");
    const relationshipDetail = document.querySelector("#relationship-detail");
    const memoryDetail = document.querySelector("#memory-detail");
    const contextDetail = document.querySelector("#context-detail");
    const startButton = document.querySelector("#start");
    const resetButton = document.querySelector("#reset");
    const heading = document.querySelector("#heading");
    const sessionLine = document.querySelector("#session");
    const messagesEl = document.querySelector("#messages");
    const composer = document.querySelector("#composer");
    const input = document.querySelector("#input");
    const send = document.querySelector("#send");
    const memoryLink = document.querySelector("#memory-link");
    const contextLink = document.querySelector("#context-link");
    let roles = [];
    let scenarios = [];
    let sessions = [];
    let selectedRole = null;
    let selectedScenario = null;
    let activeSession = null;
    let storyState = null;
    let sessionId = null;
    let starting = false;
    let streaming = false;
    function setComposer(enabled) { input.readOnly = !enabled; send.disabled = !enabled; }
    function scroll() { messagesEl.scrollTop = messagesEl.scrollHeight; }
    function displaySpeaker(speakerId, fallback = "assistant") {
      if (!speakerId) return fallback;
      if (speakerId === "user") return "user";
      const participant = activeSession && Array.isArray(activeSession.participants) ? activeSession.participants.find((item) => item.roleId === speakerId) : null;
      const role = roles.find((item) => item.id === speakerId);
      return (participant && participant.displayName) || (role && role.name) || speakerId;
    }
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
          selectedScenario = null;
          activeSession = null;
          storyState = null;
          sessionId = null;
          heading.textContent = role.name || role.id;
          sessionLine.textContent = "已选择角色，点击开始会话";
          messagesEl.replaceChildren();
          const empty = document.createElement("div");
          empty.className = "empty";
          empty.textContent = role.opening || "点击开始会话创建新会话。";
          messagesEl.append(empty);
          storyDetail.textContent = ((role.persona || "") + "\\n\\n" + (role.opening || "")).trim();
          startButton.disabled = false;
          resetButton.disabled = true;
          setComposer(false);
          renderRoles();
          renderScenarios();
          renderSessions();
          updateMemoryLink();
        };
        rolesEl.append(button);
      }
    }
    function renderScenarios() {
      scenariosEl.replaceChildren();
      for (const scenario of scenarios) {
        const button = document.createElement("button");
        button.className = "scenario-card" + (selectedScenario && selectedScenario.scenarioId === scenario.scenarioId ? " active" : "");
        button.innerHTML = "<strong></strong><span class='meta'></span>";
        button.querySelector("strong").textContent = scenario.name || scenario.scenarioId;
        button.querySelector(".meta").textContent = (scenario.mode || "scenario") + " · " + ((scenario.roleIds || []).length || 0) + " 个角色";
        button.onclick = () => {
          selectedScenario = scenario;
          selectedRole = null;
          activeSession = null;
          storyState = null;
          sessionId = null;
          heading.textContent = scenario.name || scenario.scenarioId;
          sessionLine.textContent = "已选择场景，点击开始会话";
          messagesEl.replaceChildren();
          const empty = document.createElement("div");
          empty.className = "empty";
          empty.textContent = scenario.description || "点击开始会话创建场景会话。";
          messagesEl.append(empty);
          storyDetail.textContent = ((scenario.description || "") + "\\n\\n角色：" + ((scenario.roleIds || []).join(", ") || "-")).trim();
          startButton.disabled = false;
          resetButton.disabled = true;
          setComposer(false);
          renderRoles();
          renderScenarios();
          renderSessions();
          updateMemoryLink();
        };
        scenariosEl.append(button);
      }
    }
    function renderSessions() {
      sessionsEl.replaceChildren();
      for (const item of sessions) {
        const button = document.createElement("button");
        button.className = "session-card" + (sessionId === item.sessionId ? " active" : "");
        button.innerHTML = "<strong></strong><span class='meta'></span>";
        button.querySelector("strong").textContent = item.scenarioName || item.roleName || item.roleId || "Session";
        button.querySelector(".meta").textContent = (item.mode || "companion") + " · " + (item.lastMessageAt || item.createdAt || "").replace("T", " ").slice(0, 19) + " " + item.sessionId.slice(0, 8);
        button.onclick = () => resumeSession(item.sessionId);
        sessionsEl.append(button);
      }
    }
    function renderStoryDetail() {
      if (activeSession && activeSession.mode === "scenario") {
        const participants = Array.isArray(activeSession.participants) ? activeSession.participants : [];
        const participantText = participants.map((item) => (item.displayName || item.roleId) + " (" + (item.status || "active") + ")").join("\\n") || "-";
        const stateText = storyState ? ("\\n\\n场景：" + (storyState.currentScene || "-") + "\\n阶段：" + ((storyState.currentState && storyState.currentState.phase) || "-")) : "";
        storyDetail.textContent = "参与角色：\\n" + participantText + stateText;
        return;
      }
      if (selectedScenario) {
        storyDetail.textContent = ((selectedScenario.description || "") + "\\n\\n角色：" + ((selectedScenario.roleIds || []).join(", ") || "-")).trim();
        return;
      }
      if (selectedRole) {
        storyDetail.textContent = ((selectedRole.persona || "") + "\\n\\n" + (selectedRole.opening || "")).trim();
        return;
      }
      storyDetail.textContent = "选择一个角色或场景后开始网页对话。";
    }
    async function loadSessions() {
      try {
        const response = await fetch("/api/sessions", { cache: "no-store" });
        const data = await response.json();
        sessions = Array.isArray(data.sessions) ? data.sessions : [];
        renderSessions();
      } catch {
        sessions = [];
        renderSessions();
      }
    }
    async function resumeSession(nextSessionId) {
      const summary = sessions.find((item) => item.sessionId === nextSessionId);
      sessionId = nextSessionId;
      activeSession = summary || null;
      storyState = null;
      if (summary && summary.mode === "scenario") {
        selectedScenario = scenarios.find((scenario) => scenario.scenarioId === summary.scenarioId) || selectedScenario;
        selectedRole = null;
      } else if (summary) {
        selectedRole = roles.find((role) => role.id === summary.roleId) || selectedRole;
        selectedScenario = null;
      }
      heading.textContent = (summary && (summary.scenarioName || summary.roleName)) || (selectedRole && selectedRole.name) || "Session";
      sessionLine.textContent = "session " + sessionId;
      messagesEl.replaceChildren();
      try {
        const response = await fetch("/api/sessions/" + encodeURIComponent(sessionId) + "/messages", { cache: "no-store" });
        const data = await response.json();
        for (const message of Array.isArray(data.messages) ? data.messages : []) addMessage(displaySpeaker(message.speakerId, message.role), message.content, message.role);
      } catch (error) {
        addMessage("error", String(error), "error");
      }
      await loadStoryState();
      await loadContextPreview();
      resetButton.disabled = false;
      setComposer(true);
      renderRoles();
      renderScenarios();
      renderSessions();
      renderStoryDetail();
      updateMemoryLink();
      input.focus();
    }
    async function loadStoryState() {
      if (!sessionId || !activeSession || activeSession.mode !== "scenario") {
        storyState = null;
        renderStoryDetail();
        return;
      }
      try {
        const response = await fetch("/api/sessions/" + encodeURIComponent(sessionId) + "/story-state", { cache: "no-store" });
        storyState = response.ok ? await response.json() : null;
      } catch {
        storyState = null;
      }
      renderStoryDetail();
    }
    async function loadContextPreview() {
      if (!sessionId) return;
      try {
        const response = await fetch("/api/sessions/" + encodeURIComponent(sessionId) + "/context-preview", { cache: "no-store" });
        const data = await response.json();
        const context = data.context || {};
        worldDetail.textContent = context.world || "-";
        relationshipDetail.textContent = context.relationship ? JSON.stringify(context.relationship, null, 2) : "-";
        memoryDetail.textContent = Array.isArray(context.selectedMemories)
          ? context.selectedMemories.map((item) => "[" + item.type + "] " + item.content).join("\\n")
          : "-";
        contextDetail.textContent = data.systemPrompt || "-";
      } catch (error) {
        contextDetail.textContent = String(error);
      }
    }
    function updateMemoryLink() {
      const params = new URLSearchParams({ userId: "local-user" });
      if (selectedRole) params.set("companionId", selectedRole.id);
      if (sessionId) params.set("sessionId", sessionId);
      memoryLink.href = "/memories?" + params.toString();
      contextLink.href = "/memories?" + params.toString();
    }
    async function loadRoles() {
      try {
        const response = await fetch("/api/roles", { cache: "no-store" });
        const data = await response.json();
        roles = Array.isArray(data.roles) ? data.roles : [];
        selectedRole = roles[0] || null;
        roleStatus.textContent = roles.length + " 个角色";
        renderStoryDetail();
        startButton.disabled = !selectedRole;
        renderRoles();
        updateMemoryLink();
        await loadScenarios();
        await loadSessions();
        setComposer(false);
      } catch (error) {
        roleStatus.textContent = "角色读取失败";
        storyDetail.textContent = String(error);
      }
    }
    async function loadScenarios() {
      try {
        const response = await fetch("/api/scenarios", { cache: "no-store" });
        const data = await response.json();
        scenarios = Array.isArray(data.scenarios) ? data.scenarios : [];
        renderScenarios();
      } catch {
        scenarios = [];
        renderScenarios();
      }
    }
    async function startSession() {
      if (selectedScenario) return startScenarioSession();
      if (!selectedRole || starting || streaming) return;
      starting = true;
      sessionId = null;
      activeSession = null;
      storyState = null;
      startButton.disabled = true;
      resetButton.disabled = true;
      setComposer(false);
      try {
        const response = await fetch("/api/sessions", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ role_id: selectedRole.id }) });
        if (!response.ok) { addMessage("error", await response.text(), "error"); return; }
        const data = await response.json();
        sessionId = data.sessionId;
        activeSession = data;
        heading.textContent = data.roleName || selectedRole.name || selectedRole.id;
        sessionLine.textContent = "session " + sessionId;
        messagesEl.replaceChildren();
        addMessage("assistant", data.opening || selectedRole.opening || "会话已开始", "assistant");
        resetButton.disabled = false;
        setComposer(true);
        updateMemoryLink();
        await loadContextPreview();
        await loadSessions();
        renderStoryDetail();
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
    async function startScenarioSession() {
      if (!selectedScenario || starting || streaming) return;
      starting = true;
      sessionId = null;
      activeSession = null;
      storyState = null;
      startButton.disabled = true;
      resetButton.disabled = true;
      setComposer(false);
      try {
        const response = await fetch("/api/sessions", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ mode: "scenario", scenarioId: selectedScenario.scenarioId }) });
        if (!response.ok) { addMessage("error", await response.text(), "error"); return; }
        const data = await response.json();
        sessionId = data.sessionId;
        activeSession = data;
        heading.textContent = data.scenarioName || selectedScenario.name || selectedScenario.scenarioId;
        sessionLine.textContent = "scenario session " + sessionId;
        messagesEl.replaceChildren();
        addMessage("scene", data.opening || selectedScenario.description || "场景会话已开始", "assistant");
        resetButton.disabled = false;
        setComposer(true);
        updateMemoryLink();
        await loadStoryState();
        await loadContextPreview();
        await loadSessions();
        input.focus();
      } catch (error) {
        addMessage("error", String(error), "error");
      } finally {
        starting = false;
        startButton.disabled = !selectedScenario;
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
      let assistant = null;
      let assistantSpeaker = "";
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
            if (item.event === "director" && item.data.fallback) sessionLine.textContent = "scenario session " + sessionId + " · director fallback";
            if (item.event === "token") {
              const speaker = item.data.speakerId || "assistant";
              if (!assistant || assistantSpeaker !== speaker) {
                assistantSpeaker = speaker;
                assistant = addMessage(displaySpeaker(speaker), "", "assistant");
              }
              assistant.textContent += item.data.delta || "";
            }
            if (item.event === "final") {
              const speaker = item.data.speakerId || assistantSpeaker || "assistant";
              if (!assistant || assistantSpeaker !== speaker) {
                assistantSpeaker = speaker;
                assistant = addMessage(displaySpeaker(speaker), "", "assistant");
              }
              assistant.textContent = item.data.message || assistant.textContent;
            }
            if (item.event === "error") throw new Error(item.data.message || "runtime error");
          }
          scroll();
        }
      } catch (error) {
        if (assistant) assistant.parentElement.remove();
        addMessage("error", String(error), "error");
      } finally {
        streaming = false;
        setComposer(Boolean(sessionId));
        await loadSessions();
        await loadStoryState();
        await loadContextPreview();
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
