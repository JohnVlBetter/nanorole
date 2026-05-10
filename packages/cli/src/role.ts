import { readFile } from "node:fs/promises";
import { join } from "node:path";
import YAML from "yaml";

export interface RolePackage {
  id: string;
  name: string;
  version: string;
  world: string;
  background: string;
  persona: string;
  goals: string[];
  opening: string;
  style?: Record<string, unknown>;
  safety_rules?: string[];
  metadata?: Record<string, unknown>;
}

const requiredFields = ["id", "name", "version", "world", "background", "persona", "goals", "opening"] as const;

export async function loadRolePackage(roleDir: string): Promise<RolePackage> {
  const path = join(roleDir, "character.yaml");
  const data = YAML.parse(await readFile(path, "utf8")) ?? {};
  for (const field of requiredFields) {
    if (!(field in data)) {
      throw new Error(`character.yaml missing required field: ${field}`);
    }
  }
  if ("model" in data) {
    throw new Error("model belongs in runtime config, not character.yaml");
  }
  return data as RolePackage;
}
