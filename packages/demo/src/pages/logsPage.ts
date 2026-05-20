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
