#!/usr/bin/env node

import { parseCliArgs } from "./args.js";
import { runChat } from "./chat.js";
import { runLogs } from "./logs.js";

export async function main(argv = process.argv.slice(2)): Promise<void> {
  const parsed = parseCliArgs(argv);
  if (parsed.command === "chat") {
    await runChat({ roleDir: parsed.roleDir, flags: parsed.flags });
    return;
  }
  await runLogs({ flags: parsed.flags });
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
