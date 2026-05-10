export interface SseEvent {
  event: string;
  data: unknown;
}

export class SseDecoder {
  private buffer = "";

  push(chunk: string): SseEvent[] {
    this.buffer += chunk;
    const events: SseEvent[] = [];

    while (true) {
      const boundary = this.findBoundary();
      if (boundary === -1) break;

      const raw = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(this.boundaryLength(boundary));
      if (!raw.trim()) continue;
      events.push(parseEvent(raw));
    }

    return events;
  }

  private findBoundary(): number {
    const unix = this.buffer.indexOf("\n\n");
    const windows = this.buffer.indexOf("\r\n\r\n");
    if (unix === -1) return windows;
    if (windows === -1) return unix;
    return Math.min(unix, windows);
  }

  private boundaryLength(boundary: number): number {
    return this.buffer.startsWith("\r\n\r\n", boundary) ? boundary + 4 : boundary + 2;
  }
}

function parseEvent(raw: string): SseEvent {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }
  const dataText = dataLines.join("\n");
  return { event, data: dataText ? JSON.parse(dataText) : undefined };
}

