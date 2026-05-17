import { readFile } from "node:fs/promises";
import { join } from "node:path";

export type RuntimeLogEntry = Record<string, unknown>;

export async function readRuntimeLogs(logsDir: string): Promise<RuntimeLogEntry[]> {
  let contents: string;
  try {
    contents = await readFile(join(logsDir, "runtime.jsonl"), "utf8");
  } catch {
    return [];
  }

  const entries: RuntimeLogEntry[] = [];
  for (const line of contents.split(/\r?\n/)) {
    if (!line.trim()) continue;
    try {
      const value = JSON.parse(line) as unknown;
      if (value && typeof value === "object" && !Array.isArray(value)) {
        entries.push(value as RuntimeLogEntry);
      }
    } catch {
      entries.push({ type: "parse_error", raw: line });
    }
  }
  return entries;
}
