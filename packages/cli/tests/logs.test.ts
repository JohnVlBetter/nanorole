import { describe, expect, test, vi } from "vitest";

import { runLogs } from "../src/logs.js";

describe("runLogs", () => {
  test("opens the TS demo logs page without starting Python runtime", async () => {
    const ensureRuntimeServer = vi.fn();
    const openUrl = vi.fn(async () => undefined);
    const output = { write: vi.fn() };

    await runLogs({
      flags: { port: 8765 },
      projectRoot: process.cwd(),
      ensureRuntimeServer,
      openUrl,
      output
    });

    expect(ensureRuntimeServer).not.toHaveBeenCalled();
    expect(openUrl).toHaveBeenCalledWith("http://127.0.0.1:3000/logs");
    expect(output.write).toHaveBeenCalledWith("Nanorole logs: http://127.0.0.1:3000/logs\nRun `corepack yarn demo` if the demo server is not running.\n");
  });
});
