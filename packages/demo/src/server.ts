import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { join } from "node:path";

import { readRuntimeLogs } from "./logs.js";
import { CHAT_HTML, LOGS_HTML, MEMORIES_HTML } from "./pages.js";
import { discoverRoles } from "./roles.js";

export interface DemoServerOptions {
  projectRoot: string;
  runtimeUrl: string;
}

export function createDemoServer(options: DemoServerOptions): Server {
  return createServer((request, response) => {
    handleRequest(request, response, options).catch((error: unknown) => {
      sendJson(response, 500, { error: error instanceof Error ? error.message : String(error) });
    });
  });
}

async function handleRequest(request: IncomingMessage, response: ServerResponse, options: DemoServerOptions): Promise<void> {
  const url = new URL(request.url ?? "/", "http://127.0.0.1");
  if (request.method === "GET" && url.pathname === "/") {
    response.statusCode = 302;
    response.setHeader("location", "/chat");
    response.end();
    return;
  }
  if (request.method === "GET" && url.pathname === "/chat") {
    sendHtml(response, CHAT_HTML);
    return;
  }
  if (request.method === "GET" && url.pathname === "/logs") {
    sendHtml(response, LOGS_HTML);
    return;
  }
  if (request.method === "GET" && url.pathname === "/memories") {
    sendHtml(response, MEMORIES_HTML);
    return;
  }
  if (request.method === "GET" && url.pathname === "/api/roles") {
    sendJson(response, 200, { roles: await discoverRoles(options.projectRoot) });
    return;
  }
  if (request.method === "GET" && url.pathname === "/api/logs") {
    sendJson(response, 200, { logs: await readRuntimeLogs(join(options.projectRoot, ".nanorole", "logs")) });
    return;
  }
  if (request.method === "POST" && url.pathname === "/api/sessions") {
    await proxyRequest(request, response, `${options.runtimeUrl}/v1/sessions`);
    return;
  }
  if (request.method === "GET" && url.pathname === "/api/sessions") {
    await proxyRequest(request, response, `${options.runtimeUrl}/v1/sessions`);
    return;
  }
  const sessionMatch = url.pathname.match(/^\/api\/sessions\/([^/]+)$/);
  if (request.method === "GET" && sessionMatch) {
    await proxyRequest(request, response, `${options.runtimeUrl}/v1/sessions/${encodeURIComponent(decodeURIComponent(sessionMatch[1]))}`);
    return;
  }
  const messagesMatch = url.pathname.match(/^\/api\/sessions\/([^/]+)\/messages$/);
  if (request.method === "GET" && messagesMatch) {
    await proxyRequest(request, response, `${options.runtimeUrl}/v1/sessions/${encodeURIComponent(decodeURIComponent(messagesMatch[1]))}/messages`);
    return;
  }
  const contextPreviewMatch = url.pathname.match(/^\/api\/sessions\/([^/]+)\/context-preview$/);
  if (request.method === "GET" && contextPreviewMatch) {
    await proxyRequest(
      request,
      response,
      `${options.runtimeUrl}/v1/sessions/${encodeURIComponent(decodeURIComponent(contextPreviewMatch[1]))}/context-preview${url.search}`
    );
    return;
  }
  const streamMatch = url.pathname.match(/^\/api\/sessions\/([^/]+)\/messages:stream$/);
  if (request.method === "POST" && streamMatch) {
    await proxyRequest(request, response, `${options.runtimeUrl}/v1/sessions/${encodeURIComponent(decodeURIComponent(streamMatch[1]))}/messages:stream`);
    return;
  }
  if (request.method === "GET" && url.pathname === "/api/memories") {
    await proxyRequest(request, response, `${options.runtimeUrl}/v1/memories${url.search}`);
    return;
  }
  if (request.method === "POST" && url.pathname === "/api/memories") {
    await proxyRequest(request, response, `${options.runtimeUrl}/v1/memories`);
    return;
  }
  const memoryMatch = url.pathname.match(/^\/api\/memories\/([^/]+)$/);
  if ((request.method === "PATCH" || request.method === "DELETE") && memoryMatch) {
    await proxyRequest(request, response, `${options.runtimeUrl}/v1/memories/${encodeURIComponent(decodeURIComponent(memoryMatch[1]))}`);
    return;
  }
  sendJson(response, 404, { error: "not found" });
}

async function proxyRequest(request: IncomingMessage, response: ServerResponse, targetUrl: string): Promise<void> {
  const body = await readRequestBody(request);
  const upstream = await fetch(targetUrl, {
    method: request.method,
    headers: { "content-type": request.headers["content-type"] ?? "application/json" },
    body: body.length ? new Uint8Array(body) : undefined,
  });

  response.statusCode = upstream.status;
  const contentType = upstream.headers.get("content-type");
  if (contentType) response.setHeader("content-type", contentType);
  if (!upstream.body) {
    response.end();
    return;
  }
  for await (const chunk of upstream.body as unknown as AsyncIterable<Uint8Array>) {
    response.write(chunk);
  }
  response.end();
}

async function readRequestBody(request: IncomingMessage): Promise<Buffer> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return Buffer.concat(chunks);
}

function sendHtml(response: ServerResponse, html: string): void {
  response.statusCode = 200;
  response.setHeader("content-type", "text/html; charset=utf-8");
  response.end(html);
}

function sendJson(response: ServerResponse, statusCode: number, value: unknown): void {
  response.statusCode = statusCode;
  response.setHeader("content-type", "application/json; charset=utf-8");
  response.end(JSON.stringify(value));
}
