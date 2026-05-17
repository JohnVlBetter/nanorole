import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

import { describe, expect, test } from "vitest";

import { discoverRoles } from "../src/roles.js";

describe("discoverRoles", () => {
  test("loads role packages from examples/roles and skips invalid packages", async () => {
    const root = join(process.cwd(), ".tmp-demo-roles");
    await mkdir(join(root, "examples", "roles", "demo"), { recursive: true });
    await mkdir(join(root, "examples", "roles", "broken"), { recursive: true });
    await writeFile(
      join(root, "examples", "roles", "demo", "character.yaml"),
      [
        "id: demo",
        "name: Demo Role",
        "version: 1.0.0",
        "world: Test world",
        "background: Test background",
        "persona: Useful",
        "goals:",
        "  - Help",
        "opening: Ready"
      ].join("\n"),
      "utf8"
    );
    await writeFile(join(root, "examples", "roles", "broken", "character.yaml"), "id: broken\n", "utf8");

    const roles = await discoverRoles(root);

    expect(roles).toHaveLength(1);
    expect(roles[0]).toMatchObject({ id: "demo", name: "Demo Role", opening: "Ready" });
  });
});
