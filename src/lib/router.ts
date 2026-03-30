import { RouterResult, type AgentTool } from "./types";

const USER_CREATABLE_TOOLS: Record<string, AgentTool> = {
  claude: "claude",
  codex: "codex",
  copilot: "copilot",
};

function shellSplit(text: string): string[] {
  const tokens: string[] = [];
  let current = "";
  let quote: "'" | '"' | null = null;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quote) {
      if (char === quote) {
        quote = null;
      } else {
        current += char;
      }
      continue;
    }
    if (char === "'" || char === '"') {
      quote = char;
      continue;
    }
    if (/\s/.test(char)) {
      if (current) {
        tokens.push(current);
        current = "";
      }
      continue;
    }
    current += char;
  }

  if (current) {
    tokens.push(current);
  }
  return tokens;
}

export function parseUserInput(raw: string): RouterResult {
  const text = raw.trim();
  if (!text) {
    return { kind: "empty" };
  }

  if (text.startsWith("@")) {
    const body = text.slice(1).trim();
    const firstSpace = body.indexOf(" ");
    if (firstSpace === -1) {
      return { kind: "agent_message", target: body || undefined, message: "" };
    }
    return {
      kind: "agent_message",
      target: body.slice(0, firstSpace).trim() || undefined,
      message: body.slice(firstSpace + 1).trim(),
    };
  }

  if (!text.startsWith("/")) {
    return { kind: "controller_message", message: text };
  }

  const parts = shellSplit(text);
  if (!parts.length) {
    return { kind: "empty" };
  }

  const command = parts[0];
  if (command === "/help") {
    return { kind: "help" };
  }
  if (command === "/agents") {
    return { kind: "agents" };
  }
  if (command === "/attach") {
    if (parts.length > 2) {
      return { kind: "invalid", message: "Usage: /attach [agent-name]" };
    }
    const target = parts[1]?.replace(/^@/, "");
    return { kind: "attach_agent", target: target || undefined };
  }
  if (command === "/close") {
    if (parts.length > 2) {
      return { kind: "invalid", message: "Usage: /close [agent-name]" };
    }
    const target = parts[1]?.replace(/^@/, "");
    return { kind: "close_agent", target: target || undefined };
  }
  if (command === "/new") {
    if (parts.length < 4) {
      return {
        kind: "invalid",
        message: "Usage: /new <codex|claude|copilot> <name> <cwd> [client args...]",
      };
    }

    const toolToken = parts[1].toLowerCase();
    const tool = USER_CREATABLE_TOOLS[toolToken];
    if (!tool) {
      return {
        kind: "invalid",
        message: `Unsupported client: ${toolToken}. Use codex, claude, or copilot.`,
      };
    }

    let launchCommand: string[] | undefined;
    const launchArgs = [...parts.slice(4)];
    if (launchArgs[0] === "--") {
      launchArgs.shift();
    }
    if (launchArgs[0]?.toLowerCase() === toolToken) {
      launchArgs.shift();
    }
    if (launchArgs.length) {
      launchCommand = [toolToken, ...launchArgs];
    }

    return {
      kind: "create_agent",
      tool,
      name: parts[2],
      cwd: parts[3],
      launchCommand,
    };
  }

  return { kind: "invalid", message: `Unknown command: ${command}` };
}
