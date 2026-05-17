import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";

const repoRoot = fileURLToPath(new URL("../../..", import.meta.url));

describe("runtime restart script", () => {
  test("runtime restart is core-only and demo command starts the TS demo server", async () => {
    const rootPackage = JSON.parse(await readFile(resolve(repoRoot, "package.json"), "utf8")) as {
      scripts?: Record<string, string>;
    };
    const runtimeScript = await readFile(resolve(repoRoot, "scripts", "restart-runtime.ps1"), "utf8");
    const demoScript = await readFile(resolve(repoRoot, "scripts", "start-demo.ps1"), "utf8");

    expect(rootPackage.scripts?.["runtime:restart"]).toBe("powershell -ExecutionPolicy Bypass -File scripts/restart-runtime.ps1");
    expect(rootPackage.scripts?.demo).toBe("powershell -ExecutionPolicy Bypass -File scripts/start-demo.ps1");
    expect(runtimeScript).toContain("NANOROLE_PROJECT_ROOT");
    expect(runtimeScript).toContain("corepack yarn build");
    expect(runtimeScript).toContain("uvicorn");
    expect(runtimeScript).toContain("nanorole_runtime.server:app");
    expect(runtimeScript).not.toContain("Nanorole chat");
    expect(runtimeScript).not.toContain("Nanorole logs");
    expect(demoScript).toContain("NANOROLE_RUNTIME_URL");
    expect(demoScript).toContain("NANOROLE_DEMO_PORT");
    expect(demoScript).toContain("workspace @nanorole/demo");
  });
});
