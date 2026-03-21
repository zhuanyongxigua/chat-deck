from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass
from pathlib import Path


class TmuxError(RuntimeError):
    pass


class TmuxUnavailableError(TmuxError):
    pass


class TmuxCommandError(TmuxError):
    pass


@dataclass(slots=True)
class TmuxCommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(slots=True)
class TmuxPaneState:
    session_exists: bool
    pane_dead: bool = False
    exit_status: int | None = None


class TmuxManager:
    def __init__(self, binary: str = "tmux") -> None:
        self.binary = binary
        self._available: bool | None = None

    async def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            result = await self._run("-V", check=False)
        except TmuxUnavailableError:
            self._available = False
            return False
        self._available = result.returncode == 0
        return self._available

    async def create_session(self, *, session_name: str, cwd: Path, command: list[str]) -> None:
        if not command:
            raise ValueError("tmux session command cannot be empty")
        await self._run(
            "new-session",
            "-d",
            "-s",
            session_name,
            "-c",
            str(cwd),
            self._shell_command(command),
        )
        await self._run(
            "set-window-option",
            "-t",
            session_name,
            "remain-on-exit",
            "on",
            check=False,
        )

    async def destroy_session(self, session_name: str) -> None:
        if not await self.has_session(session_name):
            return
        await self._run("kill-session", "-t", session_name, check=False)

    async def has_session(self, session_name: str) -> bool:
        result = await self._run("has-session", "-t", session_name, check=False)
        return result.returncode == 0

    async def send_text(self, session_name: str, text: str) -> None:
        await self._run("send-keys", "-t", session_name, "-l", text)
        await self._run("send-keys", "-t", session_name, "Enter")

    async def send_interrupt(self, session_name: str) -> None:
        await self._run("send-keys", "-t", session_name, "C-c")

    async def capture_snapshot(self, session_name: str, *, lines: int = 120) -> list[str]:
        if not await self.has_session(session_name):
            return []
        result = await self._run(
            "capture-pane",
            "-p",
            "-J",
            "-S",
            f"-{max(lines, 1)}",
            "-t",
            session_name,
            check=False,
        )
        if result.returncode != 0:
            return []
        return result.stdout.splitlines()

    async def pane_state(self, session_name: str) -> TmuxPaneState:
        if not await self.has_session(session_name):
            return TmuxPaneState(session_exists=False)
        result = await self._run(
            "display-message",
            "-p",
            "-t",
            session_name,
            "#{pane_dead} #{pane_dead_status}",
            check=False,
        )
        if result.returncode != 0:
            return TmuxPaneState(session_exists=False)
        parts = result.stdout.strip().split()
        pane_dead = bool(parts and parts[0] == "1")
        exit_status = None
        if pane_dead and len(parts) > 1:
            try:
                exit_status = int(parts[1])
            except ValueError:
                exit_status = None
        return TmuxPaneState(session_exists=True, pane_dead=pane_dead, exit_status=exit_status)

    async def attach_session(self, session_name: str) -> None:
        proc = await asyncio.create_subprocess_exec(self.binary, "attach-session", "-t", session_name)
        await proc.wait()

    async def _run(self, *args: str, check: bool = True) -> TmuxCommandResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise TmuxUnavailableError("tmux executable not found") from exc

        stdout, stderr = await proc.communicate()
        result = TmuxCommandResult(
            returncode=proc.returncode,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
        )
        if check and result.returncode != 0:
            raise TmuxCommandError(result.stderr.strip() or f"tmux {' '.join(args)} failed")
        return result

    def _shell_command(self, command: list[str]) -> str:
        return f"exec {shlex.join(command)}"
