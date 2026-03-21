from __future__ import annotations

import asyncio
import contextlib
import re

from relay_deck.adapters.base import AgentAdapter
from relay_deck.models import AgentEvent, AgentState, AgentSpec, EventType
from relay_deck.tmux_manager import (
    TmuxCommandError,
    TmuxError,
    TmuxManager,
    TmuxPaneState,
    TmuxUnavailableError,
)


class TmuxAgentAdapter(AgentAdapter):
    def __init__(
        self,
        spec: AgentSpec,
        emit,
        tmux: TmuxManager,
        *,
        poll_interval: float = 0.6,
        snapshot_lines: int = 120,
    ) -> None:
        super().__init__(spec, emit)
        self.tmux = tmux
        self.poll_interval = poll_interval
        self.snapshot_lines = snapshot_lines
        self.session_name = self._make_session_name(spec)
        self._poll_task: asyncio.Task[None] | None = None
        self._last_snapshot: list[str] = []
        self._closed = False
        self._final_event_emitted = False

    async def start(self) -> None:
        command = self._build_command()
        try:
            await self.tmux.create_session(
                session_name=self.session_name,
                cwd=self.spec.cwd,
                command=command,
            )
        except TmuxUnavailableError:
            self._closed = True
            await self._emit_error("tmux is required to run Claude Code or Codex agents")
            return
        except (TmuxCommandError, ValueError) as exc:
            self._closed = True
            await self._emit_error(f"Failed to start tmux session: {exc}")
            return

        await self.emit(
            AgentEvent(
                type=EventType.STARTED,
                agent_id=self.spec.agent_id,
                message=f"tmux session ready: {self.session_name}",
                state=AgentState.IDLE,
                payload={
                    "command": command,
                    "session_name": self.session_name,
                    "cwd": str(self.spec.cwd),
                },
            )
        )
        await self.emit(
            AgentEvent(
                type=EventType.SUMMARY_UPDATED,
                agent_id=self.spec.agent_id,
                message=f"Running inside tmux session {self.session_name}",
            )
        )
        await self.emit(
            AgentEvent(
                type=EventType.STATE_CHANGED,
                agent_id=self.spec.agent_id,
                message="Agent session is idle",
                state=AgentState.IDLE,
            )
        )
        self._poll_task = asyncio.create_task(self._poll_session())

    async def send(self, message: str) -> None:
        if self._closed:
            await self._emit_error("tmux session is not running")
            return
        try:
            await self.tmux.send_text(self.session_name, message)
        except (TmuxUnavailableError, TmuxCommandError) as exc:
            await self._emit_error(f"Failed to send input to tmux session: {exc}")
            return

        await self.emit(
            AgentEvent(
                type=EventType.MESSAGE_SENT,
                agent_id=self.spec.agent_id,
                message=message,
                state=AgentState.WORKING,
                payload={"session_name": self.session_name},
            )
        )
        await self.emit(
            AgentEvent(
                type=EventType.STATE_CHANGED,
                agent_id=self.spec.agent_id,
                message="Input injected into tmux session",
                state=AgentState.WORKING,
            )
        )

    async def interrupt(self) -> None:
        if self._closed:
            return
        try:
            await self.tmux.send_interrupt(self.session_name)
        except (TmuxUnavailableError, TmuxCommandError) as exc:
            await self._emit_error(f"Failed to interrupt tmux session: {exc}")
            return
        await self.emit(
            AgentEvent(
                type=EventType.STATE_CHANGED,
                agent_id=self.spec.agent_id,
                message="Interrupt sent to tmux session",
                state=AgentState.WAITING,
            )
        )

    async def stop(self) -> None:
        self._closed = True
        if self._poll_task is not None:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
        with contextlib.suppress(TmuxError):
            await self.tmux.destroy_session(self.session_name)

    def _build_command(self) -> list[str]:
        if self.spec.launch_command:
            return self.spec.launch_command
        raise NotImplementedError("Subclasses must provide a default launch command")

    async def _poll_session(self) -> None:
        while not self._closed:
            try:
                snapshot = await self.tmux.capture_snapshot(self.session_name, lines=self.snapshot_lines)
                await self._emit_snapshot_delta(snapshot)
                pane_state = await self.tmux.pane_state(self.session_name)
            except TmuxUnavailableError:
                await self._emit_error("tmux became unavailable")
                return
            except TmuxCommandError as exc:
                await self._emit_error(f"tmux polling failed: {exc}")
                return

            if await self._handle_pane_state(pane_state):
                return
            await asyncio.sleep(self.poll_interval)

    async def _emit_snapshot_delta(self, snapshot: list[str]) -> None:
        new_lines = self._new_lines(snapshot)
        for line in new_lines:
            if not line.strip():
                continue
            await self.emit(
                AgentEvent(
                    type=EventType.OUTPUT,
                    agent_id=self.spec.agent_id,
                    message=line,
                    state=AgentState.WORKING,
                    payload={
                        "stream": "pane",
                        "session_name": self.session_name,
                    },
                )
            )

    async def _handle_pane_state(self, pane_state: TmuxPaneState) -> bool:
        if not pane_state.session_exists:
            self._closed = True
            if not self._final_event_emitted:
                await self._emit_error("tmux session disappeared")
            return True
        if not pane_state.pane_dead:
            return False
        self._closed = True
        exit_status = pane_state.exit_status or 0
        self._final_event_emitted = True
        event_type = EventType.COMPLETED if exit_status == 0 else EventType.ERROR
        state = AgentState.COMPLETED if exit_status == 0 else AgentState.ERROR
        await self.emit(
            AgentEvent(
                type=event_type,
                agent_id=self.spec.agent_id,
                message=f"tmux pane exited with code {exit_status}",
                state=state,
                payload={"session_name": self.session_name},
            )
        )
        return True

    def _new_lines(self, snapshot: list[str]) -> list[str]:
        if not self._last_snapshot:
            self._last_snapshot = list(snapshot)
            return list(snapshot)
        overlap = 0
        max_overlap = min(len(self._last_snapshot), len(snapshot))
        for size in range(max_overlap, 0, -1):
            if self._last_snapshot[-size:] == snapshot[:size]:
                overlap = size
                break
        self._last_snapshot = list(snapshot)
        return snapshot[overlap:]

    async def _emit_error(self, message: str) -> None:
        self._closed = True
        self._final_event_emitted = True
        await self.emit(
            AgentEvent(
                type=EventType.ERROR,
                agent_id=self.spec.agent_id,
                message=message,
                state=AgentState.ERROR,
                payload={"session_name": self.session_name},
            )
        )

    def _make_session_name(self, spec: AgentSpec) -> str:
        base = f"relay-{spec.tool_type.value}-{spec.name}"
        if spec.agent_id:
            base = f"{base}-{spec.agent_id}"
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", base).strip("-")
        return normalized[:64] or "relay-agent"
