from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from asyncio.subprocess import Process

from relay_deck.adapters.base import AgentAdapter
from relay_deck.models import AgentEvent, AgentState, AgentSpec, EventType


class CliAgentAdapter(AgentAdapter):
    def __init__(self, spec: AgentSpec, emit) -> None:
        super().__init__(spec, emit)
        self._process: Process | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        command = self._build_command()
        try:
            self._process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(self.spec.cwd),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._build_env(),
            )
        except FileNotFoundError:
            await self.emit(
                AgentEvent(
                    type=EventType.ERROR,
                    agent_id=self.spec.agent_id,
                    message=f"Executable not found: {command[0]}",
                    state=AgentState.ERROR,
                )
            )
            return
        except Exception as exc:
            await self.emit(
                AgentEvent(
                    type=EventType.ERROR,
                    agent_id=self.spec.agent_id,
                    message=f"Failed to start agent: {exc}",
                    state=AgentState.ERROR,
                )
            )
            return

        await self.emit(
            AgentEvent(
                type=EventType.STARTED,
                agent_id=self.spec.agent_id,
                message="Agent process started",
                state=AgentState.IDLE,
                payload={"command": command},
            )
        )
        await self.emit(
            AgentEvent(
                type=EventType.STATE_CHANGED,
                agent_id=self.spec.agent_id,
                message="Agent is idle",
                state=AgentState.IDLE,
            )
        )

        if self._process.stdout is not None:
            self._stdout_task = asyncio.create_task(self._consume_stream(self._process.stdout, is_error=False))
        if self._process.stderr is not None:
            self._stderr_task = asyncio.create_task(self._consume_stream(self._process.stderr, is_error=True))
        asyncio.create_task(self._watch_process())

    async def send(self, message: str) -> None:
        if self._process is None or self._process.stdin is None:
            await self.emit(
                AgentEvent(
                    type=EventType.ERROR,
                    agent_id=self.spec.agent_id,
                    message="Agent process is not running",
                    state=AgentState.ERROR,
                )
            )
            return

        try:
            self._process.stdin.write(f"{message}\n".encode())
            await self._process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            await self.emit(
                AgentEvent(
                    type=EventType.ERROR,
                    agent_id=self.spec.agent_id,
                    message="Agent process closed its stdin",
                    state=AgentState.ERROR,
                )
            )
            return
        await self.emit(
            AgentEvent(
                type=EventType.MESSAGE_SENT,
                agent_id=self.spec.agent_id,
                message=message,
                state=AgentState.WORKING,
            )
        )
        await self.emit(
            AgentEvent(
                type=EventType.STATE_CHANGED,
                agent_id=self.spec.agent_id,
                message="Agent is processing input",
                state=AgentState.WORKING,
            )
        )

    async def interrupt(self) -> None:
        if self._process is None:
            return
        self._process.send_signal(signal.SIGINT)
        await self.emit(
            AgentEvent(
                type=EventType.STATE_CHANGED,
                agent_id=self.spec.agent_id,
                message="Interrupt sent",
                state=AgentState.WAITING,
            )
        )

    async def stop(self) -> None:
        if self._process is not None and self._process.returncode is None:
            self._process.terminate()
            await self._process.wait()
        for task in (self._stdout_task, self._stderr_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    def _build_command(self) -> list[str]:
        if self.spec.launch_command:
            return self.spec.launch_command
        raise NotImplementedError("Subclasses must provide a default launch command")

    def _build_env(self) -> dict[str, str]:
        return dict(os.environ)

    async def _consume_stream(self, stream: asyncio.StreamReader, *, is_error: bool) -> None:
        while True:
            line = await stream.readline()
            if not line:
                return
            text = line.decode(errors="replace").rstrip()
            if not text:
                continue
            event_type = EventType.OUTPUT
            state = self._infer_state(text) if not is_error else AgentState.WORKING
            payload = {"stream": "stderr" if is_error else "stdout"}
            await self.emit(
                AgentEvent(
                    type=event_type,
                    agent_id=self.spec.agent_id,
                    message=text if not is_error else f"[stderr] {text}",
                    state=state,
                    payload=payload,
                )
            )
            if not is_error and state not in {AgentState.UNKNOWN, AgentState.WORKING}:
                await self.emit(
                    AgentEvent(
                        type=EventType.STATE_CHANGED,
                        agent_id=self.spec.agent_id,
                        message=text,
                        state=state,
                    )
                )
            elif not is_error:
                await self.emit(
                    AgentEvent(
                        type=EventType.SUMMARY_UPDATED,
                        agent_id=self.spec.agent_id,
                        message=text,
                    )
                )

    async def _watch_process(self) -> None:
        if self._process is None:
            return
        code = await self._process.wait()
        message = f"Process exited with code {code}"
        event_type = EventType.COMPLETED if code == 0 else EventType.ERROR
        state = AgentState.COMPLETED if code == 0 else AgentState.ERROR
        await self.emit(
            AgentEvent(
                type=event_type,
                agent_id=self.spec.agent_id,
                message=message,
                state=state,
            )
        )

    def _infer_state(self, text: str) -> AgentState:
        normalized = text.lower()
        if "waiting" in normalized or "input needed" in normalized:
            return AgentState.WAITING
        if "blocked" in normalized:
            return AgentState.BLOCKED
        if "complete" in normalized or "done" in normalized or "finished" in normalized:
            return AgentState.COMPLETED
        if "idle" in normalized:
            return AgentState.IDLE
        return AgentState.WORKING
