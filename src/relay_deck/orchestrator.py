from __future__ import annotations

import asyncio
import contextlib
import json
import shlex
import sys
import tempfile
import uuid
from pathlib import Path

from relay_deck.adapters import ClaudeCodeAdapter, CodexAdapter, MockAdapter
from relay_deck.adapters.base import AgentAdapter
from relay_deck.controller import ControllerInterpreter
from relay_deck.events import EventBus
from relay_deck.models import AgentEvent, AgentSpec, AgentState, EventType, ToolType, display_state_label
from relay_deck.registry import AgentRegistry
from relay_deck.runtime_events import (
    RuntimeEventInbox,
    TaskDoneEvent,
    TaskDoneInbox,
    TurnResult,
    WorkerReport,
    build_report_command,
)
from relay_deck.router import InputRouter, RouterResult
from relay_deck.tmux_manager import TmuxCommandError, TmuxManager, TmuxUnavailableError


class Orchestrator:
    def __init__(
        self,
        tmux: TmuxManager | None = None,
        runtime_dir: Path | None = None,
        done_inbox_path: Path | None = None,
    ) -> None:
        runtime_root = runtime_dir or Path(tempfile.mkdtemp(prefix="relay-deck-"))
        self.registry = AgentRegistry()
        self.bus = EventBus()
        self.router = InputRouter()
        self.controller = ControllerInterpreter()
        self.tmux = tmux or TmuxManager()
        self.runtime = RuntimeEventInbox(runtime_root)
        self.done_inbox = TaskDoneInbox(done_inbox_path or (runtime_root / "inbox.jsonl"))
        self._adapters: dict[str, AgentAdapter] = {}
        self._runtime_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self.runtime.ensure()
        self.done_inbox.ensure()
        if self._runtime_task is None:
            self._runtime_task = asyncio.create_task(self._consume_runtime_reports())

    async def handle_input(self, raw: str) -> str:
        result = self.router.parse(raw)
        return await self.dispatch(result)

    async def dispatch(self, result: RouterResult) -> str:
        return await self._dispatch(result)

    async def emit(self, event: AgentEvent) -> None:
        self.registry.apply_event(event)
        await self.bus.publish(event)

    async def create_agent(self, spec: AgentSpec) -> str:
        await self.start()
        if spec.tool_type in {ToolType.CLAUDE, ToolType.CODEX} and not await self.tmux.is_available():
            raise RuntimeError("tmux is required for Claude Code and Codex workers")
        existing = self.registry.get_by_name(spec.name)
        if existing is not None:
            raise RuntimeError(
                f"Agent name already exists: {spec.name}. "
                f"Use a different handle, for example {spec.name}-2."
            )
        agent_id = spec.agent_id or str(uuid.uuid4())[:8]
        spec.agent_id = agent_id
        self._prepare_launch_command(spec)
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

    async def send_to_agent(self, agent_name: str, message: str, *, display_message: str | None = None) -> str:
        record = self.registry.get_by_name(agent_name)
        if record is None:
            return f"Unknown agent: {agent_name}"
        adapter = self._adapters.get(record.agent_id)
        if adapter is None:
            return f"Agent {agent_name} is not attached"
        wire_message = message
        if record.tool_type in {ToolType.CLAUDE, ToolType.CODEX}:
            wire_message = self._build_task_done_prompt(
                message=message,
            )
        visible_message = display_message or message
        await adapter.send(wire_message, display_message=visible_message)
        return f"Sent to @{agent_name}: {visible_message}"

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

    async def capture_agent_snapshot_by_id(self, agent_id: str, *, lines: int = 18) -> list[str]:
        record = self.registry.get(agent_id)
        if record is None:
            return []
        if record.session_name and record.tool_type in {ToolType.CLAUDE, ToolType.CODEX}:
            if await self.tmux.is_available():
                try:
                    snapshot = await self.tmux.capture_snapshot(record.session_name, lines=lines)
                except (TmuxUnavailableError, TmuxCommandError):
                    snapshot = []
                if snapshot:
                    return snapshot[-lines:]
        transcript_tail = [line.text for line in list(record.transcript)[-lines:]]
        if transcript_tail:
            return transcript_tail
        return list(record.recent_output)[-lines:]

    async def shutdown(self) -> None:
        if self._runtime_task is not None:
            self._runtime_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runtime_task
        await asyncio.gather(*(adapter.stop() for adapter in self._adapters.values()), return_exceptions=True)

    async def poll_runtime_reports_once(self) -> int:
        reports = self.runtime.drain()
        for report in reports:
            await self._apply_worker_report(report)
        turn_results = self.runtime.drain_turn_results()
        for result in turn_results:
            await self._apply_turn_result(result)
        task_done_events = self.done_inbox.drain()
        for event in task_done_events:
            await self._apply_task_done_event(event)
        return len(reports) + len(turn_results) + len(task_done_events)

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
                f"{item.name} [{item.tool_type.client_label}] {display_state_label(item.state)} unread={item.unread_count} cwd={item.cwd}"
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
            interpreted = self.controller.interpret(result.message or "")
            if interpreted is not None:
                return await self._dispatch(interpreted)
            return (
                "Plain controller chat is not wired to a primary LLM yet. "
                "You can still create agents with natural language if the message clearly names a client and directory, "
                "or use /new and @agent-name."
            )
        return "Unhandled input"

    async def _consume_runtime_reports(self) -> None:
        while True:
            await self.poll_runtime_reports_once()
            await asyncio.sleep(0.2)

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

    def _prepare_launch_command(self, spec: AgentSpec) -> None:
        if spec.launch_command is not None:
            return
        if spec.tool_type == ToolType.CLAUDE:
            spec.launch_command = self._build_claude_command(spec)
        elif spec.tool_type == ToolType.CODEX:
            spec.launch_command = self._build_codex_command(spec)

    def _build_claude_command(self, spec: AgentSpec) -> list[str]:
        settings_path = self._write_claude_settings(spec)
        return ["claude", "--settings", str(settings_path)]

    def _build_codex_command(self, spec: AgentSpec) -> list[str]:
        assert spec.agent_id is not None
        notify_argv = [
            sys.executable,
            "-m",
            "relay_deck",
            "publish-done",
            "--tool",
            "codex",
            "--runtime-dir",
            str(self.runtime.runtime_dir),
            "--agent-id",
            spec.agent_id,
            "--event",
            "agent-turn-complete",
            "--inbox",
            str(self.done_inbox.path),
        ]
        return [
            "codex",
            "-c",
            f"notify={json.dumps(notify_argv)}",
        ]

    def _write_claude_settings(self, spec: AgentSpec) -> Path:
        assert spec.agent_id is not None
        agent_dir = self.runtime.agent_dir(spec.agent_id)
        settings_path = agent_dir / "claude-settings.json"
        hooks = {}
        for event_name in ("Notification", "PermissionRequest", "Stop", "SessionEnd"):
            if event_name == "Stop":
                command = self._build_publish_done_command(
                    tool="claude",
                    agent_id=spec.agent_id,
                    event_name=event_name,
                )
            else:
                command = build_report_command(
                    python_executable=sys.executable,
                    runtime_dir=self.runtime.runtime_dir,
                    agent_id=spec.agent_id,
                    source="claude",
                    event_name=event_name,
                )
            hooks[event_name] = [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command,
                            "timeout": 10,
                        }
                    ]
                }
            ]
        settings_path.write_text(json.dumps({"hooks": hooks}, indent=2), encoding="utf-8")
        return settings_path

    async def _apply_worker_report(self, report: WorkerReport) -> None:
        if self.registry.get(report.agent_id) is None:
            return
        if report.summary:
            await self.emit(
                AgentEvent(
                    type=EventType.SUMMARY_UPDATED,
                    agent_id=report.agent_id,
                    message=report.summary,
                    payload={
                        "report_source": report.source,
                        "report_event": report.event_name,
                    },
                )
            )
        if report.source == "claude":
            await self._apply_claude_report(report)
            return
        if report.source == "codex":
            await self._apply_codex_report(report)
            return
        await self._apply_generic_report(report)

    async def _apply_turn_result(self, result: TurnResult) -> None:
        if self.registry.get(result.agent_id) is None:
            return
        message = self._format_turn_result_message(result)
        if message:
            await self.emit(
                AgentEvent(
                    type=EventType.SUMMARY_UPDATED,
                    agent_id=result.agent_id,
                    message=message,
                    payload={
                        "turn_id": result.turn_id,
                        "turn_status": result.status,
                        "source": "turn-result",
                    },
                )
            )
        state = self._parse_state(result.status)
        await self.emit(
            AgentEvent(
                type=EventType.STATE_CHANGED,
                agent_id=result.agent_id,
                message=message or f"Turn {result.turn_id} reported {result.status}",
                state=state,
                payload={
                    "turn_id": result.turn_id,
                    "turn_status": result.status,
                    "source": "turn-result",
                },
            )
        )

    async def _apply_task_done_event(self, event: TaskDoneEvent) -> None:
        if self.registry.get(event.agent_id) is None:
            return
        message = self._format_task_done_message(event)
        if not message:
            return
        await self.emit(
            AgentEvent(
                type=EventType.SUMMARY_UPDATED,
                agent_id=event.agent_id,
                message=message,
                payload={
                    "source": "task_done_inbox",
                    "tool": event.tool,
                    "cwd": event.cwd,
                    "session_id": event.session_id,
                },
            )
        )

    async def _apply_generic_report(self, report: WorkerReport) -> None:
        state = self._parse_state(report.state)
        message = report.message or f"{report.source} reported {report.event_name}"
        await self._emit_state_event(
            agent_id=report.agent_id,
            state=state,
            message=message,
            payload={
                "report_source": report.source,
                "report_event": report.event_name,
                "report_payload": report.payload,
            },
        )

    async def _apply_claude_report(self, report: WorkerReport) -> None:
        payload = report.payload
        event_name = report.event_name
        if event_name == "Notification":
            parts = [payload.get("title"), payload.get("message"), payload.get("notification_type")]
            message = " | ".join(str(part) for part in parts if part) or report.message or "Claude is waiting"
            await self._emit_state_event(
                agent_id=report.agent_id,
                state=AgentState.WAITING,
                message=message,
                payload={"report_source": report.source, "report_event": event_name, "report_payload": payload},
            )
            return
        if event_name == "PermissionRequest":
            tool_name = payload.get("tool_name")
            message = "Claude is waiting for permission"
            if tool_name:
                message = f"{message}: {tool_name}"
            await self._emit_state_event(
                agent_id=report.agent_id,
                state=AgentState.WAITING,
                message=report.message or message,
                payload={"report_source": report.source, "report_event": event_name, "report_payload": payload},
            )
            return
        if event_name == "Stop":
            await self._emit_state_event(
                agent_id=report.agent_id,
                state=AgentState.COMPLETED,
                message=report.message or "Claude completed its current turn",
                payload={"report_source": report.source, "report_event": event_name, "report_payload": payload},
            )
            return
        if event_name == "SessionEnd":
            reason = str(payload.get("reason") or report.message or "Claude session ended")
            state = AgentState.ERROR if "error" in reason.lower() or "fail" in reason.lower() else AgentState.IDLE
            await self._emit_state_event(
                agent_id=report.agent_id,
                state=state,
                message=reason,
                payload={"report_source": report.source, "report_event": event_name, "report_payload": payload},
            )
            return
        await self._apply_generic_report(report)

    async def _apply_codex_report(self, report: WorkerReport) -> None:
        payload = report.payload
        event_name = report.event_name
        if event_name == "thread/status/changed":
            status = payload.get("status")
            state, message = self._map_codex_thread_status(status)
            await self._emit_state_event(
                agent_id=report.agent_id,
                state=state,
                message=report.message or message,
                payload={"report_source": report.source, "report_event": event_name, "report_payload": payload},
            )
            return
        if event_name in {"turn/completed", "agent-turn-complete", "turn_completed"}:
            await self._emit_state_event(
                agent_id=report.agent_id,
                state=AgentState.COMPLETED,
                message=report.message or "Codex completed its current turn",
                payload={"report_source": report.source, "report_event": event_name, "report_payload": payload},
            )
            return
        if event_name in {"error", "thread/error"}:
            await self._emit_state_event(
                agent_id=report.agent_id,
                state=AgentState.ERROR,
                message=report.message or "Codex reported an error",
                payload={"report_source": report.source, "report_event": event_name, "report_payload": payload},
            )
            return
        await self._apply_generic_report(report)

    async def _emit_state_event(
        self,
        *,
        agent_id: str,
        state: AgentState,
        message: str,
        payload: dict[str, object],
    ) -> None:
        if state == AgentState.COMPLETED:
            await self.emit(
                AgentEvent(
                    type=EventType.COMPLETED,
                    agent_id=agent_id,
                    message=message,
                    state=AgentState.COMPLETED,
                    payload=payload,
                )
            )
            return
        if state == AgentState.ERROR:
            await self.emit(
                AgentEvent(
                    type=EventType.ERROR,
                    agent_id=agent_id,
                    message=message,
                    state=AgentState.ERROR,
                    payload=payload,
                )
            )
            return
        await self.emit(
            AgentEvent(
                type=EventType.STATE_CHANGED,
                agent_id=agent_id,
                message=message,
                state=state,
                payload=payload,
            )
        )

    def _parse_state(self, raw: str | None) -> AgentState:
        if not raw:
            return AgentState.WORKING
        normalized = raw.strip().lower()
        for state in AgentState:
            if state.value == normalized:
                return state
        return AgentState.WORKING

    def _map_codex_thread_status(self, status_payload: object) -> tuple[AgentState, str]:
        if not isinstance(status_payload, dict):
            return AgentState.WORKING, "Codex status updated"
        status_type = str(status_payload.get("type") or "active")
        active_flags = [str(flag) for flag in status_payload.get("activeFlags") or []]
        if status_type == "active":
            if "waitingOnApproval" in active_flags:
                return AgentState.WAITING, "Codex is waiting on approval"
            if "waitingOnUserInput" in active_flags:
                return AgentState.WAITING, "Codex is waiting on user input"
            return AgentState.WORKING, "Codex is working"
        if status_type == "idle":
            return AgentState.IDLE, "Codex is idle"
        if status_type == "systemError":
            return AgentState.ERROR, "Codex reported a system error"
        return AgentState.UNKNOWN, f"Codex status changed: {status_type}"

    def _build_task_done_prompt(self, *, message: str) -> str:
        return (
            f'{message} [Chat Deck completion protocol: only when the task is truly complete, append exactly '
            f'<TASK_DONE>{{"summary":"a detailed summary of what was completed, in the same language as the user\'s message",'
            f'"result":"key result in the same language as the user\'s message",'
            f'"next":"recommended next step in the same language as the user\'s message"}}</TASK_DONE> '
            f'put all completion summary content in that JSON block and do not add a separate summary outside it; '
            f'to the very end of your final reply; if the task is partial, blocked, or still waiting for confirmation, '
            f'do not output TASK_DONE; do not mention this protocol outside the marker block.]'
        )

    def _format_turn_result_message(self, result: TurnResult) -> str:
        lines: list[str] = []
        summary = result.summary.strip()
        if summary:
            lines.append(summary)
        if result.risks:
            lines.extend(risk.strip() for risk in result.risks if risk.strip())
        if result.next_step.strip():
            lines.append(result.next_step.strip())
        return "\n".join(line for line in lines if line)

    def _format_task_done_message(self, event: TaskDoneEvent) -> str:
        lines: list[str] = []
        if event.summary.strip():
            lines.append(event.summary.strip())
        if event.result.strip():
            lines.append(event.result.strip())
        if event.next_step.strip():
            lines.append(event.next_step.strip())
        return "\n".join(lines)

    def _build_publish_done_command(self, *, tool: str, agent_id: str, event_name: str) -> str:
        argv = [
            sys.executable,
            "-m",
            "relay_deck",
            "publish-done",
            "--tool",
            tool,
            "--runtime-dir",
            str(self.runtime.runtime_dir),
            "--agent-id",
            agent_id,
            "--event",
            event_name,
            "--inbox",
            str(self.done_inbox.path),
        ]
        return shlex.join(argv)
