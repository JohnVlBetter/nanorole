import { createInterface } from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import { resolve } from "node:path";

import { loadCliConfig, type CliFlags } from "./config.js";
import { loadRolePackage } from "./role.js";
import { ensureRuntimeServer } from "./serverProcess.js";
import { createSession, streamMessage } from "./runtimeApi.js";
import { findProjectRoot } from "./projectRoot.js";

export interface ChatOptions {
  roleDir: string;
  flags: CliFlags;
  projectRoot?: string;
}

export async function runChat(options: ChatOptions): Promise<void> {
  const projectRoot = resolve(options.projectRoot ?? await findProjectRoot());
  const config = await loadCliConfig({ rootDir: projectRoot, flags: options.flags });
  const role = await loadRolePackage(resolve(projectRoot, options.roleDir));
  const server = await ensureRuntimeServer({
    host: config.server.host,
    port: config.server.port,
    projectRoot,
    traceRequests: config.logging.traceRequests
  });
  const session = await createSession(server.url, role);
  output.write(`${session.opening}\n`);

  const readline = createInterface({ input, output });
  try {
    while (true) {
      let line: string;
      try {
        line = await readline.question("> ");
      } catch (error) {
        if (isReadlineClosedError(error)) {
          break;
        }
        throw error;
      }
      const message = line.trim();
      if (!message || message === "/exit" || message === "/quit") {
        break;
      }
      for await (const event of streamMessage(server.url, session.sessionId, message)) {
        if (event.event === "token" && event.data && typeof event.data === "object" && "delta" in event.data) {
          output.write(String((event.data as { delta: string }).delta));
        }
        if (event.event === "final") {
          output.write("\n");
        }
        if (event.event === "error") {
          const data = event.data as { message?: string };
          output.write(`\nerror: ${data.message ?? "unknown runtime error"}\n`);
        }
      }
    }
  } finally {
    readline.close();
  }
}

export function isReadlineClosedError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }
  const code = (error as Error & { code?: string }).code;
  return code === "ERR_USE_AFTER_CLOSE" || error.message.toLowerCase().includes("readline was closed");
}
