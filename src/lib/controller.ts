import { RouterResult, type AgentTool } from "./types";

const CREATE_KEYWORDS = [
  "create",
  "start",
  "spawn",
  "launch",
  "new agent",
  "new session",
  "创建",
  "新建",
  "启动",
  "开一个",
  "开启",
];

const NAME_PATTERNS = [
  /\b(?:named|name)\s+(?<name>[A-Za-z0-9_-]+)\b/i,
  /(?:叫|名为)(?<name>[A-Za-z0-9_-]+)/,
];

const PATH_PATTERN = /(?<path>(?:~|\/)[^\s,，。；;]+)/;

function detectToolType(text: string): AgentTool | null {
  const lowered = text.toLowerCase();
  if (lowered.includes("claude code") || lowered.includes("claude")) {
    return "claude";
  }
  if (lowered.includes("codex")) {
    return "codex";
  }
  return null;
}

function detectName(text: string): string | null {
  for (const pattern of NAME_PATTERNS) {
    const match = pattern.exec(text);
    if (match?.groups?.name) {
      return match.groups.name;
    }
  }
  return null;
}

function detectPath(text: string): string | null {
  const match = PATH_PATTERN.exec(text);
  return match?.groups?.path ?? null;
}

function deriveName(tool: AgentTool, cwd: string): string {
  const base = cwd.split("/").filter(Boolean).pop() || "workspace";
  const normalized = base.replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase() || "workspace";
  return `${normalized}-${tool}`;
}

export function interpretControllerMessage(text: string): RouterResult | null {
  if (!text.trim()) {
    return null;
  }
  const lowered = text.toLowerCase();
  if (!CREATE_KEYWORDS.some((keyword) => lowered.includes(keyword))) {
    return null;
  }
  const tool = detectToolType(text);
  const cwd = detectPath(text);
  if (!tool || !cwd) {
    return null;
  }

  return {
    kind: "create_agent",
    tool,
    cwd,
    name: detectName(text) || deriveName(tool, cwd),
    message: text,
  };
}
