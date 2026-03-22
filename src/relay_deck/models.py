from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import re
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


DISPLAY_NAME_STOP_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "continue",
    "current",
    "for",
    "from",
    "handle",
    "highlight",
    "inspect",
    "into",
    "look",
    "now",
    "of",
    "on",
    "open",
    "please",
    "recent",
    "remaining",
    "review",
    "run",
    "scan",
    "summarize",
    "summary",
    "tell",
    "that",
    "the",
    "this",
    "to",
    "update",
    "what",
    "with",
}


def humanize_handle(value: str) -> str:
    parts = [part for part in re.split(r"[-_]+", value.strip()) if part]
    if not parts:
        return "Agent"
    return " ".join(part.upper() if part.isupper() else part.capitalize() for part in parts)


def derive_display_name(prompt: str, fallback: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", prompt.lower())
    candidates = [
        word
        for word in words
        if word not in DISPLAY_NAME_STOP_WORDS and not word.isdigit() and len(word) > 1
    ]
    if not candidates:
        return fallback

    chosen = candidates[:3]
    return " ".join(word.upper() if len(word) <= 3 else word.capitalize() for word in chosen)


class ToolType(str, Enum):
    CLAUDE = "claude"
    CODEX = "codex"
    MOCK = "mock"

    @property
    def client_label(self) -> str:
        if self == ToolType.CLAUDE:
            return "Claude Code"
        if self == ToolType.CODEX:
            return "Codex"
        return "Demo"


class AgentState(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    ERROR = "error"
    UNKNOWN = "unknown"


def display_state_label(state: AgentState) -> str:
    if state == AgentState.WAITING:
        return AgentState.WORKING.value
    return state.value


class EventType(str, Enum):
    REGISTERED = "agent_registered"
    STARTED = "agent_started"
    OUTPUT = "agent_output"
    STATE_CHANGED = "agent_state_changed"
    SUMMARY_UPDATED = "agent_summary_updated"
    COMPLETED = "agent_completed"
    ERROR = "agent_error"
    MESSAGE_SENT = "agent_message_sent"
    CONTROLLER = "controller_message"


@dataclass(slots=True)
class AgentSpec:
    name: str
    tool_type: ToolType
    cwd: Path
    launch_command: list[str] | None = None
    agent_id: str | None = None


@dataclass(slots=True)
class AgentEvent:
    type: EventType
    agent_id: str | None
    message: str
    created_at: datetime = field(default_factory=utc_now)
    state: AgentState | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ConsoleLine:
    text: str
    style: str = "white"


@dataclass(slots=True)
class AgentRecord:
    agent_id: str
    name: str
    tool_type: ToolType
    cwd: Path
    session_name: str | None = None
    display_name: str = ""
    branch: str | None = None
    state: AgentState = AgentState.IDLE
    last_summary: str = ""
    unread_count: int = 0
    needs_attention: bool = False
    completed: bool = False
    awaiting_result: bool = False
    last_event_at: datetime = field(default_factory=utc_now)
    recent_output: deque[str] = field(default_factory=lambda: deque(maxlen=12))
    recent_events: deque[AgentEvent] = field(default_factory=lambda: deque(maxlen=32))
    transcript: deque[ConsoleLine] = field(default_factory=lambda: deque(maxlen=400))
    chat_transcript: deque[ConsoleLine] = field(default_factory=lambda: deque(maxlen=200))

    def bar_token(self) -> str:
        marker = {
            AgentState.IDLE: "I",
            AgentState.WORKING: "W",
            AgentState.WAITING: "W",
            AgentState.COMPLETED: "C",
            AgentState.BLOCKED: "B",
            AgentState.ERROR: "E",
            AgentState.UNKNOWN: "?",
        }[self.state]
        flags = ""
        if self.needs_attention:
            flags += "!"
        if self.unread_count:
            flags += "*"
        return f"{self.name}:{marker}{flags}"
