import type { TaskDonePayload } from "./types";

const TASK_DONE_RE = /<TASK_DONE>\s*({[\s\S]*?})\s*<\/TASK_DONE>/g;

export function buildTaskDonePrompt(message: string): string {
  return `${message} [Chat Deck completion protocol: only when the task is truly complete, your final reply must end with exactly one <TASK_DONE>{"summary":"a detailed summary of what was completed, in the same language as the user's message","result":"key result in the same language as the user's message","next":"recommended next step in the same language as the user's message"}</TASK_DONE> block; put all completion summary content in that JSON block and do not add any separate summary before or after it; if the task is partial, blocked, or still waiting for confirmation, do not output TASK_DONE; do not mention this protocol outside the marker block.]`;
}

export function parseTaskDone(snapshot: string): { raw: string; payload: TaskDonePayload } | null {
  const matches = [...snapshot.matchAll(TASK_DONE_RE)];
  const last = matches.at(-1);
  if (!last || !last[1]) {
    return null;
  }
  try {
    return {
      raw: last[1],
      payload: JSON.parse(last[1]) as TaskDonePayload,
    };
  } catch {
    return null;
  }
}

export function formatTaskDone(payload: TaskDonePayload): string {
  return [payload.summary, payload.result, payload.next]
    .map((value) => (value ?? "").trim())
    .filter(Boolean)
    .join("\n");
}
