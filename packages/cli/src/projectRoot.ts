import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";

export async function findProjectRoot(startDir = process.cwd()): Promise<string> {
  let current = resolve(startDir);
  while (true) {
    if (existsSync(resolve(current, "nanorole.config.yaml"))) {
      return current;
    }
    const parent = dirname(current);
    if (parent === current) {
      return resolve(startDir);
    }
    current = parent;
  }
}

