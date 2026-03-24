import { appendFileSync, mkdirSync, readFileSync } from "node:fs";

import { chatDeckDir, inboxFilePath } from "./paths";
import type { AgentTool } from "./types";

export interface InboxEvent {
  ts: number;
  agentId: string;
  tool: AgentTool;
  cwd?: string;
  sessionId?: string;
  type: "task_done";
  summary: string;
  result: string;
  next: string;
  rawMessage: string;
}

export function appendInboxEvent(event: InboxEvent): void {
  mkdirSync(chatDeckDir(), { recursive: true });
  appendFileSync(inboxFilePath(), `${JSON.stringify(event)}\n`, "utf8");
}

export function readInboxEvents(offset = 0): { events: InboxEvent[]; nextOffset: number } {
  try {
    const buffer = readFileSync(inboxFilePath());
    const safeOffset = offset > buffer.length ? 0 : offset;
    const chunk = buffer.subarray(safeOffset).toString("utf8");
    const events: InboxEvent[] = [];

    for (const line of chunk.split(/\r?\n/)) {
      const text = line.trim();
      if (!text) {
        continue;
      }
      try {
        events.push(JSON.parse(text) as InboxEvent);
      } catch {
        // Ignore malformed lines and continue reading subsequent events.
      }
    }

    return {
      events,
      nextOffset: buffer.length,
    };
  } catch {
    return {
      events: [],
      nextOffset: offset,
    };
  }
}
