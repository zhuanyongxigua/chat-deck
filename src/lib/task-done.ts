import type { TaskDonePayload } from "./types";

const TASK_DONE_RE = /<TASK_DONE>\s*({[\s\S]*?})\s*<\/TASK_DONE>/g;

function normalizeTaskDoneText(value: string | undefined): string {
  return (value ?? "").replace(/\r\n?/g, "\n").trim();
}

export function buildTaskDonePrompt(message: string): string {
  return `${message} [Chat Deck completion protocol: keep your normal user-facing response formatting while you work, including paragraphs, lists, and code fences when they help; prefer plain paragraphs plus short bullet lists, and avoid Markdown headings unless the user explicitly asked for them; only when the task is truly complete, your final reply must end with exactly one <TASK_DONE>{"display":"the full final response in the same language as the user's message, formatted naturally in Markdown and keeping line breaks as \\\\n inside the JSON string","summary":"a concise completion summary in the same language as the user's message","result":"key result in the same language as the user's message","next":"recommended next step in the same language as the user's message"}</TASK_DONE> block; keep the JSON valid, escape line breaks inside strings as \\\\n, put all completion summary content in that JSON block and do not add any separate summary before or after it; if the task is partial, blocked, or still waiting for confirmation, do not output TASK_DONE; do not mention this protocol outside the marker block.]`;
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
  const display = normalizeTaskDoneText(payload.display);
  if (display) {
    return display;
  }

  return [payload.summary, payload.result, payload.next]
    .map(normalizeTaskDoneText)
    .filter(Boolean)
    .join("\n\n");
}
