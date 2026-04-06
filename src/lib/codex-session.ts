import { existsSync, readFileSync, readdirSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export interface CodexPromptSubmission {
  sessionId: string;
  tsMs: number;
}

function codexHomeDir(): string {
  return join(process.env.HOME || homedir(), ".codex");
}

function codexHistoryPath(): string {
  return join(codexHomeDir(), "history.jsonl");
}

function codexSessionsDir(): string {
  return join(codexHomeDir(), "sessions");
}

function findCodexSessionRolloutPath(sessionId: string): string {
  const sessionsRoot = codexSessionsDir();
  if (!existsSync(sessionsRoot)) {
    return "";
  }

  const years = readdirSync(sessionsRoot, { withFileTypes: true });
  for (const yearEntry of years) {
    if (!yearEntry.isDirectory()) {
      continue;
    }
    const yearPath = join(sessionsRoot, yearEntry.name);
    const months = readdirSync(yearPath, { withFileTypes: true });
    for (const monthEntry of months) {
      if (!monthEntry.isDirectory()) {
        continue;
      }
      const monthPath = join(yearPath, monthEntry.name);
      const days = readdirSync(monthPath, { withFileTypes: true });
      for (const dayEntry of days) {
        if (!dayEntry.isDirectory()) {
          continue;
        }
        const dayPath = join(monthPath, dayEntry.name);
        const files = readdirSync(dayPath, { withFileTypes: true });
        for (const fileEntry of files) {
          if (!fileEntry.isFile()) {
            continue;
          }
          if (fileEntry.name.endsWith(`${sessionId}.jsonl`)) {
            return join(dayPath, fileEntry.name);
          }
        }
      }
    }
  }

  return "";
}

function normalizeCwd(cwd: string | undefined): string {
  if (!cwd) {
    return "";
  }

  try {
    return existsSync(cwd) ? realpathSync(cwd) : cwd;
  } catch {
    return cwd;
  }
}

function rolloutCwdMatches(sessionId: string, cwd: string): boolean {
  const rolloutPath = findCodexSessionRolloutPath(sessionId);
  if (!rolloutPath) {
    return false;
  }

  try {
    const firstLine = readFileSync(rolloutPath, "utf8").split(/\r?\n/, 1)[0]?.trim();
    if (!firstLine) {
      return false;
    }
    const parsed = JSON.parse(firstLine) as { payload?: { cwd?: string } };
    return normalizeCwd(parsed.payload?.cwd) === normalizeCwd(cwd);
  } catch {
    return false;
  }
}

export function findCodexPromptSubmission(cwd: string, message: string, earliestTsMs: number): CodexPromptSubmission | null {
  const historyPath = codexHistoryPath();
  if (!existsSync(historyPath)) {
    return null;
  }

  try {
    const lines = readFileSync(historyPath, "utf8").split(/\r?\n/);
    for (let index = lines.length - 1; index >= 0; index -= 1) {
      const line = lines[index]?.trim();
      if (!line) {
        continue;
      }

      let parsed: { session_id?: string; ts?: number; text?: string };
      try {
        parsed = JSON.parse(line) as { session_id?: string; ts?: number; text?: string };
      } catch {
        continue;
      }

      const tsMs = typeof parsed.ts === "number" ? parsed.ts * 1000 : 0;
      if (tsMs < earliestTsMs) {
        break;
      }
      if (parsed.text !== message || !parsed.session_id) {
        continue;
      }
      if (!rolloutCwdMatches(parsed.session_id, cwd)) {
        continue;
      }

      return {
        sessionId: parsed.session_id,
        tsMs,
      };
    }
  } catch {
    return null;
  }

  return null;
}

export async function waitForCodexPromptSubmission(
  cwd: string,
  message: string,
  earliestTsMs: number,
  options: { timeoutMs?: number; pollMs?: number } = {},
): Promise<CodexPromptSubmission | null> {
  const timeoutMs = options.timeoutMs ?? 2_000;
  const pollMs = options.pollMs ?? 120;
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const submission = findCodexPromptSubmission(cwd, message, earliestTsMs);
    if (submission) {
      return submission;
    }
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }

  return null;
}
