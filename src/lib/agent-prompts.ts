import type { AgentTool } from "./types";

function normalizeSnapshot(snapshot: string): string {
  return snapshot.replace(/\r\n?/g, "\n").toLowerCase();
}

function includesAny(text: string, patterns: string[]): boolean {
  return patterns.some((pattern) => text.includes(pattern));
}

export function detectBlockedPrompt(tool: AgentTool, snapshot: string): string | null {
  const text = normalizeSnapshot(snapshot);

  if (tool === "codex" && includesAny(text, ["do you trust the contents of this directory?"])) {
    return "Codex is waiting for directory trust confirmation. Attach with Ctrl+T and continue once for this folder.";
  }

  if (tool === "claude" && includesAny(text, ["do you trust the files in this folder?", "yes, proceed"])) {
    return "Claude is waiting for workspace trust confirmation. Attach with Ctrl+T and choose Yes, proceed once for this folder.";
  }

  if (
    tool === "copilot" &&
    includesAny(text, [
      "confirm folder trust",
      "do you trust the files in this folder?",
      "yes, and remember this folder for future sessions",
    ])
  ) {
    return "Copilot is waiting for folder trust confirmation. Attach with Ctrl+T and confirm trust for this folder.";
  }

  return null;
}
