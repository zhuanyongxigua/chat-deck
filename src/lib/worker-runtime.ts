import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { appendInboxEvent, type InboxEvent } from "./inbox";
import { agentRuntimeDir } from "./paths";
import { parseTaskDone } from "./task-done";
import type { AgentTool } from "./types";

const PROJECT_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

function shellEscape(value: string): string {
  return `'${value.replace(/'/g, `'\"'\"'`)}'`;
}

function callbackCommandArgs(tool: AgentTool, agentId: string): string[] {
  return [process.execPath, resolve(PROJECT_ROOT, "bin/chat-deck"), "publish-done", tool, agentId];
}

function callbackCommandString(tool: AgentTool, agentId: string): string {
  return callbackCommandArgs(tool, agentId).map(shellEscape).join(" ");
}

function firstString(payload: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }
  return "";
}

async function readStdin(): Promise<string> {
  if (process.stdin.isTTY) {
    return "";
  }
  let text = "";
  for await (const chunk of process.stdin) {
    text += chunk.toString();
  }
  return text;
}

export interface PreparedLaunchCommand {
  command: string[];
  runtimeFiles: string[];
}

export function prepareWorkerLaunchCommand(
  tool: AgentTool,
  agentId: string,
  launchCommand?: string[],
): PreparedLaunchCommand {
  const base = launchCommand?.length ? [...launchCommand] : [tool];

  if (tool === "codex") {
    return {
      command: [...base, "-c", `notify=${JSON.stringify(callbackCommandArgs(tool, agentId))}`],
      runtimeFiles: [],
    };
  }

  const runtimeDir = agentRuntimeDir(agentId);
  mkdirSync(runtimeDir, { recursive: true });
  const settingsPath = join(runtimeDir, "claude-settings.json");

  writeFileSync(
    settingsPath,
    JSON.stringify(
      {
        hooks: {
          Stop: [
            {
              hooks: [
                {
                  type: "command",
                  command: callbackCommandString(tool, agentId),
                },
              ],
            },
          ],
        },
      },
      null,
      2,
    ),
    "utf8",
  );

  return {
    command: [...base, "--settings", settingsPath],
    runtimeFiles: [settingsPath],
  };
}

export function cleanupRuntimeFiles(files: string[]): void {
  for (const file of files) {
    rmSync(file, { force: true });
  }
}

export function publishDoneEventFromPayload(
  tool: AgentTool,
  agentId: string,
  payload: Record<string, unknown>,
): InboxEvent | null {
  const rawMessage = firstString(payload, [
    "last_assistant_message",
    "last-assistant-message",
    "lastAssistantMessage",
    "message",
  ]);
  const parsed = parseTaskDone(rawMessage);
  if (!parsed) {
    return null;
  }

  return {
    ts: Date.now(),
    agentId,
    tool,
    cwd: firstString(payload, ["cwd"]),
    sessionId: firstString(payload, ["session_id", "session-id", "thread-id", "thread_id"]),
    type: "task_done",
    summary: parsed.payload.summary?.trim() ?? "",
    result: parsed.payload.result?.trim() ?? "",
    next: parsed.payload.next?.trim() ?? "",
    rawMessage,
  };
}

export async function publishDoneFromArgs(args: string[]): Promise<number> {
  const [toolArg, agentId, maybePayload] = args;
  if ((toolArg !== "claude" && toolArg !== "codex") || !agentId) {
    console.error("Usage: chat-deck publish-done <claude|codex> <agent-id> [payload-json]");
    return 1;
  }

  const stdinPayload = await readStdin();
  const rawPayload = (maybePayload?.trim() || stdinPayload.trim()) ?? "";
  if (!rawPayload) {
    return 0;
  }

  try {
    const payload = JSON.parse(rawPayload) as Record<string, unknown>;
    const event = publishDoneEventFromPayload(toolArg, agentId, payload);
    if (event) {
      appendInboxEvent(event);
    }
    return 0;
  } catch (error) {
    console.error((error as Error).message);
    return 1;
  }
}
