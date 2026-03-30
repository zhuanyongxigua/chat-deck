export type AgentTool = "claude" | "codex" | "copilot";

export type AgentState = "idle" | "working" | "completed" | "error" | "blocked";

export type ChatRole = "user" | "assistant" | "system" | "error";

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: number;
}

export interface AgentRecord {
  id: string;
  name: string;
  tool: AgentTool;
  cwd: string;
  branch: string | null;
  sessionName: string;
  launchCommand: string[];
  runtimeFiles: string[];
  state: AgentState;
  unreadCount: number;
  awaitingResult: boolean;
  needsAttention: boolean;
  lastSummary: string;
  messages: ChatMessage[];
  createdAt: number;
}

export interface RouterResult {
  kind:
    | "empty"
    | "help"
    | "agents"
    | "create_agent"
    | "attach_agent"
    | "close_agent"
    | "agent_message"
    | "controller_message"
    | "invalid";
  target?: string;
  message?: string;
  tool?: AgentTool;
  cwd?: string;
  name?: string;
  launchCommand?: string[];
}

export interface TaskDonePayload {
  summary?: string;
  result?: string;
  next?: string;
}
