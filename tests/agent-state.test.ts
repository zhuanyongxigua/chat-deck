import { describe, expect, test } from "bun:test";

import { applyAgentPaneExit, applyAgentSelection } from "../src/lib/agent-state";
import type { AgentRecord } from "../src/lib/types";

function makeAgent(overrides: Partial<AgentRecord>): AgentRecord {
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
    statusDetail: "",
    lastSummary: "",
    messages: [],
    createdAt: 0,
    ...overrides,
  };
}

describe("applyAgentSelection", () => {
  test("consumes ready state when selecting a completed target session", () => {
    const agents = [
      makeAgent({ id: "a", name: "a" }),
      makeAgent({ id: "b", name: "b", state: "completed", unreadCount: 2 }),
    ];

    const next = applyAgentSelection(agents, "a", "b");

    expect(next[1]?.state).toBe("idle");
    expect(next[1]?.unreadCount).toBe(0);
  });

  test("consumes ready state when leaving a completed active session", () => {
    const agents = [
      makeAgent({ id: "a", name: "a", state: "completed" }),
      makeAgent({ id: "b", name: "b" }),
    ];

    const next = applyAgentSelection(agents, "a", "b");

    expect(next[0]?.state).toBe("idle");
    expect(next[1]?.state).toBe("idle");
  });

  test("does not consume ready state when selection does not change", () => {
    const agents = [makeAgent({ id: "a", name: "a", state: "completed", unreadCount: 1 })];

    const next = applyAgentSelection(agents, "a", "a");

    expect(next[0]?.state).toBe("completed");
    expect(next[0]?.unreadCount).toBe(0);
  });
});

describe("applyAgentPaneExit", () => {
  test("keeps a clean exit with assistant output as completed", () => {
    const next = applyAgentPaneExit(
      makeAgent({
        state: "working",
        awaitingResult: true,
        lastSummary: "Finished the task.",
      }),
      0,
    );

    expect(next.state).toBe("completed");
    expect(next.awaitingResult).toBe(false);
    expect(next.needsAttention).toBe(false);
  });

  test("treats a clean exit without assistant output as an error", () => {
    const next = applyAgentPaneExit(
      makeAgent({
        state: "working",
        awaitingResult: true,
        messages: [{ id: "m1", role: "user", content: "hello", createdAt: 0 }],
      }),
      0,
    );

    expect(next.state).toBe("error");
    expect(next.awaitingResult).toBe(false);
    expect(next.needsAttention).toBe(true);
  });

  test("treats a non-zero exit status as an error", () => {
    const next = applyAgentPaneExit(makeAgent({ state: "working", awaitingResult: true }), 2);

    expect(next.state).toBe("error");
    expect(next.awaitingResult).toBe(false);
    expect(next.needsAttention).toBe(true);
  });
});
