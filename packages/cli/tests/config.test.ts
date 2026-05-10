import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { describe, expect, test } from "vitest";

import { loadCliConfig } from "../src/config.js";

describe("loadCliConfig", () => {
  test("merges defaults, config file, .env/process env, and flags in precedence order", async () => {
    const root = join(process.cwd(), ".tmp-config-test");
    await mkdir(root, { recursive: true });
    await writeFile(
      join(root, "nanorole.config.yaml"),
      [
        "server:",
        "  host: 0.0.0.0",
        "  port: 7000",
        "model:",
        "  base_url: https://from-config.example/v1",
        "  name: from-config",
        "logging:",
        "  trace_requests: false",
        "paths:",
        "  logs_dir: custom/logs",
        "  sessions_dir: custom/sessions"
      ].join("\n")
    );
    await writeFile(
      join(root, ".env"),
      [
        "OPENAI_API_KEY=env-file-key",
        "OPENAI_BASE_URL=https://from-env-file.example/v1",
        "NANOROLE_MODEL=from-env-file"
      ].join("\n")
    );

    const config = await loadCliConfig({
      rootDir: root,
      env: { NANOROLE_MODEL: "from-process-env" },
      flags: { port: 8123, debug: true }
    });

    expect(config.server.host).toBe("0.0.0.0");
    expect(config.server.port).toBe(8123);
    expect(config.model.baseUrl).toBe("https://from-env-file.example/v1");
    expect(config.model.name).toBe("from-process-env");
    expect(config.model.apiKey).toBe("env-file-key");
    expect(config.logging.traceRequests).toBe(true);
    expect(config.paths.logsDir).toBe(join(root, "custom", "logs"));
    expect(config.paths.sessionsDir).toBe(join(root, "custom", "sessions"));
  });

  test("loads DeepSeek key and request options from config and env", async () => {
    const root = join(process.cwd(), ".tmp-deepseek-config-test");
    await mkdir(root, { recursive: true });
    await writeFile(
      join(root, "nanorole.config.yaml"),
      [
        "model:",
        "  provider: deepseek",
        "  base_url: https://api.deepseek.com",
        "  name: deepseek-v4-pro",
        "  reasoning_effort: high",
        "  extra_body:",
        "    thinking:",
        "      type: enabled"
      ].join("\n")
    );
    await writeFile(join(root, ".env"), "DEEPSEEK_API_KEY=deepseek-file-key\n");

    const config = await loadCliConfig({ rootDir: root, env: {} });

    expect(config.model.provider).toBe("deepseek");
    expect(config.model.baseUrl).toBe("https://api.deepseek.com");
    expect(config.model.name).toBe("deepseek-v4-pro");
    expect(config.model.apiKey).toBe("deepseek-file-key");
    expect(config.model.reasoningEffort).toBe("high");
    expect(config.model.extraBody).toEqual({ thinking: { type: "enabled" } });
  });
});
