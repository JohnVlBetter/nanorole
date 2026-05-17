import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

import { describe, expect, test } from "vitest";

import { readRuntimeLogs } from "../src/logs.js";

describe("readRuntimeLogs", () => {
  test("reads runtime JSONL entries and keeps malformed lines visible", async () => {
    const root = join(process.cwd(), ".tmp-demo-logs");
    const logsDir = join(root, ".nanorole", "logs");
    await mkdir(logsDir, { recursive: true });
    await writeFile(
      join(logsDir, "runtime.jsonl"),
      [
        JSON.stringify({ type: "session_created", session_id: "s1" }),
        "",
        "{bad json",
        JSON.stringify({ type: "request_completed", output: { message: "hello" } })
      ].join("\n"),
      "utf8"
    );

    const logs = await readRuntimeLogs(logsDir);

    expect(logs).toEqual([
      { type: "session_created", session_id: "s1" },
      { type: "parse_error", raw: "{bad json" },
      { type: "request_completed", output: { message: "hello" } }
    ]);
  });

  test("returns an empty list when runtime log file is missing", async () => {
    const root = join(process.cwd(), ".tmp-demo-empty-logs");

    await expect(readRuntimeLogs(join(root, ".nanorole", "logs"))).resolves.toEqual([]);
  });
});
