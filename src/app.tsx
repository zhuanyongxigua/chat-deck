import { useEffect, useMemo, useRef, useState } from "react";
import { useKeyboard, useRenderer, useTerminalDimensions } from "@opentui/react";
import { CliRenderEvents, TextAttributes, type KeyEvent, type MouseEvent } from "@opentui/core";
import { randomUUID } from "node:crypto";
import { existsSync, statSync } from "node:fs";
import { resolve } from "node:path";

import { applyAgentSelection } from "./lib/agent-state";
import { loadAppState, saveAppState, type PersistedAppState, type ViewState } from "./lib/app-state";
import { interpretControllerMessage } from "./lib/controller";
import { HISTORY_LIMIT, loadHistory, rememberHistory } from "./lib/history";
import { readInboxEvents } from "./lib/inbox";
import { parseUserInput } from "./lib/router";
import { buildTaskDonePrompt, formatTaskDone } from "./lib/task-done";
import {
  attachTmuxSession,
  commandExists,
  createTmuxSession,
  destroyTmuxSession,
  detectGitBranch,
  getTmuxPaneState,
  isTmuxAvailable,
  sendTextToTmux,
} from "./lib/tmux";
import { cleanupRuntimeFiles, prepareWorkerLaunchCommand } from "./lib/worker-runtime";
import type { AgentRecord, AgentState, AgentTool, ChatMessage, RouterResult } from "./lib/types";

const SPINNER_FRAMES = ["◐", "◓", "◑", "◒"];
const TOP_BAR_BACKGROUND = "#111821";
const MESSAGE_SCROLLBOX_ID = "message-scrollbox";
const COMMAND_SPECS: Array<{ command: string; description: string }> = [
  { command: "/help", description: "Show available commands" },
  { command: "/agents", description: "List current agents" },
  { command: "/new", description: "Create a Claude or Codex agent" },
  { command: "/attach", description: "Open the selected agent tmux session" },
  { command: "/close", description: "Close the selected or named agent" },
];

function createMessage(role: ChatMessage["role"], content: string): ChatMessage {
  return {
    id: randomUUID(),
    role,
    content,
    createdAt: Date.now(),
  };
}

function clientLabel(tool: AgentTool): string {
  return tool === "claude" ? "Claude Code" : "Codex";
}

function stateLabel(state: AgentState): string {
  if (state === "completed") {
    return "ready";
  }
  return state;
}

function stateToken(state: AgentState): string {
  switch (state) {
    case "idle":
      return "I";
    case "working":
      return "W";
    case "completed":
      return "C";
    case "blocked":
      return "B";
    case "error":
      return "E";
    default:
      return "?";
  }
}

function stateColor(state: AgentState): string {
  switch (state) {
    case "completed":
      return "#7FE5B2";
    case "idle":
      return "#F2D98C";
    case "error":
      return "#FF6F6F";
    case "working":
      return "#7FE5B2";
    case "blocked":
      return "#FFB56B";
    default:
      return "#B3BFCC";
  }
}

function borderColor(active: boolean): string {
  return active ? "#3E7F5D" : "#7FB3FF";
}

function placeholderStatusSymbol(state: AgentState, tick: number): string {
  if (state === "completed") {
    return "●";
  }
  if (state === "idle") {
    return "●";
  }
  if (state === "error") {
    return "●";
  }
  if (state === "working") {
    return SPINNER_FRAMES[tick % SPINNER_FRAMES.length]!;
  }
  if (state === "blocked") {
    return "●";
  }
  return "●";
}

function initialControllerMessages(): ChatMessage[] {
  return [
    createMessage(
      "system",
      "Commands: /help, /agents, /new <codex|claude> <name> <cwd> [client args...], /attach [agent-name], /close [agent-name], @agent-name <message>",
    ),
    createMessage("system", "The sidebar keeps all agent status visible without opening extra panes."),
    createMessage("system", "Claude Code and Codex workers run inside tmux sessions."),
    createMessage("system", "Use Ctrl+1..9 to select agents, Ctrl+T to attach, Ctrl+X to close, and Esc to return to controller."),
  ];
}

function normalizeCwd(input: string): string {
  if (input.startsWith("~")) {
    return input.replace(/^~/, process.env.HOME ?? "");
  }
  return input;
}

