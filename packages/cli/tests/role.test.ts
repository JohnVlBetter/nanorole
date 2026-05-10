import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { describe, expect, test } from "vitest";

import { loadRolePackage } from "../src/role.js";

describe("loadRolePackage", () => {
  test("rejects model because model selection belongs in runtime config", async () => {
    const root = join(process.cwd(), ".tmp-role-test");
    const roleDir = join(root, "role");
    await mkdir(roleDir, { recursive: true });
    await writeFile(
      join(roleDir, "character.yaml"),
      [
        "id: clockwork-sage",
        "name: Clockwork Sage",
        "version: 1.0.0",
        "world: A city of brass towers.",
        "background: The sage repairs memory machines.",
        "persona: Measured, curious, precise.",
        "goals:",
        "  - Help the user uncover forgotten causes.",
        "opening: The gears quiet as you enter.",
        "model: gpt-4.1-mini"
      ].join("\n")
    );

    await expect(loadRolePackage(roleDir)).rejects.toThrow("model belongs in runtime config");
  });
});

