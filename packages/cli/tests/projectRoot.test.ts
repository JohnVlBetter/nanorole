import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { describe, expect, test } from "vitest";

import { findProjectRoot } from "../src/projectRoot.js";

describe("findProjectRoot", () => {
  test("walks upward from package cwd to the repo config", async () => {
    const root = join(process.cwd(), ".tmp-project-root-test");
    const nested = join(root, "packages", "cli");
    await mkdir(nested, { recursive: true });
    await writeFile(join(root, "nanorole.config.yaml"), "server:\n  port: 8765\n");

    expect(await findProjectRoot(nested)).toBe(root);
  });
});

