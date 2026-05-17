import { readFile, readdir } from "node:fs/promises";
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

export async function discoverRoles(projectRoot: string): Promise<RolePackage[]> {
  const rolesDir = join(projectRoot, "examples", "roles");
  let entries: Array<{ name: string; isDirectory: () => boolean }>;
  try {
    entries = await readdir(rolesDir, { withFileTypes: true });
  } catch {
    return [];
  }

  const roles: RolePackage[] = [];
  for (const entry of entries.filter((item) => item.isDirectory()).sort((left, right) => left.name.localeCompare(right.name))) {
    try {
      roles.push(await loadRolePackage(join(rolesDir, entry.name)));
    } catch {
      continue;
    }
  }
  return roles;
}

async function loadRolePackage(roleDir: string): Promise<RolePackage> {
  const data = YAML.parse(await readFile(join(roleDir, "character.yaml"), "utf8")) ?? {};
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new Error("character.yaml must contain a mapping");
  }

  const record = data as Record<string, unknown>;
  for (const field of requiredFields) {
    if (!(field in record)) {
      throw new Error(`character.yaml missing required field: ${field}`);
    }
  }
  if ("model" in record) {
    throw new Error("model belongs in runtime config, not character.yaml");
  }
  if (!Array.isArray(record.goals) || !record.goals.every((goal) => typeof goal === "string" && goal.trim())) {
    throw new Error("goals must be a list of non-empty strings");
  }

  return record as unknown as RolePackage;
}
