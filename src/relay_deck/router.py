from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

from relay_deck.models import ToolType


@dataclass(slots=True)
class RouterResult:
    kind: str
    target: str | None = None
    message: str | None = None
    tool_type: ToolType | None = None
    cwd: Path | None = None
    name: str | None = None


class InputRouter:
    USER_CREATABLE_TOOLS = {
        "claude": ToolType.CLAUDE,
        "codex": ToolType.CODEX,
    }

    def parse(self, raw: str) -> RouterResult:
        text = raw.strip()
        if not text:
            return RouterResult(kind="empty")

        if text.startswith("@"):
            target, _, message = text[1:].partition(" ")
            return RouterResult(
                kind="agent_message",
                target=target.strip() or None,
                message=message.strip(),
            )

        if text.startswith("/"):
            return self._parse_command(text)

        return RouterResult(kind="controller_message", message=text)

    def _parse_command(self, text: str) -> RouterResult:
        parts = shlex.split(text)
        if not parts:
            return RouterResult(kind="empty")

        command = parts[0]
        if command == "/help":
            return RouterResult(kind="help")
        if command == "/agents":
            return RouterResult(kind="agents")
        if command == "/attach":
            if len(parts) > 2:
                return RouterResult(kind="invalid", message="Usage: /attach [agent-name]")
            target = parts[1] if len(parts) == 2 else None
            if target and target.startswith("@"):
                target = target[1:]
            return RouterResult(kind="attach_agent", target=target or None)
        if command == "/new":
            if len(parts) < 4:
                return RouterResult(kind="invalid", message="Usage: /new <codex|claude> <name> <cwd>")
            tool_token = parts[1].lower()
            tool_type = self.USER_CREATABLE_TOOLS.get(tool_token)
            if tool_type is None:
                return RouterResult(kind="invalid", message=f"Unsupported client: {tool_token}. Use codex or claude.")
            return RouterResult(
                kind="create_agent",
                tool_type=tool_type,
                name=parts[2],
                cwd=Path(parts[3]).expanduser(),
            )
        return RouterResult(kind="invalid", message=f"Unknown command: {command}")
