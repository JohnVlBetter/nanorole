import { describe, expect, test } from "vitest";

import { parseCliArgs } from "../src/args.js";

describe("parseCliArgs", () => {
  test("parses chat role directory and runtime flags", () => {
    const parsed = parseCliArgs(["chat", "examples/roles/demo", "--port", "9999", "--host", "127.0.0.2", "--debug"]);

    expect(parsed).toEqual({
      command: "chat",
      roleDir: "examples/roles/demo",
      flags: {
        port: 9999,
        host: "127.0.0.2",
        debug: true
      }
    });
  });
});

