import { describe, expect, test } from "vitest";

import { SseDecoder } from "../src/sse.js";

describe("SseDecoder", () => {
  test("parses token final and error events across chunk boundaries", () => {
    const decoder = new SseDecoder();
    const first = decoder.push('event: token\ndata: {"delta":"hel');
    const second = decoder.push('lo"}\n\nevent: final\ndata: {"message":"hello"}\n\n');
    const third = decoder.push('event: error\ndata: {"message":"bad"}\n\n');

    expect(first).toEqual([]);
    expect(second).toEqual([
      { event: "token", data: { delta: "hello" } },
      { event: "final", data: { message: "hello" } }
    ]);
    expect(third).toEqual([{ event: "error", data: { message: "bad" } }]);
  });
});