function makeSessionName(tool: AgentTool, name: string, id: string): string {
  const base = `chatdeck-${tool}-${name}-${id}`.replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  return base.slice(0, 64) || `chatdeck-${id}`;
}

function looksLikeError(text: string): boolean {
  const lowered = text.toLowerCase();
  return [
    "error",
    "failed",
    "unknown",
    "does not exist",
    "already exists",
    "required",
    "invalid",
    "unsupported",
    "not installed",
  ].some((marker) => lowered.includes(marker));
}

function commandFooter(matches: Array<{ command: string; description: string }>, index: number): string {
  const active = matches[index] ?? matches[0];
  const commands = matches
    .map((item, itemIndex) => (itemIndex === index ? `[${item.command}]` : item.command))
    .join("  ");
  return `Commands: ${commands}\n${active?.description ?? ""}  Tab to autocomplete`;
}

function messageViewKey(agentId: string | null): string {
  return agentId ?? "controller";
}

function clampSidebarWidth(width: number, terminalWidth: number): number {
  const minSidebarWidth = 24;
  const minContentWidth = 48;
  const maxSidebarWidth = Math.max(minSidebarWidth, terminalWidth - minContentWidth);
  return Math.max(minSidebarWidth, Math.min(width, maxSidebarWidth));
}

