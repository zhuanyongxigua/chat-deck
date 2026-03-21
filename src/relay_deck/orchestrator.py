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


class Orchestrator:
    def __init__(self) -> None:
        self.registry = AgentRegistry()
        self.bus = EventBus()
        self.router = InputRouter()
        self._adapters: dict[str, AgentAdapter] = {}

    async def handle_input(self, raw: str) -> str:
        result = self.router.parse(raw)
        return await self._dispatch(result)

    async def emit(self, event: AgentEvent) -> None:
        self.registry.apply_event(event)
        await self.bus.publish(event)

    async def create_agent(self, spec: AgentSpec) -> str:
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

    async def shutdown(self) -> None:
        await asyncio.gather(*(adapter.stop() for adapter in self._adapters.values()), return_exceptions=True)

    async def _dispatch(self, result: RouterResult) -> str:
        if result.kind == "empty":
            return ""
        if result.kind == "help":
            return (
                "Commands: /help, /agents, /new <codex|claude> <name> <cwd>, "
                "@agent-name <message>"
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
            spec = AgentSpec(name=result.name, tool_type=result.tool_type, cwd=cwd)
            agent_id = await self.create_agent(spec)
            return f"Created {result.tool_type.client_label} agent {result.name} ({agent_id})"
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
            return ClaudeCodeAdapter(spec, self.emit)
        if spec.tool_type == ToolType.CODEX:
            return CodexAdapter(spec, self.emit)
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
