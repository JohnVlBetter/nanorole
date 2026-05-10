import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { isAbsolute, resolve } from "node:path";
import YAML from "yaml";

export interface CliConfig {
  server: {
    host: string;
    port: number;
  };
  model: {
    provider: string;
    baseUrl: string;
    name: string;
    apiKey?: string;
    reasoningEffort?: string;
    extraBody: Record<string, unknown>;
  };
  logging: {
    level: string;
    traceRequests: boolean;
  };
  paths: {
    logsDir: string;
    sessionsDir: string;
  };
}

export interface CliFlags {
  host?: string;
  port?: number;
  debug?: boolean;
  model?: string;
  baseUrl?: string;
}

export interface LoadCliConfigOptions {
  rootDir?: string;
  env?: Record<string, string | undefined>;
  flags?: CliFlags;
}

export async function loadCliConfig(options: LoadCliConfigOptions = {}): Promise<CliConfig> {
  const rootDir = resolve(options.rootDir ?? process.cwd());
  const env = options.env ?? process.env;
  const flags = options.flags ?? {};
  const configPath = resolve(rootDir, "nanorole.config.yaml");
  const envPath = resolve(rootDir, ".env");

  const data: Record<string, any> = {
    server: { host: "127.0.0.1", port: 8765 },
    model: {
      provider: "openai",
      base_url: "https://api.openai.com/v1",
      name: "gpt-4.1-mini"
    },
    logging: { level: "INFO", trace_requests: false },
    paths: { logs_dir: ".nanorole/logs", sessions_dir: ".nanorole/sessions" }
  };

  if (existsSync(configPath)) {
    const fileData = YAML.parse(await readFile(configPath, "utf8")) ?? {};
    deepMerge(data, fileData);
  }

  const envFileValues = existsSync(envPath) ? parseDotEnv(await readFile(envPath, "utf8")) : {};
  const mergedEnv = { ...envFileValues, ...env };
  const provider = String(data.model.provider ?? "openai").toLowerCase();
  if (provider === "deepseek" && mergedEnv.DEEPSEEK_API_KEY) data.model.api_key = mergedEnv.DEEPSEEK_API_KEY;
  else if (mergedEnv.OPENAI_API_KEY) data.model.api_key = mergedEnv.OPENAI_API_KEY;
  else if (mergedEnv.DEEPSEEK_API_KEY) data.model.api_key = mergedEnv.DEEPSEEK_API_KEY;
  if (mergedEnv.OPENAI_BASE_URL) data.model.base_url = mergedEnv.OPENAI_BASE_URL;
  if (mergedEnv.NANOROLE_MODEL) data.model.name = mergedEnv.NANOROLE_MODEL;
  if (mergedEnv.NANOROLE_TRACE_REQUESTS) data.logging.trace_requests = parseBoolean(mergedEnv.NANOROLE_TRACE_REQUESTS);

  if (flags.host) data.server.host = flags.host;
  if (flags.port !== undefined) data.server.port = flags.port;
  if (flags.debug !== undefined) data.logging.trace_requests = flags.debug;
  if (flags.model) data.model.name = flags.model;
  if (flags.baseUrl) data.model.base_url = flags.baseUrl;

  return {
    server: {
      host: String(data.server.host),
      port: Number(data.server.port)
    },
    model: {
      provider: String(data.model.provider),
      baseUrl: String(data.model.base_url),
      name: String(data.model.name),
      apiKey: data.model.api_key ? String(data.model.api_key) : undefined,
      reasoningEffort: data.model.reasoning_effort ? String(data.model.reasoning_effort) : undefined,
      extraBody: data.model.extra_body ?? {}
    },
    logging: {
      level: String(data.logging.level),
      traceRequests: Boolean(data.logging.trace_requests)
    },
    paths: {
      logsDir: resolveConfigPath(rootDir, data.paths.logs_dir),
      sessionsDir: resolveConfigPath(rootDir, data.paths.sessions_dir)
    }
  };
}

function deepMerge(target: Record<string, any>, source: Record<string, any>): void {
  for (const [key, value] of Object.entries(source)) {
    if (value && typeof value === "object" && !Array.isArray(value) && typeof target[key] === "object") {
      deepMerge(target[key], value as Record<string, any>);
    } else {
      target[key] = value;
    }
  }
}

function parseDotEnv(contents: string): Record<string, string> {
  const values: Record<string, string> = {};
  for (const line of contents.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const index = trimmed.indexOf("=");
    if (index === -1) continue;
    const key = trimmed.slice(0, index).trim();
    const raw = trimmed.slice(index + 1).trim();
    values[key] = raw.replace(/^['"]|['"]$/g, "");
  }
  return values;
}

function resolveConfigPath(rootDir: string, value: string): string {
  return isAbsolute(value) ? resolve(value) : resolve(rootDir, value);
}

function parseBoolean(value: string): boolean {
  return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
}