export function ChatDeckApp() {
  const initialAppStateRef = useRef<PersistedAppState | null>(null);
  if (initialAppStateRef.current === null) {
    initialAppStateRef.current = loadAppState();
  }
  const initialAppState = initialAppStateRef.current;
  const renderer = useRenderer();
  const { width, height } = useTerminalDimensions();
  const [agents, setAgents] = useState<AgentRecord[]>(() => initialAppState?.agents ?? []);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(() => initialAppState?.selectedAgentId ?? null);
  const [controllerMessages, setControllerMessages] = useState<ChatMessage[]>(
    () => initialAppState?.controllerMessages ?? initialControllerMessages(),
  );
  const [inputValue, setInputValue] = useState(() => {
    const selected = initialAppState?.selectedAgentId ?? null;
    const viewKey = messageViewKey(selected);
    return initialAppState?.viewStates[viewKey]?.draft ?? "";
  });
  const [footerText, setFooterText] = useState("");
  const [footerError, setFooterError] = useState(false);
  const [sidebarVisible, setSidebarVisible] = useState(() => initialAppState?.sidebarVisible ?? true);
  const [sidebarWidthOverride, setSidebarWidthOverride] = useState<number | null>(() => initialAppState?.sidebarWidth ?? null);
  const [dividerActive, setDividerActive] = useState(false);
  const [animationTick, setAnimationTick] = useState(0);
  const [history, setHistory] = useState<string[]>(() => loadHistory(HISTORY_LIMIT));
  const [historyIndex, setHistoryIndex] = useState<number | null>(null);
  const [historyDraft, setHistoryDraft] = useState("");
  const [commandIndex, setCommandIndex] = useState(0);

  const agentsRef = useRef(agents);
  const selectedAgentIdRef = useRef(selectedAgentId);
  const inputValueRef = useRef(inputValue);
  const historyRef = useRef(history);
  const inboxOffsetRef = useRef(initialAppState?.inboxOffset ?? 0);
  const clipboardWarningShownRef = useRef(false);
  const controllerMessagesRef = useRef(controllerMessages);
  const sidebarVisibleRef = useRef(sidebarVisible);
  const sidebarWidthRef = useRef(sidebarWidthOverride);
  const dividerDragRef = useRef<{ startX: number; startWidth: number } | null>(null);
  const viewStatesRef = useRef<Record<string, ViewState>>(initialAppState?.viewStates ?? {
    controller: { draft: "", scrollTop: 0 },
  });

  useEffect(() => {
    agentsRef.current = agents;
  }, [agents]);

  useEffect(() => {
    selectedAgentIdRef.current = selectedAgentId;
  }, [selectedAgentId]);

  useEffect(() => {
    inputValueRef.current = inputValue;
  }, [inputValue]);

  useEffect(() => {
    historyRef.current = history;
  }, [history]);

  useEffect(() => {
    controllerMessagesRef.current = controllerMessages;
  }, [controllerMessages]);

  useEffect(() => {
    sidebarVisibleRef.current = sidebarVisible;
  }, [sidebarVisible]);

  useEffect(() => {
    sidebarWidthRef.current = sidebarWidthOverride;
  }, [sidebarWidthOverride]);

  useEffect(() => {
    const timer = setInterval(() => setAnimationTick((value) => value + 1), 200);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      void pollAgents();
    }, 700);
    return () => clearInterval(timer);
  }, []);

  function persistAppState() {
    saveAppState({
      version: 1,
      agents: agentsRef.current,
      selectedAgentId: selectedAgentIdRef.current,
      controllerMessages: controllerMessagesRef.current,
      sidebarVisible: sidebarVisibleRef.current,
      sidebarWidth: sidebarWidthRef.current,
      viewStates: viewStatesRef.current,
      inboxOffset: inboxOffsetRef.current,
    });
  }

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === selectedAgentId) ?? null,
    [agents, selectedAgentId],
  );

  const visibleMessages = selectedAgent ? selectedAgent.messages : controllerMessages;

  const commandMatches = useMemo(() => {
    const text = inputValue.trim();
    if (!text.startsWith("/") || text.includes(" ")) {
      return [] as Array<{ command: string; description: string }>;
    }
    const matches = COMMAND_SPECS.filter((item) => item.command.startsWith(text));
    return matches.length ? matches : text === "/" ? COMMAND_SPECS : [];
  }, [inputValue]);

  useEffect(() => {
    setCommandIndex(0);
  }, [inputValue]);

  useEffect(() => {
    const handleSelection = () => {
      const selection = renderer.getSelection();
      const text = selection?.getSelectedText() ?? "";
      if (!text) {
        return;
      }
      const copied = renderer.copyToClipboardOSC52(text);
      if (!copied && !clipboardWarningShownRef.current) {
        clipboardWarningShownRef.current = true;
        setFooterText("Clipboard copy is unavailable in this terminal. Enable terminal clipboard access for OSC52.");
        setFooterError(true);
      }
    };

    renderer.on(CliRenderEvents.SELECTION, handleSelection);
    return () => {
      renderer.off(CliRenderEvents.SELECTION, handleSelection);
    };
  }, [renderer]);

  function getMessageScrollbox(): { scrollTop: number } | null {
    const renderable = renderer.root.findDescendantById(MESSAGE_SCROLLBOX_ID);
    if (!renderable || typeof (renderable as { scrollTop?: unknown }).scrollTop !== "number") {
      return null;
    }
    return renderable as unknown as { scrollTop: number };
  }

  function getViewState(viewKey: string): ViewState {
    const existing = viewStatesRef.current[viewKey];
    if (existing) {
      return existing;
    }
    const created: ViewState = { draft: "", scrollTop: 0 };
    viewStatesRef.current[viewKey] = created;
    return created;
  }

  function setViewDraft(viewKey: string, draft: string) {
    getViewState(viewKey).draft = draft;
  }

  function getViewDraft(viewKey: string): string {
    return getViewState(viewKey).draft;
  }

  function rememberCurrentViewState(viewKey: string) {
    const scrollbox = getMessageScrollbox();
    const nextState = getViewState(viewKey);
    nextState.draft = inputValueRef.current;
    if (scrollbox) {
      nextState.scrollTop = scrollbox.scrollTop;
    }
  }

  function restoreScrollPosition(viewKey: string) {
    const scrollbox = getMessageScrollbox();
    if (!scrollbox) {
      return;
    }
    scrollbox.scrollTop = getViewState(viewKey).scrollTop;
  }

  useEffect(() => {
    const timer = setTimeout(() => {
      restoreScrollPosition(messageViewKey(selectedAgentId));
    }, 0);
    return () => clearTimeout(timer);
  }, [renderer, selectedAgentId]);

  useEffect(() => {
    const currentView = messageViewKey(selectedAgentId);
    setViewDraft(currentView, inputValue);

    const timer = setTimeout(() => {
      persistAppState();
    }, 120);

    return () => clearTimeout(timer);
  }, [agents, controllerMessages, inputValue, selectedAgentId, sidebarVisible]);

  useEffect(() => {
    const timer = setInterval(() => {
      rememberCurrentViewState(messageViewKey(selectedAgentIdRef.current));
      persistAppState();
    }, 1000);

    return () => {
      clearInterval(timer);
      rememberCurrentViewState(messageViewKey(selectedAgentIdRef.current));
      persistAppState();
    };
  }, []);

  async function pollAgents() {
    const current = agentsRef.current;
    if (!current.length) {
      return;
    }

    const updates = await Promise.all(
      current.map(async (agent) => {
        const paneState = await getTmuxPaneState(agent.sessionName);
        return { agentId: agent.id, paneState };
      }),
    );
    const { events, nextOffset } = readInboxEvents(inboxOffsetRef.current);
    inboxOffsetRef.current = nextOffset;

    setAgents((previous) =>
      previous.map((agent) => {
        const update = updates.find((item) => item.agentId === agent.id);
        if (!update) {
          return agent;
        }

        let next = { ...agent };

        if (!update.paneState.sessionExists) {
          next = {
            ...next,
            state: "error",
            awaitingResult: false,
            needsAttention: true,
          };
        } else if (update.paneState.paneDead) {
          next = {
            ...next,
            state: update.paneState.exitStatus && update.paneState.exitStatus !== 0 ? "error" : "completed",
            awaitingResult: false,
            needsAttention: Boolean(update.paneState.exitStatus && update.paneState.exitStatus !== 0),
          };
        }

        const taskDoneEvents = events.filter((event) => event.agentId === agent.id && event.type === "task_done");
        for (const event of taskDoneEvents) {
          const formatted = formatTaskDone({
            summary: event.summary,
            result: event.result,
            next: event.next,
          });
          if (formatted) {
            next = {
              ...next,
              state: "completed",
              awaitingResult: false,
              needsAttention: false,
              lastSummary: formatted,
              messages: [...next.messages, createMessage("assistant", formatted)],
              unreadCount: selectedAgentIdRef.current === agent.id ? 0 : next.unreadCount + 1,
            };
          }
        }

        return next;
      }),
    );
  }

  function writeController(text: string, role: ChatMessage["role"] = "system") {
    setControllerMessages((previous) => [...previous, createMessage(role, text)]);
    setFooterText(text);
    setFooterError(role === "error" || looksLikeError(text));
  }

  function selectAgent(agentId: string | null) {
    const previousSelectedId = selectedAgentIdRef.current;
    rememberCurrentViewState(messageViewKey(previousSelectedId));
    setSelectedAgentId(agentId);
    setInputValue(getViewDraft(messageViewKey(agentId)));
    setHistoryIndex(null);
    setHistoryDraft("");
    setAgents((previous) => applyAgentSelection(previous, previousSelectedId, agentId));
  }

  async function createAgent({
    tool,
    name,
    cwd,
    launchCommand,
  }: {
    tool: AgentTool;
    name: string;
    cwd: string;
    launchCommand?: string[];
  }) {
    const resolvedCwd = resolve(normalizeCwd(cwd));
    if (!existsSync(resolvedCwd) || !statSync(resolvedCwd).isDirectory()) {
      setFooterText(`Working directory does not exist: ${resolvedCwd}`);
      setFooterError(true);
      return;
    }
    if (agentsRef.current.some((agent) => agent.name === name)) {
      setFooterText(`Agent name already exists: ${name}. Use a different handle, for example ${name}-2.`);
      setFooterError(true);
      return;
    }
    if (!(await isTmuxAvailable())) {
      setFooterText("tmux is required for Claude Code and Codex workers, but it is not installed or not on PATH.");
      setFooterError(true);
      return;
    }
    if (!(await commandExists(tool))) {
      setFooterText(`${tool} is not installed or not on PATH.`);
      setFooterError(true);
      return;
    }

    const id = randomUUID().slice(0, 8);
    const sessionName = makeSessionName(tool, name, id);
    const branch = await detectGitBranch(resolvedCwd);
    const prepared = prepareWorkerLaunchCommand(tool, id, launchCommand);

    try {
      await createTmuxSession(sessionName, resolvedCwd, prepared.command);
    } catch (error) {
      setFooterText((error as Error).message);
      setFooterError(true);
      return;
    }

    const record: AgentRecord = {
      id,
      name,
      tool,
      cwd: resolvedCwd,
      branch,
      sessionName,
      launchCommand: prepared.command,
      runtimeFiles: prepared.runtimeFiles,
      state: "idle",
      unreadCount: 0,
      awaitingResult: false,
      needsAttention: false,
      lastSummary: "",
      messages: [],
      createdAt: Date.now(),
    };

    setAgents((previous) => [...previous, record]);
    selectAgent(record.id);
    writeController(`Created ${clientLabel(tool)} agent ${name} (${id})`);
  }

  async function closeAgent(name?: string) {
    const target =
      (name ? agentsRef.current.find((agent) => agent.name === name) : undefined) ??
      (selectedAgentIdRef.current ? agentsRef.current.find((agent) => agent.id === selectedAgentIdRef.current) : undefined);

    if (!target) {
      setFooterText("No active agent to close");
      setFooterError(true);
      return;
    }

    await destroyTmuxSession(target.sessionName);
    cleanupRuntimeFiles(target.runtimeFiles);
    delete viewStatesRef.current[target.id];
    setAgents((previous) => previous.filter((agent) => agent.id !== target.id));
    if (selectedAgentIdRef.current === target.id) {
      selectAgent(null);
    }
    writeController(`Closed @${target.name}`);
  }

  async function attachAgent(name?: string) {
    const target =
      (name ? agentsRef.current.find((agent) => agent.name === name) : undefined) ??
      (selectedAgentIdRef.current ? agentsRef.current.find((agent) => agent.id === selectedAgentIdRef.current) : undefined);

    if (!target) {
      setFooterText("No agent selected. Use Ctrl+1..9 or /attach <agent-name>.");
      setFooterError(true);
      return;
    }

    const paneState = await getTmuxPaneState(target.sessionName);
    if (!paneState.sessionExists) {
      setFooterText(`tmux session is gone: ${target.sessionName}`);
      setFooterError(true);
      return;
    }
    if (paneState.paneDead) {
      setFooterText(`tmux pane for @${target.name} has already exited. There is no live CLI to attach to.`);
      setFooterError(true);
      return;
    }

    setFooterText(`Attaching @${target.name}. Detach with Ctrl+B then d to return.`);
    setFooterError(false);
    renderer.suspend();
    try {
      attachTmuxSession(target.sessionName);
    } finally {
      renderer.resume();
    }
    setFooterText(`Returned from tmux session @${target.name}`);
    setFooterError(false);
  }

  async function sendToAgent(agentName: string, message: string) {
    const target = agentsRef.current.find((agent) => agent.name === agentName);
    if (!target) {
      setFooterText(`Unknown agent: ${agentName}`);
      setFooterError(true);
      return;
    }

    try {
      await sendTextToTmux(target.sessionName, buildTaskDonePrompt(message));
    } catch (error) {
      setFooterText((error as Error).message);
      setFooterError(true);
      return;
    }

    setAgents((previous) =>
      previous.map((agent) => {
        if (agent.id !== target.id) {
          return agent;
        }
        return {
          ...agent,
          state: "working",
          awaitingResult: true,
          needsAttention: false,
          messages: [...agent.messages, createMessage("user", message)],
          unreadCount: selectedAgentIdRef.current === agent.id ? 0 : agent.unreadCount + 1,
        };
      }),
    );
    setFooterText("");
    setFooterError(false);
  }

  async function handleRouterResult(result: RouterResult) {
    if (result.kind === "help") {
      writeController(
        "Commands: /help, /agents, /new <codex|claude> <name> <cwd> [client args...], /attach [agent-name], /close [agent-name], @agent-name <message>.",
      );
      return;
    }
    if (result.kind === "agents") {
      if (!agentsRef.current.length) {
        writeController("No agents registered");
        return;
      }
      writeController(
        agentsRef.current
          .map(
            (agent) =>
              `${agent.name} [${clientLabel(agent.tool)}] ${stateLabel(agent.state)} unread=${agent.unreadCount} cwd=${agent.cwd}`,
          )
          .join("\n"),
      );
      return;
    }
    if (result.kind === "invalid") {
      setFooterText(result.message ?? "Invalid input");
      setFooterError(true);
      return;
    }
    if (result.kind === "create_agent" && result.tool && result.name && result.cwd) {
      await createAgent({
        tool: result.tool,
        name: result.name,
        cwd: result.cwd,
        launchCommand: result.launchCommand,
      });
      return;
    }
    if (result.kind === "close_agent") {
      await closeAgent(result.target);
      return;
    }
    if (result.kind === "attach_agent") {
      await attachAgent(result.target);
      return;
    }
    if (result.kind === "agent_message") {
      if (!result.target || !result.message) {
        setFooterText("Usage: @agent-name <message>");
        setFooterError(true);
        return;
      }
      await sendToAgent(result.target, result.message);
      const target = agentsRef.current.find((agent) => agent.name === result.target);
      if (target) {
        selectAgent(target.id);
      }
      return;
    }
    if (result.kind === "controller_message") {
      const interpreted = interpretControllerMessage(result.message ?? "");
      if (interpreted) {
        await handleRouterResult(interpreted);
        return;
      }
      writeController(
        "Plain controller chat is not wired to a primary LLM yet. You can still create agents with natural language if the message clearly names a client and directory, or use /new and @agent-name.",
        "error",
      );
    }
  }

  async function submitInput(rawValue?: string) {
    const currentView = messageViewKey(selectedAgentIdRef.current);
    const currentValue = (rawValue ?? inputValueRef.current).trimEnd();
    const remembered = rememberHistory(historyRef.current, currentValue, HISTORY_LIMIT);
    setHistory(remembered);
    setHistoryIndex(null);
    setHistoryDraft("");
    setInputValue("");
    setViewDraft(currentView, "");

    if (!currentValue.trim()) {
      return;
    }

    if (selectedAgentIdRef.current && !currentValue.startsWith("/") && !currentValue.startsWith("@")) {
      const selected = agentsRef.current.find((agent) => agent.id === selectedAgentIdRef.current);
      if (selected) {
        await sendToAgent(selected.name, currentValue);
        return;
      }
    }

    writeController(currentValue, "user");
    await handleRouterResult(parseUserInput(currentValue));
  }

  function historyPrevious() {
    const currentHistory = historyRef.current;
    const currentView = messageViewKey(selectedAgentIdRef.current);
    if (!currentHistory.length) {
      return;
    }
    if (historyIndex === null) {
      setHistoryDraft(inputValueRef.current);
      const nextIndex = currentHistory.length - 1;
      setHistoryIndex(nextIndex);
      const nextValue = currentHistory[nextIndex] ?? "";
      setInputValue(nextValue);
      setViewDraft(currentView, nextValue);
      return;
    }
    const nextIndex = Math.max(0, historyIndex - 1);
    setHistoryIndex(nextIndex);
    const nextValue = currentHistory[nextIndex] ?? "";
    setInputValue(nextValue);
    setViewDraft(currentView, nextValue);
  }

  function historyNext() {
    const currentView = messageViewKey(selectedAgentIdRef.current);
    const currentHistory = historyRef.current;
    if (historyIndex === null) {
      return;
    }
    if (historyIndex >= currentHistory.length - 1) {
      setHistoryIndex(null);
      setInputValue(historyDraft);
      setViewDraft(currentView, historyDraft);
      return;
    }
    const nextIndex = historyIndex + 1;
    setHistoryIndex(nextIndex);
    const nextValue = currentHistory[nextIndex] ?? "";
    setInputValue(nextValue);
    setViewDraft(currentView, nextValue);
  }

  function startSidebarResize(event: MouseEvent) {
    dividerDragRef.current = {
      startX: event.x,
      startWidth: sidebarWidth,
    };
    setDividerActive(true);
    renderer.setMousePointer("move");
  }

  function resizeSidebarFromMouse(event: MouseEvent) {
    const drag = dividerDragRef.current;
    if (!drag) {
      return;
    }
    const delta = event.x - drag.startX;
    setSidebarWidthOverride(clampSidebarWidth(drag.startWidth + delta, width));
    setDividerActive(true);
    renderer.setMousePointer("move");
  }

  function finishSidebarResize(pointer: "default" | "move") {
    dividerDragRef.current = null;
    setDividerActive(pointer === "move");
    renderer.setMousePointer(pointer);
  }

  function handleGlobalDividerDrag(event: MouseEvent) {
    if (!dividerDragRef.current) {
      return;
    }
    resizeSidebarFromMouse(event);
  }

  function handleGlobalDividerRelease(pointer: "default" | "move") {
    if (!dividerDragRef.current) {
      return;
    }
    finishSidebarResize(pointer);
  }

  useKeyboard((key: KeyEvent) => {
    if (key.ctrl && key.name === "c") {
      renderer.destroy();
      process.exit(0);
    }

    if (key.ctrl && key.name === "b") {
      setSidebarVisible((value) => !value);
      return;
    }

    if (key.ctrl && key.name === "x") {
      void closeAgent();
      return;
    }

    if (key.ctrl && key.name === "t") {
      void attachAgent();
      return;
    }

    if (key.ctrl && /^[1-9]$/.test(key.name)) {
      const index = Number.parseInt(key.name, 10) - 1;
      const target = agentsRef.current[index];
      if (target) {
        selectAgent(target.id);
      }
      return;
    }

    if (key.name === "escape") {
      selectAgent(null);
      return;
    }

    if (key.name === "up") {
      historyPrevious();
      return;
    }

    if (key.name === "down") {
      historyNext();
      return;
    }

    if (key.name === "tab" && commandMatches.length) {
      const nextIndex = (commandIndex + 1) % commandMatches.length;
      const active = commandMatches[commandIndex] ?? commandMatches[0];
      setInputValue(`${active?.command ?? commandMatches[0]?.command ?? ""}${active?.command === "/new" || active?.command === "/attach" || active?.command === "/close" ? " " : ""}`);
      setCommandIndex(nextIndex);
    }
  });

  const sidebarWidth = sidebarVisible
    ? clampSidebarWidth(sidebarWidthOverride ?? Math.floor(width * 0.32), width)
    : 0;
  const statusBarText = agents.length
    ? agents
        .map((agent) => `${agent.name}:${stateToken(agent.state)}${agent.unreadCount ? "*" : ""}${agent.needsAttention ? "!" : ""}`)
        .join(" | ")
    : "No agents running";
  const footerDisplay = commandMatches.length ? commandFooter(commandMatches, commandIndex % commandMatches.length) : footerText;
  const footerColor = commandMatches.length ? "#B3BFCC" : footerError ? "#FF6F6F" : "#D1D8E0";
  const workspaceTitle = selectedAgent
    ? `@${selectedAgent.name}  ${clientLabel(selectedAgent.tool)}  ${stateLabel(selectedAgent.state)}`
    : "Controller";

  return (
    <box style={{ width: "100%", height: "100%", flexDirection: "column", backgroundColor: "transparent" }}>
      <box
        style={{
          width: "100%",
          height: 1,
          paddingLeft: 1,
          backgroundColor: TOP_BAR_BACKGROUND,
        }}
      >
        <text fg="#EFF1F5" attributes={TextAttributes.BOLD}>
          {statusBarText}
        </text>
      </box>

      <box
        style={{ width: "100%", height: "100%", flexDirection: "row", backgroundColor: "transparent" }}
        onMouseDrag={handleGlobalDividerDrag}
        onMouseDragEnd={() => handleGlobalDividerRelease("default")}
        onMouseUp={() => handleGlobalDividerRelease("default")}
      >
        {sidebarVisible ? (
          <box
            style={{
              width: sidebarWidth,
              height: "100%",
              flexDirection: "column",
              backgroundColor: "transparent",
              paddingTop: 0,
            }}
          >
            {agents.length ? (
              <scrollbox stickyScroll stickyStart="top" style={{ width: "100%", height: "100%" }}>
                {agents.map((agent) => (
                  <box
                    key={agent.id}
                    title={`@${agent.name}`}
                    style={{
                      width: "100%",
                      border: true,
                      borderStyle: "rounded",
                      borderColor: borderColor(agent.id === selectedAgentId),
                      paddingLeft: 1,
                      paddingRight: 1,
                      paddingTop: 0,
                      paddingBottom: 0,
                      marginTop: 0,
                      marginBottom: 1,
                      flexDirection: "column",
                    }}
                  >
                    <text fg="#FFFFFF">client {clientLabel(agent.tool)}</text>
                    <text fg="#FFFFFF">dir {agent.cwd}</text>
                    <text fg={stateColor(agent.state)}>
                      {placeholderStatusSymbol(agent.state, animationTick)} {stateLabel(agent.state)}
                    </text>
                  </box>
                ))}
              </scrollbox>
            ) : (
              <box style={{ paddingLeft: 1, paddingRight: 1, paddingTop: 1, flexDirection: "column" }}>
                <text fg="#8293A6">No agents yet.</text>
                <text fg="#8293A6">Use /new &lt;codex|claude&gt; &lt;name&gt; &lt;cwd&gt;</text>
                <text fg="#8293A6">or say: create a codex session in /path/to/project</text>
              </box>
            )}
          </box>
        ) : null}

        {sidebarVisible ? (
          <box
            style={{
              width: 1,
              height: "100%",
              border: ["left"],
              borderColor: dividerActive ? "#7FB3FF" : "#2A3E52",
            }}
            onMouseOver={() => {
              setDividerActive(true);
              renderer.setMousePointer("move");
            }}
            onMouseOut={() => {
              if (!dividerDragRef.current) {
                setDividerActive(false);
                renderer.setMousePointer("default");
              }
            }}
            onMouseDown={startSidebarResize}
            onMouseDragEnd={() => {
              finishSidebarResize("default");
            }}
            onMouseUp={() => {
              finishSidebarResize("move");
            }}
          />
        ) : null}

        <box style={{ width: "100%", height: "100%", flexDirection: "column", backgroundColor: "transparent" }}>
          <box style={{ width: "100%", height: 1, paddingLeft: 1, backgroundColor: "transparent" }}>
            <text fg="#B3BFCC">{workspaceTitle}</text>
          </box>

          <scrollbox
            id={MESSAGE_SCROLLBOX_ID}
            stickyScroll
            stickyStart="bottom"
            style={{
              width: "100%",
              height: "100%",
              backgroundColor: "transparent",
              paddingLeft: 1,
              paddingRight: 1,
            }}
          >
            {visibleMessages.length ? (
              visibleMessages.map((message, index) => (
                <box
                  key={message.id}
                  style={{
                    width: "100%",
                    flexDirection: "column",
                    marginBottom: index === visibleMessages.length - 1 ? 0 : 1,
                  }}
                >
                  <text
                    fg={
                      message.role === "user"
                        ? "#7FB3FF"
                        : message.role === "error"
                          ? "#FF6F6F"
                          : message.role === "system"
                            ? "#B3BFCC"
                            : "#EFF1F5"
                    }
                  >
                    {message.role === "user" &&
                    selectedAgent &&
                    selectedAgent.awaitingResult &&
                    index === visibleMessages.length - 1
                      ? `> ${SPINNER_FRAMES[animationTick % SPINNER_FRAMES.length]} ${message.content}`
                      : message.role === "user"
                        ? `> ${message.content}`
                        : message.content}
                  </text>
                </box>
              ))
            ) : (
              <text fg="#8293A6">
                {selectedAgent ? `@${selectedAgent.name} selected. Waiting for the next agent result...` : "Controller is ready."}
              </text>
            )}
          </scrollbox>

          <box style={{ width: "100%", height: 5, flexDirection: "column", backgroundColor: "transparent" }}>
            <box
              style={{
                width: "100%",
                height: 3,
                border: ["top", "bottom"],
                borderColor: "#2A3E52",
                backgroundColor: "transparent",
                paddingLeft: 1,
                paddingRight: 1,
                flexDirection: "row",
                alignItems: "center",
              }}
            >
              <text fg="#7FE5B2" attributes={TextAttributes.BOLD}>
                &gt;
              </text>
              <input
                value={inputValue}
                focused
                placeholder={
                  selectedAgent
                    ? `Message @${selectedAgent.name} directly, or press Esc to return to controller`
                    : "Ask controller, create agents naturally, or use /new /attach @agent-name ..."
                }
                onInput={(value) => {
                  setInputValue(value);
                  setViewDraft(messageViewKey(selectedAgentIdRef.current), value);
                }}
                onSubmit={(valueOrEvent) => {
                  if (typeof valueOrEvent === "string") {
                    void submitInput(valueOrEvent);
                    return;
                  }
                  void submitInput();
                }}
                width={Math.max(10, width - sidebarWidth - 8)}
                backgroundColor="transparent"
                focusedBackgroundColor="transparent"
                textColor="#EFF1F5"
                cursorColor="#7FE5B2"
              />
            </box>
            <box style={{ width: "100%", height: 2, paddingLeft: 1, paddingRight: 1, justifyContent: "center" }}>
              <text fg={footerColor}>{footerDisplay}</text>
            </box>
          </box>
        </box>
      </box>
    </box>
  );
}
