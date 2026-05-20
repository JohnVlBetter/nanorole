export const MEMORIES_HTML = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Nanorole Memories</title>
  <style>
    :root { --bg: #f4f6f8; --panel: #fff; --soft: #f8fafc; --border: #d6dde7; --text: #17202a; --muted: #657386; --accent: #0f766e; --accent-soft: #e6f4f1; --danger: #b42318; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); }
    button, input, select, textarea { font: inherit; }
    button, input, select, textarea { border: 1px solid var(--border); border-radius: 6px; background: var(--panel); }
    button { padding: 8px 12px; cursor: pointer; }
    button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
    button.danger { color: var(--danger); }
    input, select, textarea { width: 100%; padding: 9px 10px; }
    textarea { min-height: 74px; resize: vertical; line-height: 20px; }
    header { position: sticky; top: 0; z-index: 2; display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 14px 20px; background: var(--panel); border-bottom: 1px solid var(--border); }
    h1 { margin: 0; font-size: 18px; }
    h2 { margin: 0; font-size: 15px; }
    a { color: var(--accent); text-decoration: none; font-size: 13px; }
    main { max-width: 1180px; margin: 0 auto; padding: 18px 20px 32px; display: grid; grid-template-columns: 320px minmax(0, 1fr); gap: 18px; align-items: start; }
    aside, section { display: grid; gap: 12px; }
    .panel { border: 1px solid var(--border); border-radius: 7px; background: var(--panel); padding: 14px; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .full { grid-column: 1 / -1; }
    .muted { color: var(--muted); font-size: 12px; }
    .status { color: var(--muted); font-size: 13px; }
    .group { display: grid; gap: 8px; }
    .memory { display: grid; gap: 8px; border: 1px solid var(--border); border-left: 4px solid var(--accent); border-radius: 7px; background: var(--panel); padding: 12px; }
    .memory header { position: static; display: flex; padding: 0; border: 0; background: transparent; }
    .memory textarea { min-height: 64px; }
    .sources { display: grid; gap: 4px; }
    .source-line { overflow-wrap: anywhere; }
    .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .pill { display: inline-flex; align-items: center; border-radius: 999px; background: var(--accent-soft); color: var(--accent); padding: 3px 8px; font-size: 12px; font-weight: 700; }
    pre { margin: 10px 0; white-space: pre-wrap; overflow-wrap: anywhere; font-family: Consolas, monospace; font-size: 12px; line-height: 18px; }
    @media (max-width: 880px) { main { grid-template-columns: 1fr; } .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <div><h1>Nanorole Memories</h1><div class="status" id="status">Not loaded</div></div>
    <div class="row"><a href="/chat">Back to chat</a><a href="/logs">Logs</a></div>
  </header>
  <main>
    <aside>
      <form class="panel grid" id="filters">
        <label>User ID<input id="user-id" value="local-user" /></label>
        <label>Companion ID<input id="companion-id" /></label>
        <button class="primary full" type="submit">Load memories</button>
      </form>
      <form class="panel grid" id="add-form">
        <label>Type<select id="new-type"><option>preference</option><option>profile</option><option>episodic</option><option>relationship</option><option>boundary</option></select></label>
        <label>Importance<input id="new-importance" type="number" min="0" max="1" step="0.1" value="0.7" /></label>
        <label>Confidence<input id="new-confidence" type="number" min="0" max="1" step="0.1" value="0.8" /></label>
        <label class="full">Source message IDs<input id="new-sources" placeholder="comma separated" /></label>
        <label class="full">Content<textarea id="new-content"></textarea></label>
        <button class="primary full" type="submit">Add memory</button>
      </form>
      <form class="panel grid" id="preview-form">
        <label class="full">Session ID<input id="preview-session" /></label>
        <label class="full">User input<input id="preview-input" placeholder="optional next message" /></label>
        <button class="primary full" type="submit">Preview context</button>
      </form>
    </aside>
    <section id="memories"></section>
  </main>
  <script>
    const params = new URLSearchParams(location.search);
    const statusEl = document.querySelector("#status");
    const memoriesEl = document.querySelector("#memories");
    const userInput = document.querySelector("#user-id");
    const companionInput = document.querySelector("#companion-id");
    const filters = document.querySelector("#filters");
    const addForm = document.querySelector("#add-form");
    const previewForm = document.querySelector("#preview-form");
    const previewSession = document.querySelector("#preview-session");
    userInput.value = params.get("userId") || "local-user";
    companionInput.value = params.get("companionId") || "";
    previewSession.value = params.get("sessionId") || "";
    let memories = [];
    function sourceIds(value) {
      return String(value || "").split(",").map((item) => item.trim()).filter(Boolean);
    }
    function grouped(items) {
      return items.reduce((acc, item) => {
        (acc[item.type] ||= []).push(item);
        return acc;
      }, {});
    }
    function render() {
      memoriesEl.replaceChildren();
      const groups = grouped(memories);
      for (const type of ["boundary", "preference", "profile", "relationship", "episodic"]) {
        const items = groups[type] || [];
        if (!items.length) continue;
        const group = document.createElement("div");
        group.className = "group";
        const title = document.createElement("h2");
        title.textContent = type + " (" + items.length + ")";
        group.append(title);
        for (const memory of items) group.append(memoryCard(memory));
        memoriesEl.append(group);
      }
      if (!memories.length) {
        const empty = document.createElement("div");
        empty.className = "panel muted";
        empty.textContent = "No active memories.";
        memoriesEl.append(empty);
      }
    }
    function renderPreview(data) {
      const panel = document.createElement("div");
      panel.className = "panel";
      const system = Array.isArray(data.messages) ? data.messages.find((item) => item.role === "system") : null;
      panel.innerHTML = '<h2>Context preview</h2><pre></pre><div class="muted"></div>';
      panel.querySelector("pre").textContent = system ? system.content : JSON.stringify(data, null, 2);
      panel.querySelector(".muted").textContent = "Selected memories: " + ((data.usedMemories || []).map((item) => item.memoryId).join(", ") || "-");
      memoriesEl.prepend(panel);
    }
    function renderSources(container, memory) {
      container.replaceChildren();
      const label = document.createElement("div");
      label.textContent = "Sources:";
      container.append(label);
      const sourceMessages = Array.isArray(memory.sourceMessages) ? memory.sourceMessages : [];
      if (!sourceMessages.length) {
        const fallback = document.createElement("div");
        fallback.className = "source-line";
        fallback.textContent = ((memory.sourceMessageIds || []).join(", ") || "-");
        container.append(fallback);
        return;
      }
      for (const source of sourceMessages) {
        const line = document.createElement("div");
        line.className = "source-line";
        line.textContent = (source.role || "message") + ": " + (source.content || source.messageId);
        container.append(line);
      }
    }
    function memoryCard(memory) {
      const card = document.createElement("article");
      card.className = "memory";
      card.innerHTML =
        '<header><span class="pill"></span><span class="muted"></span></header>' +
        '<textarea class="content"></textarea>' +
        '<div class="grid"><label>Importance<input class="importance" type="number" min="0" max="1" step="0.1" /></label><label>Confidence<input class="confidence" type="number" min="0" max="1" step="0.1" /></label></div>' +
        '<div class="muted sources"></div><div class="row"><button class="save primary">Save</button><button class="archive">Archive</button><button class="delete danger">Delete</button></div>';
      card.querySelector(".pill").textContent = memory.type;
      card.querySelector(".muted").textContent = memory.memoryId.slice(0, 8) + " updated " + String(memory.updatedAt || "").slice(0, 19).replace("T", " ");
      card.querySelector(".content").value = memory.content;
      card.querySelector(".importance").value = memory.importance;
      card.querySelector(".confidence").value = memory.confidence;
      renderSources(card.querySelector(".sources"), memory);
      card.querySelector(".save").onclick = () => updateMemory(memory.memoryId, {
        content: card.querySelector(".content").value,
        importance: Number(card.querySelector(".importance").value),
        confidence: Number(card.querySelector(".confidence").value)
      });
      card.querySelector(".archive").onclick = () => updateMemory(memory.memoryId, { status: "archived" });
      card.querySelector(".delete").onclick = () => deleteMemory(memory.memoryId);
      return card;
    }
    async function loadMemories() {
      const companionId = companionInput.value.trim();
      if (!companionId) {
        statusEl.textContent = "Companion ID is required.";
        memories = [];
        render();
        return;
      }
      const query = new URLSearchParams({ userId: userInput.value.trim() || "local-user", companionId });
      const response = await fetch("/api/memories?" + query.toString(), { cache: "no-store" });
      const data = await response.json();
      memories = Array.isArray(data.memories) ? data.memories : [];
      statusEl.textContent = memories.length + " active memories";
      render();
    }
    async function updateMemory(memoryId, patch) {
      await fetch("/api/memories/" + encodeURIComponent(memoryId), { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify(patch) });
      await loadMemories();
    }
    async function deleteMemory(memoryId) {
      await fetch("/api/memories/" + encodeURIComponent(memoryId), { method: "DELETE" });
      await loadMemories();
    }
    filters.onsubmit = (event) => { event.preventDefault(); loadMemories().catch((error) => statusEl.textContent = String(error)); };
    addForm.onsubmit = async (event) => {
      event.preventDefault();
      await fetch("/api/memories", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          userId: userInput.value.trim() || "local-user",
          companionId: companionInput.value.trim(),
          type: document.querySelector("#new-type").value,
          content: document.querySelector("#new-content").value.trim(),
          importance: Number(document.querySelector("#new-importance").value),
          confidence: Number(document.querySelector("#new-confidence").value),
          sourceMessageIds: sourceIds(document.querySelector("#new-sources").value)
        })
      });
      document.querySelector("#new-content").value = "";
      document.querySelector("#new-sources").value = "";
      await loadMemories();
    };
    previewForm.onsubmit = async (event) => {
      event.preventDefault();
      const sessionId = previewSession.value.trim();
      if (!sessionId) {
        statusEl.textContent = "Session ID is required for context preview.";
        return;
      }
      const query = new URLSearchParams({ userInput: document.querySelector("#preview-input").value });
      const response = await fetch("/api/sessions/" + encodeURIComponent(sessionId) + "/context-preview?" + query.toString(), { cache: "no-store" });
      renderPreview(await response.json());
    };
    loadMemories().catch((error) => statusEl.textContent = String(error));
  </script>
</body>
</html>`;
