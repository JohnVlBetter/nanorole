import { spawn } from "node:child_process";

import type { CliFlags } from "./config.js";
import type { RuntimeServer } from "./serverProcess.js";

export interface RunLogsOptions {
  flags: CliFlags;
  projectRoot?: string;
  ensureRuntimeServer?: (options: {
    host: string;
    port: number;
    projectRoot: string;
    traceRequests?: boolean;
  }) => Promise<RuntimeServer>;
  openUrl?: (url: string) => Promise<void>;
  output?: Pick<NodeJS.WriteStream, "write">;
}

export async function runLogs(options: RunLogsOptions): Promise<void> {
  const openUrl = options.openUrl ?? defaultOpenUrl;
  const output = options.output ?? process.stdout;
  const host = options.flags.host ?? "127.0.0.1";
  const url = `http://${host}:3000/logs`;

  try {
    await openUrl(url);
    output.write(`Nanorole logs: ${url}\nRun \`corepack yarn demo\` if the demo server is not running.\n`);
  } catch {
    output.write(`Nanorole logs: ${url}\nRun \`corepack yarn demo\` if the demo server is not running.\n`);
  }
}

export async function defaultOpenUrl(url: string): Promise<void> {
  const command =
    process.platform === "win32"
      ? { file: "cmd", args: ["/c", "start", "", url] }
      : process.platform === "darwin"
        ? { file: "open", args: [url] }
        : { file: "xdg-open", args: [url] };

  await new Promise<void>((resolvePromise, reject) => {
    const child = spawn(command.file, command.args, {
      detached: true,
      stdio: "ignore",
      windowsHide: true
    });
    child.on("error", reject);
    child.on("spawn", () => {
      child.unref();
      resolvePromise();
    });
  });
}
