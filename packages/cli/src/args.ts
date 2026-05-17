export type ParsedCliArgs =
  | {
      command: "chat";
      roleDir: string;
      flags: RuntimeFlags;
    }
  | {
      command: "logs";
      flags: RuntimeFlags;
    };

export interface RuntimeFlags {
  host?: string;
  port?: number;
  debug?: boolean;
}

export function parseCliArgs(argv: string[]): ParsedCliArgs {
  const [command, ...rest] = argv;
  if (command === "chat") {
    const [roleDir, ...flagTokens] = rest;
    if (!roleDir) {
      throw new Error("missing role directory");
    }
    return { command, roleDir, flags: parseFlags(flagTokens) };
  }
  if (command === "logs") {
    return { command, flags: parseFlags(rest) };
  }
  throw new Error("expected command: chat or logs");
}

function parseFlags(tokens: string[]): RuntimeFlags {
  const flags: RuntimeFlags = {};
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (token === "--debug") {
      flags.debug = true;
      continue;
    }
    if (token === "--port") {
      const value = tokens[index + 1];
      if (!value) throw new Error("--port requires a value");
      flags.port = Number(value);
      index += 1;
      continue;
    }
    if (token === "--host") {
      const value = tokens[index + 1];
      if (!value) throw new Error("--host requires a value");
      flags.host = value;
      index += 1;
      continue;
    }
    throw new Error(`unknown option: ${token}`);
  }

  return flags;
}
