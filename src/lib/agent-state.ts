import type { AgentRecord } from "./types";

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
