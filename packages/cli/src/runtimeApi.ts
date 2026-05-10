import { SseDecoder, type SseEvent } from "./sse.js";
import type { RolePackage } from "./role.js";

export async function createSession(baseUrl: string, role: RolePackage): Promise<{ sessionId: string; opening: string }> {
  const response = await fetch(`${baseUrl}/v1/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role })
  });
  if (!response.ok) {
    throw new Error(`failed to create session: ${response.status} ${await response.text()}`);
  }
  return (await response.json()) as { sessionId: string; opening: string };
}

export async function* streamMessage(baseUrl: string, sessionId: string, message: string): AsyncGenerator<SseEvent> {
  const response = await fetch(`${baseUrl}/v1/sessions/${sessionId}/messages:stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message })
  });
  if (!response.ok || !response.body) {
    throw new Error(`message stream failed: ${response.status} ${await response.text()}`);
  }

  const decoder = new TextDecoder();
  const sse = new SseDecoder();
  for await (const chunk of response.body as unknown as AsyncIterable<Uint8Array>) {
    for (const event of sse.push(decoder.decode(chunk, { stream: true }))) {
      yield event;
    }
  }
}

