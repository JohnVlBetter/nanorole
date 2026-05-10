export interface ParsedCliArgs {
  command: "chat";
  roleDir: string;
  flags: {
    host?: string;
    port?: number;
    debug?: boolean;
  };
}

export function parseCliArgs(argv: string[]): ParsedCliArgs {
  const [command, roleDir, ...rest] = argv;
  if (command !== "chat") {
    throw new Error("expected command: chat");
  }
  if (!roleDir) {
    throw new Error("missing role directory");
  }

  const flags: ParsedCliArgs["flags"] = {};
  for (let index = 0; index < rest.length; index += 1) {
    const token = rest[index];
    if (token === "--debug") {
      flags.debug = true;
      continue;
    }
    if (token === "--port") {
      const value = rest[index + 1];
      if (!value) throw new Error("--port requires a value");
      flags.port = Number(value);
      index += 1;
      continue;
    }
    if (token === "--host") {
      const value = rest[index + 1];
      if (!value) throw new Error("--host requires a value");
      flags.host = value;
      index += 1;
      continue;
    }
    throw new Error(`unknown option: ${token}`);
  }

  return { command, roleDir, flags };
}

