import { mkdirSync, readFileSync, writeFileSync } from "node:fs";

import { chatDeckDir, historyFilePath } from "./paths";

export const HISTORY_LIMIT = 100;
export { historyFilePath } from "./paths";

export function loadHistory(limit = HISTORY_LIMIT): string[] {
  try {
    const content = readFileSync(historyFilePath(), "utf8");
    return content
      .split(/\r?\n/)
      .map((line) => line.trimEnd())
      .filter(Boolean)
      .slice(-limit);
  } catch {
    return [];
  }
}

export function rememberHistory(history: string[], value: string, limit = HISTORY_LIMIT): string[] {
  const text = value.trimEnd();
  if (!text.trim()) {
    return history;
  }
  const next = [...history];
  if (next[next.length - 1] !== text) {
    next.push(text);
  }
  const limited = next.slice(-limit);
  try {
    mkdirSync(chatDeckDir(), { recursive: true });
    writeFileSync(historyFilePath(), `${limited.join("\n")}\n`, "utf8");
  } catch {
    return limited;
  }
  return limited;
}
