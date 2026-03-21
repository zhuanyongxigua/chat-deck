from __future__ import annotations

import re
from pathlib import Path

from relay_deck.models import ToolType
from relay_deck.router import RouterResult


class ControllerInterpreter:
    CREATE_KEYWORDS = (
        "create",
        "start",
        "spawn",
        "launch",
        "new agent",
        "new session",
        "创建",
        "新建",
        "启动",
        "开一个",
        "开启",
    )

    NAME_PATTERNS = (
        re.compile(r"\b(?:named|name)\s+(?P<name>[A-Za-z0-9_-]+)\b", re.IGNORECASE),
        re.compile(r"(?:叫|名为)(?P<name>[A-Za-z0-9_-]+)"),
    )

    PATH_PATTERN = re.compile(r"(?P<path>(?:~|/)[^\s,，。；;]+)")

    def interpret(self, text: str) -> RouterResult | None:
        if not text.strip():
            return None
        tool_type = self._detect_tool_type(text)
        cwd = self._detect_cwd(text)
        if tool_type is None or cwd is None or not self._looks_like_create_request(text):
            return None
        name = self._detect_name(text) or self._derive_name(tool_type, cwd)
        return RouterResult(
            kind="create_agent",
            tool_type=tool_type,
            name=name,
            cwd=cwd,
            message=text,
        )

    def _looks_like_create_request(self, text: str) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in self.CREATE_KEYWORDS)

    def _detect_tool_type(self, text: str) -> ToolType | None:
        lowered = text.lower()
        if "claude code" in lowered or "claude" in lowered:
            return ToolType.CLAUDE
        if "codex" in lowered:
            return ToolType.CODEX
        return None

    def _detect_name(self, text: str) -> str | None:
        for pattern in self.NAME_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group("name")
        return None

    def _detect_cwd(self, text: str) -> Path | None:
        match = self.PATH_PATTERN.search(text)
        if match is None:
            return None
        return Path(match.group("path")).expanduser()

    def _derive_name(self, tool_type: ToolType, cwd: Path) -> str:
        base = cwd.name or "workspace"
        normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", base).strip("-").lower() or "workspace"
        return f"{normalized}-{tool_type.value}"
