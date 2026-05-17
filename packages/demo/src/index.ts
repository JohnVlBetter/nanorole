import { resolve } from "node:path";

import { createDemoServer } from "./server.js";

const host = process.env.NANOROLE_DEMO_HOST ?? "127.0.0.1";
const port = Number(process.env.NANOROLE_DEMO_PORT ?? "3000");
const runtimeUrl = process.env.NANOROLE_RUNTIME_URL ?? "http://127.0.0.1:8765";
const projectRoot = resolve(process.env.NANOROLE_PROJECT_ROOT ?? process.cwd());

const server = createDemoServer({ projectRoot, runtimeUrl });
server.listen(port, host, () => {
  console.log(`Nanorole demo: http://${host}:${port}`);
  console.log(`Nanorole chat: http://${host}:${port}/chat`);
  console.log(`Nanorole logs: http://${host}:${port}/logs`);
  console.log(`Nanorole core: ${runtimeUrl}`);
});
