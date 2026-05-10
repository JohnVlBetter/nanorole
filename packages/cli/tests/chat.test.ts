import { describe, expect, test } from "vitest";

import { isReadlineClosedError } from "../src/chat.js";

describe("isReadlineClosedError", () => {
  test("detects readline closed errors so piped input can exit cleanly", () => {
    expect(isReadlineClosedError(new Error("readline was closed"))).toBe(true);
    expect(isReadlineClosedError(Object.assign(new Error("closed"), { code: "ERR_USE_AFTER_CLOSE" }))).toBe(true);
    expect(isReadlineClosedError(new Error("different failure"))).toBe(false);
  });
});

