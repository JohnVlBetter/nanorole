import { describe, expect, test, vi } from "vitest";

import { ensureRuntimeServer } from "../src/serverProcess.js";

describe("ensureRuntimeServer", () => {
  test("reuses an existing Nanorole service when health identifies it", async () => {
    const spawn = vi.fn();
    const healthCheck = vi.fn(async () => ({ ok: true, service: "nanorole-runtime" }));

    const server = await ensureRuntimeServer({
      host: "127.0.0.1",
      port: 8765,
      projectRoot: process.cwd(),
      healthCheck,
      spawnRuntime: spawn
    });

    expect(server.reused).toBe(true);
    expect(server.url).toBe("http://127.0.0.1:8765");
    expect(spawn).not.toHaveBeenCalled();
  });

  test("reports an unknown process instead of starting another server on that port", async () => {
    await expect(
      ensureRuntimeServer({
        host: "127.0.0.1",
        port: 8765,
        projectRoot: process.cwd(),
        healthCheck: async () => ({ ok: true, service: "other-service" }),
        spawnRuntime: vi.fn()
      })
    ).rejects.toThrow("port 8765 is already in use by an unknown service");
  });

  test("starts the runtime when health check cannot connect", async () => {
    const spawn = vi.fn(async () => undefined);

    const server = await ensureRuntimeServer({
      host: "127.0.0.1",
      port: 8765,
      projectRoot: process.cwd(),
      traceRequests: true,
      healthCheck: async () => ({ ok: false }),
      spawnRuntime: spawn
    });

    expect(server.reused).toBe(false);
    expect(spawn).toHaveBeenCalledWith({
      host: "127.0.0.1",
      port: 8765,
      projectRoot: process.cwd(),
      traceRequests: true
    });
  });
});
