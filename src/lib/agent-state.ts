import type { AgentRecord } from "./types";

function hasAssistantResult(agent: AgentRecord): boolean {
  return agent.lastSummary.trim().length > 0 || agent.messages.some((message) => message.role === "assistant");
}

export function applyAgentSelection(
  agents: AgentRecord[],
  previousSelectedId: string | null,
  nextSelectedId: string | null,
): AgentRecord[] {
  return agents.map((agent) => {
    let next = agent;

    if (nextSelectedId && agent.id === nextSelectedId && agent.unreadCount !== 0) {
      next = { ...next, unreadCount: 0 };
    }

    if (previousSelectedId === nextSelectedId) {
      return next;
    }

    if (
      agent.state === "completed" &&
      (agent.id === previousSelectedId || agent.id === nextSelectedId)
    ) {
      next = {
        ...next,
        state: "idle",
      };
    }

    return next;
  });
}

export function applyAgentPaneExit(agent: AgentRecord, exitStatus: number | null): AgentRecord {
  if (exitStatus && exitStatus !== 0) {
    return {
      ...agent,
      state: "error",
      awaitingResult: false,
      needsAttention: true,
      statusDetail: "",
    };
  }

  if (hasAssistantResult(agent)) {
    return {
      ...agent,
      state: "completed",
      awaitingResult: false,
      needsAttention: false,
      statusDetail: "",
    };
  }

  return {
    ...agent,
    state: "error",
    awaitingResult: false,
    needsAttention: true,
    statusDetail: "",
  };
}
