import { spawn } from "node:child_process";
import { join } from "node:path";

export interface HealthResult {
  ok: boolean;
  service?: string;
}

export interface SpawnRuntimeOptions {
  host: string;
  port: number;
  projectRoot: string;
  traceRequests?: boolean;
}

export interface EnsureRuntimeServerOptions extends SpawnRuntimeOptions {
  healthCheck?: (url: string) => Promise<HealthResult>;
  spawnRuntime?: (options: SpawnRuntimeOptions) => Promise<void>;
}

export interface RuntimeServer {
  url: string;
  reused: boolean;
}

export async function ensureRuntimeServer(options: EnsureRuntimeServerOptions): Promise<RuntimeServer> {
  const url = `http://${options.host}:${options.port}`;
  const healthCheck = options.healthCheck ?? defaultHealthCheck;
  const spawnRuntime = options.spawnRuntime ?? defaultSpawnRuntime;
  const health = await healthCheck(url);

  if (health.ok && health.service === "nanorole-runtime") {
    return { url, reused: true };
  }
  if (health.ok) {
    throw new Error(`port ${options.port} is already in use by an unknown service`);
  }

  await spawnRuntime({
    host: options.host,
    port: options.port,
    projectRoot: options.projectRoot,
    traceRequests: options.traceRequests
  });
  return { url, reused: false };
}

export async function defaultHealthCheck(url: string): Promise<HealthResult> {
  try {
    const response = await fetch(`${url}/health`);
    if (!response.ok) return { ok: false };
    const data = (await response.json()) as { service?: string };
    return { ok: true, service: data.service };
  } catch {
    return { ok: false };
  }
}

export async function defaultSpawnRuntime(options: SpawnRuntimeOptions): Promise<void> {
  const runtimeDir = join(options.projectRoot, "python", "nanorole_runtime");
  const child = spawn(
    "uv",
    ["run", "uvicorn", "nanorole_runtime.server:app", "--host", options.host, "--port", String(options.port)],
    {
      cwd: runtimeDir,
      detached: true,
      env: {
        ...process.env,
        NANOROLE_PROJECT_ROOT: options.projectRoot,
        NANOROLE_TRACE_REQUESTS: options.traceRequests ? "true" : process.env.NANOROLE_TRACE_REQUESTS
      },
      stdio: "ignore",
      windowsHide: true
    }
  );
  child.unref();
  await waitForRuntime(`http://${options.host}:${options.port}`);
}

async function waitForRuntime(url: string): Promise<void> {
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    const health = await defaultHealthCheck(url);
    if (health.ok && health.service === "nanorole-runtime") return;
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw new Error(`runtime did not become healthy at ${url}`);
}
