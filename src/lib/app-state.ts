import { mkdirSync, readFileSync, writeFileSync } from "node:fs";

import { appStateFilePath, chatDeckDir } from "./paths";
import type { AgentRecord, ChatMessage } from "./types";

export interface ViewState {
  draft: string;
  scrollTop: number;
}

export interface PersistedAppState {
  version: 1;
  agents: AgentRecord[];
  selectedAgentId: string | null;
  controllerMessages: ChatMessage[];
  sidebarVisible: boolean;
  sidebarWidth: number | null;
  viewStates: Record<string, ViewState>;
  inboxOffset: number;
}

function isChatMessage(value: unknown): value is ChatMessage {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as Partial<ChatMessage>;
  return (
    typeof candidate.id === "string" &&
    (candidate.role === "user" ||
      candidate.role === "assistant" ||
      candidate.role === "system" ||
      candidate.role === "error") &&
    typeof candidate.content === "string" &&
    typeof candidate.createdAt === "number"
  );
}

function isAgentRecord(value: unknown): value is AgentRecord {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as Partial<AgentRecord>;
  return (
    typeof candidate.id === "string" &&
    typeof candidate.name === "string" &&
    (candidate.tool === "claude" || candidate.tool === "codex") &&
    typeof candidate.cwd === "string" &&
    (typeof candidate.branch === "string" || candidate.branch === null) &&
    typeof candidate.sessionName === "string" &&
    Array.isArray(candidate.launchCommand) &&
    candidate.launchCommand.every((item) => typeof item === "string") &&
    Array.isArray(candidate.runtimeFiles) &&
    candidate.runtimeFiles.every((item) => typeof item === "string") &&
    (candidate.state === "idle" ||
      candidate.state === "working" ||
      candidate.state === "completed" ||
      candidate.state === "error" ||
      candidate.state === "blocked") &&
    typeof candidate.unreadCount === "number" &&
    typeof candidate.awaitingResult === "boolean" &&
    typeof candidate.needsAttention === "boolean" &&
    typeof candidate.lastSummary === "string" &&
    Array.isArray(candidate.messages) &&
    candidate.messages.every(isChatMessage) &&
    typeof candidate.createdAt === "number"
  );
}

function sanitizeViewStates(value: unknown): Record<string, ViewState> {
  const next: Record<string, ViewState> = { controller: { draft: "", scrollTop: 0 } };
  if (!value || typeof value !== "object") {
    return next;
  }

  for (const [key, view] of Object.entries(value)) {
    if (!view || typeof view !== "object") {
      continue;
    }
    const candidate = view as Partial<ViewState>;
    next[key] = {
      draft: typeof candidate.draft === "string" ? candidate.draft : "",
      scrollTop: typeof candidate.scrollTop === "number" ? candidate.scrollTop : 0,
    };
  }

  return next;
}

export function loadAppState(): PersistedAppState | null {
  try {
    const raw = JSON.parse(readFileSync(appStateFilePath(), "utf8")) as Partial<PersistedAppState>;
    if (raw.version !== 1) {
      return null;
    }

    const agents = Array.isArray(raw.agents) ? raw.agents.filter(isAgentRecord) : [];
    const controllerMessages = Array.isArray(raw.controllerMessages)
      ? raw.controllerMessages.filter(isChatMessage)
      : [];
    const selectedAgentId =
      typeof raw.selectedAgentId === "string" || raw.selectedAgentId === null ? raw.selectedAgentId : null;

    return {
      version: 1,
      agents,
      selectedAgentId,
      controllerMessages,
      sidebarVisible: typeof raw.sidebarVisible === "boolean" ? raw.sidebarVisible : true,
      sidebarWidth: typeof raw.sidebarWidth === "number" ? raw.sidebarWidth : null,
      viewStates: sanitizeViewStates(raw.viewStates),
      inboxOffset: typeof raw.inboxOffset === "number" ? raw.inboxOffset : 0,
    };
  } catch {
    return null;
  }
}

export function saveAppState(state: PersistedAppState): void {
  mkdirSync(chatDeckDir(), { recursive: true });
  writeFileSync(appStateFilePath(), `${JSON.stringify(state, null, 2)}\n`, "utf8");
}
