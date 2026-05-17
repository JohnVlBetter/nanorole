import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

import { afterEach, describe, expect, test } from "vitest";

import { createDemoServer } from "../src/server.js";

const servers: Array<{ close: () => void }> = [];

afterEach(async () => {
  await Promise.all(
    servers.map(
      (server) =>
        new Promise<void>((resolve) => {
          server.close();
          resolve();
        })
    )
  );
  servers.length = 0;
});

async function listen(server: ReturnType<typeof createServer>): Promise<string> {
  servers.push(server);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("missing server address");
  return `http://127.0.0.1:${address.port}`;
}

describe("demo server", () => {
  test("serves chat/log pages and file-backed API responses", async () => {
    const root = join(process.cwd(), ".tmp-demo-server");
    await mkdir(join(root, "examples", "roles", "demo"), { recursive: true });
    await mkdir(join(root, ".nanorole", "logs"), { recursive: true });
    await writeFile(
      join(root, "examples", "roles", "demo", "character.yaml"),
      [
        "id: demo",
        "name: Demo Role",
        "version: 1.0.0",
        "world: Test world",
        "background: Test background",
        "persona: Useful",
        "goals:",
        "  - Help",
        "opening: Ready"
      ].join("\n"),
      "utf8"
    );
    await writeFile(join(root, ".nanorole", "logs", "runtime.jsonl"), '{"type":"request_completed"}\n', "utf8");
    const server = createDemoServer({ projectRoot: root, runtimeUrl: "http://127.0.0.1:9" });
    const baseUrl = await listen(server);

    await expect(fetch(`${baseUrl}/chat`).then((response) => response.text())).resolves.toContain("Nanorole Chat");
    await expect(fetch(`${baseUrl}/logs`).then((response) => response.text())).resolves.toContain("Nanorole Logs");
    await expect(fetch(`${baseUrl}/memories`).then((response) => response.text())).resolves.toContain("Nanorole Memories");
    await expect(fetch(`${baseUrl}/api/roles`).then((response) => response.json())).resolves.toMatchObject({
      roles: [{ id: "demo", name: "Demo Role" }]
    });
    await expect(fetch(`${baseUrl}/api/logs`).then((response) => response.json())).resolves.toEqual({
      logs: [{ type: "request_completed" }]
    });
  });

  test("keeps the chat composer focusable and starts a default session", async () => {
    const demo = createDemoServer({ projectRoot: process.cwd(), runtimeUrl: "http://127.0.0.1:9" });
    const baseUrl = await listen(demo);

    const html = await fetch(`${baseUrl}/chat`).then((response) => response.text());

    expect(html).not.toMatch(/<textarea[^>]*\sdisabled\b/i);
    expect(html).toContain("input.readOnly = !enabled");
    expect(html).toContain("await startSession();");
  });

  test("proxies session creation and message streams to Python core", async () => {
    const runtime = createServer(async (request: IncomingMessage, response: ServerResponse) => {
      if (request.url === "/v1/sessions" && request.method === "POST") {
        response.setHeader("content-type", "application/json");
        response.end(JSON.stringify({ sessionId: "s1", opening: "Ready" }));
        return;
      }
      if (request.url === "/v1/sessions/s1/messages:stream" && request.method === "POST") {
        response.setHeader("content-type", "text/event-stream");
        response.end('event: token\ndata: {"delta":"hi"}\n\n');
        return;
      }
      response.statusCode = 404;
      response.end();
    });
    const runtimeUrl = await listen(runtime);
    const demo = createDemoServer({ projectRoot: process.cwd(), runtimeUrl });
    const baseUrl = await listen(demo);

    await expect(
      fetch(`${baseUrl}/api/sessions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ role_id: "demo" })
      }).then((response) => response.json())
    ).resolves.toEqual({ sessionId: "s1", opening: "Ready" });

    await expect(
      fetch(`${baseUrl}/api/sessions/s1/messages:stream`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ message: "hello" })
      }).then((response) => response.text())
    ).resolves.toContain('event: token\ndata: {"delta":"hi"}');
  });

  test("proxies session and memory management endpoints to Python core", async () => {
    const seen: string[] = [];
    const runtime = createServer(async (request: IncomingMessage, response: ServerResponse) => {
      const body = request.method === "GET" || request.method === "DELETE" ? "" : await new Promise<string>((resolve) => {
        const chunks: Buffer[] = [];
        request.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
        request.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
      });
      seen.push(`${request.method} ${request.url} ${body}`.trim());
      response.setHeader("content-type", "application/json");
      response.end(JSON.stringify({ ok: true }));
    });
    const runtimeUrl = await listen(runtime);
    const demo = createDemoServer({ projectRoot: process.cwd(), runtimeUrl });
    const baseUrl = await listen(demo);

    await fetch(`${baseUrl}/api/sessions`);
    await fetch(`${baseUrl}/api/sessions/s1`);
    await fetch(`${baseUrl}/api/sessions/s1/messages`);
    await fetch(`${baseUrl}/api/sessions/s1/context-preview?userInput=hello`);
    await fetch(`${baseUrl}/api/memories?userId=local-user&companionId=demo`);
    await fetch(`${baseUrl}/api/memories`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ companionId: "demo", type: "preference", content: "x", importance: 0.5, confidence: 0.5 })
    });
    await fetch(`${baseUrl}/api/memories/m1`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ content: "y" })
    });
    await fetch(`${baseUrl}/api/memories/m1`, { method: "DELETE" });

    expect(seen).toEqual([
      "GET /v1/sessions",
      "GET /v1/sessions/s1",
      "GET /v1/sessions/s1/messages",
      "GET /v1/sessions/s1/context-preview?userInput=hello",
      "GET /v1/memories?userId=local-user&companionId=demo",
      'POST /v1/memories {"companionId":"demo","type":"preference","content":"x","importance":0.5,"confidence":0.5}',
      'PATCH /v1/memories/m1 {"content":"y"}',
      "DELETE /v1/memories/m1"
    ]);
  });
});
