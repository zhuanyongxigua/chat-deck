import { describe, expect, test, beforeEach, afterEach } from "bun:test";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

import { appStateFilePath } from "../src/lib/paths";
import { loadAppState, saveAppState, type PersistedAppState } from "../src/lib/app-state";
import type { AgentRecord, ChatMessage } from "../src/lib/types";

function makeMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "message-1",
    role: "system",
    content: "hello",
    createdAt: 0,
    ...overrides,
  };
}

function makeAgent(overrides: Partial<AgentRecord> = {}): AgentRecord {
  return {
    id: "agent-1",
    name: "agent-1",
    tool: "codex",
    cwd: "/tmp/demo",
    branch: null,
    sessionName: "chatdeck-codex-agent-1",
    launchCommand: ["codex"],
    runtimeFiles: [],
    state: "idle",
    unreadCount: 0,
    awaitingResult: false,
    needsAttention: false,
    lastSummary: "",
    messages: [makeMessage()],
    createdAt: 0,
    ...overrides,
  };
}

describe("app state storage", () => {
  const previousHome = process.env.CHAT_DECK_HOME;
  let tempHome = "";

  beforeEach(() => {
    tempHome = mkdtempSync(join(tmpdir(), "chat-deck-state-"));
    process.env.CHAT_DECK_HOME = tempHome;
  });

  afterEach(() => {
    rmSync(tempHome, { recursive: true, force: true });
    if (previousHome === undefined) {
      delete process.env.CHAT_DECK_HOME;
    } else {
      process.env.CHAT_DECK_HOME = previousHome;
    }
  });

  test("returns null when no state file exists", () => {
    expect(loadAppState()).toBeNull();
  });

  test("persists and reloads app state under the chat-deck directory", () => {
    const state: PersistedAppState = {
      version: 1,
      agents: [makeAgent({ state: "completed", unreadCount: 2 })],
      selectedAgentId: "agent-1",
      controllerMessages: [makeMessage({ id: "controller-1", content: "Commands..." })],
      sidebarVisible: false,
      viewStates: {
        controller: { draft: "controller draft", scrollTop: 3 },
        "agent-1": { draft: "agent draft", scrollTop: 12 },
      },
      inboxOffset: 128,
    };

    saveAppState(state);

    expect(existsSync(appStateFilePath())).toBe(true);
    expect(JSON.parse(readFileSync(appStateFilePath(), "utf8"))).toMatchObject(state);
    expect(loadAppState()).toEqual(state);
  });

  test("sanitizes malformed state entries while preserving valid ones", () => {
    saveAppState({
      version: 1,
      agents: [makeAgent()],
      selectedAgentId: "agent-1",
      controllerMessages: [makeMessage()],
      sidebarVisible: true,
      viewStates: { controller: { draft: "", scrollTop: 0 } },
      inboxOffset: 0,
    });

    const raw = JSON.parse(readFileSync(appStateFilePath(), "utf8")) as Record<string, unknown>;
    raw.agents = [{ ...makeAgent(), messages: [{ nope: true }] }, makeAgent({ id: "agent-2", name: "agent-2" })];
    raw.controllerMessages = [{ bad: true }, makeMessage({ id: "controller-2" })];
    raw.viewStates = {
      controller: { draft: 42, scrollTop: "bad" },
      "agent-2": { draft: "saved", scrollTop: 8 },
    };
    writeFileSync(appStateFilePath(), `${JSON.stringify(raw, null, 2)}\n`, "utf8");

    expect(loadAppState()).toEqual({
      version: 1,
      agents: [makeAgent({ id: "agent-2", name: "agent-2" })],
      selectedAgentId: "agent-1",
      controllerMessages: [makeMessage({ id: "controller-2" })],
      sidebarVisible: true,
      viewStates: {
        controller: { draft: "", scrollTop: 0 },
        "agent-2": { draft: "saved", scrollTop: 8 },
      },
      inboxOffset: 0,
    });
  });
});
