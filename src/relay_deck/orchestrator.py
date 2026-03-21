from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from relay_deck.adapters import ClaudeCodeAdapter, CodexAdapter, MockAdapter
from relay_deck.adapters.base import AgentAdapter
from relay_deck.events import EventBus
from relay_deck.models import AgentEvent, AgentSpec, EventType, ToolType
from relay_deck.registry import AgentRegistry
from relay_deck.router import InputRouter, RouterResult
from relay_deck.tmux_manager import TmuxCommandError, TmuxManager, TmuxUnavailableError


class Orchestrator:
    def __init__(self, tmux: TmuxManager | None = None) -> None:
        self.registry = AgentRegistry()
        self.bus = EventBus()
        self.router = InputRouter()
        self.tmux = tmux or TmuxManager()
        self._adapters: dict[str, AgentAdapter] = {}

    async def handle_input(self, raw: str) -> str:
        result = self.router.parse(raw)
        return await self.dispatch(result)

    async def dispatch(self, result: RouterResult) -> str:
        return await self._dispatch(result)

    async def emit(self, event: AgentEvent) -> None:
        self.registry.apply_event(event)
        await self.bus.publish(event)

    async def create_agent(self, spec: AgentSpec) -> str:
        if spec.tool_type in {ToolType.CLAUDE, ToolType.CODEX} and not await self.tmux.is_available():
            raise RuntimeError("tmux is required for Claude Code and Codex workers")
        agent_id = spec.agent_id or str(uuid.uuid4())[:8]
        spec.agent_id = agent_id
        branch = await self._detect_git_branch(spec.cwd)
        self.registry.register(
            agent_id=agent_id,
            name=spec.name,
            tool_type=spec.tool_type,
            cwd=spec.cwd,
            branch=branch,
        )
        await self.emit(
            AgentEvent(
                type=EventType.REGISTERED,
                agent_id=agent_id,
                message=f"Registered {spec.name}",
                payload={"branch": branch or ""},
            )
        )
        adapter = self._make_adapter(spec)
        self._adapters[agent_id] = adapter
        await adapter.start()
        return agent_id

    async def send_to_agent(self, agent_name: str, message: str) -> str:
        record = self.registry.get_by_name(agent_name)
        if record is None:
            return f"Unknown agent: {agent_name}"
        adapter = self._adapters.get(record.agent_id)
        if adapter is None:
            return f"Agent {agent_name} is not attached"
        await adapter.send(message)
        return f"Sent to @{agent_name}: {message}"

    async def attach_agent_session(self, agent_name: str) -> str:
        record = self.registry.get_by_name(agent_name)
        if record is None:
            return f"Unknown agent: {agent_name}"
        return await self.attach_agent_session_by_id(record.agent_id)

    async def attach_agent_session_by_id(self, agent_id: str) -> str:
        record = self.registry.get(agent_id)
        if record is None:
            return "Selected agent is no longer available"
        if record.tool_type == ToolType.MOCK:
            return "Demo agents do not have real tmux sessions"
        if not record.session_name:
            return f"Agent @{record.name} does not have a tmux session yet"
        if not await self.tmux.is_available():
            return "tmux is required but is not installed or not on PATH"
        if not await self.tmux.has_session(record.session_name):
            return f"tmux session is gone: {record.session_name}"
        try:
            await self.tmux.attach_session(record.session_name)
        except (TmuxUnavailableError, TmuxCommandError, FileNotFoundError) as exc:
            return f"Failed to attach tmux session: {exc}"
        return ""

    async def shutdown(self) -> None:
        await asyncio.gather(*(adapter.stop() for adapter in self._adapters.values()), return_exceptions=True)

    async def _dispatch(self, result: RouterResult) -> str:
        if result.kind == "empty":
            return ""
        if result.kind == "help":
            return (
                "Commands: /help, /agents, /new <codex|claude> <name> <cwd>, "
                "/attach [agent-name], @agent-name <message>. "
                "Claude/Codex workers run inside tmux sessions."
            )
        if result.kind == "agents":
            agents = self.registry.list()
            if not agents:
                return "No agents registered"
            return "\n".join(
                f"{item.name} [{item.tool_type.client_label}] {item.state.value} unread={item.unread_count} cwd={item.cwd}"
                for item in agents
            )
        if result.kind == "invalid":
            return result.message or "Invalid input"
        if result.kind == "create_agent":
            assert result.name is not None
            assert result.cwd is not None
            assert result.tool_type is not None
            cwd = result.cwd.resolve()
            if not cwd.exists() or not cwd.is_dir():
                return f"Working directory does not exist: {cwd}"
            if result.tool_type in {ToolType.CLAUDE, ToolType.CODEX} and not await self.tmux.is_available():
                return "tmux is required for Claude Code and Codex workers, but it is not installed or not on PATH"
            spec = AgentSpec(name=result.name, tool_type=result.tool_type, cwd=cwd)
            try:
                agent_id = await self.create_agent(spec)
            except RuntimeError as exc:
                return str(exc)
            return f"Created {result.tool_type.client_label} agent {result.name} ({agent_id})"
        if result.kind == "attach_agent":
            if result.target:
                return f"Attach @{result.target} from the UI with Ctrl+T or use the selected agent."
            return "Select an agent first, then press Ctrl+T, or run /attach <agent-name> in the UI."
        if result.kind == "agent_message":
            if not result.target:
                return "Usage: @agent-name <message>"
            if not result.message:
                return f"Usage: @{result.target} <message>"
            return await self.send_to_agent(result.target, result.message)
        if result.kind == "controller_message":
            return (
                "Plain controller chat is not wired to a primary LLM yet. "
                "Use /new to start agents or @agent-name to route work."
            )
        return "Unhandled input"

    def _make_adapter(self, spec: AgentSpec) -> AgentAdapter:
        if spec.tool_type == ToolType.CLAUDE:
            return ClaudeCodeAdapter(spec, self.emit, self.tmux)
        if spec.tool_type == ToolType.CODEX:
            return CodexAdapter(spec, self.emit, self.tmux)
        if spec.tool_type == ToolType.MOCK:
            return MockAdapter(spec, self.emit)
        raise ValueError(f"Unsupported tool type: {spec.tool_type}")

    async def _detect_git_branch(self, cwd: Path) -> str | None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "rev-parse",
                "--abbrev-ref",
                "HEAD",
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return None

        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return None
        branch = stdout.decode().strip()
        return branch or None
