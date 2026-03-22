from __future__ import annotations

import re
import time
from pathlib import Path

from textual import events
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Input


def default_history_path() -> Path:
    return Path.home() / ".chat-deck" / "command-history.txt"


class HistoryInput(Input):
    PASTE_PREVIEW_THRESHOLD = 120
    PASTE_PLACEHOLDER_RE = re.compile(r"^\[Pasted Content \d+ chars(?: #\d+)?\]$")
    PASTE_DEDUP_WINDOW_SECONDS = 0.25
    PASTE_FOLLOWUP_SUPPRESSION_SECONDS = 0.35

    class CommandSuggestionRequested(Message):
        def __init__(self, *, reverse: bool = False) -> None:
            self.reverse = reverse
            super().__init__()

    BINDINGS = [
        *Input.BINDINGS,
        Binding("up", "history_previous", "Previous history", show=False),
        Binding("down", "history_next", "Next history", show=False),
        Binding("tab", "request_command_suggestion", "Accept suggestion", show=False),
        Binding("shift+tab", "request_command_suggestion(True)", "Previous suggestion", show=False),
    ]

    def __init__(
        self,
        *args,
        history_path: Path | None = None,
        history_limit: int = 100,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.history_path = history_path or default_history_path()
        self.history_limit = max(1, history_limit)
        self._history: list[str] = []
        self._history_index: int | None = None
        self._history_draft = ""
        self._collapsed_pastes: dict[str, str] = {}
        self._bypass_paste_collapse = False
        self._last_paste_text = ""
        self._last_paste_at = 0.0
        self._suppressed_paste_text = ""
        self._suppressed_paste_placeholder = ""
        self._suppressed_paste_offset = 0
        self._suppress_followup_until = 0.0
        self._load_history()

    def remember(self, value: str) -> None:
        text = value.rstrip("\n")
        if not text.strip():
            self.reset_history_navigation()
            return
        if not self._history or self._history[-1] != text:
            self._history.append(text)
            if len(self._history) > self.history_limit:
                self._history = self._history[-self.history_limit :]
            self._save_history()
        self.reset_history_navigation()

    def reset_history_navigation(self) -> None:
        self._history_index = None
        self._history_draft = ""

    def action_history_previous(self) -> None:
        if not self._history:
            return
        if self._history_index is None:
            self._history_draft = self.value
            self._history_index = len(self._history) - 1
        else:
            self._history_index = max(0, self._history_index - 1)
        self._apply_history_value(self._history[self._history_index])

    def action_history_next(self) -> None:
        if self._history_index is None:
            return
        if self._history_index >= len(self._history) - 1:
            draft = self._history_draft
            self.reset_history_navigation()
            self._apply_history_value(draft)
            return
        self._history_index += 1
        self._apply_history_value(self._history[self._history_index])

    def action_request_command_suggestion(self, reverse: bool = False) -> None:
        self.post_message(self.CommandSuggestionRequested(reverse=reverse))

    def _apply_history_value(self, value: str) -> None:
        self.value = value
        self.cursor_position = len(self.value)

    def insert_pasted_text(self, text: str) -> None:
        if not text:
            return
        if self._is_duplicate_paste(text):
            return
        start, end = self.selection
        self._replace_with_paste_awareness(text, start, end)
        self._mark_recent_paste(text)

    def replace(self, text: str, start: int, end: int) -> None:
        if self._should_ignore_followup_text(text):
            return
        self._replace_with_paste_awareness(text, start, end)

    def insert_text_at_cursor(self, text: str) -> None:
        if self._should_ignore_followup_text(text):
            return
        if self._bypass_paste_collapse or not self._should_collapse_paste(text):
            super().insert_text_at_cursor(text)
            return
        placeholder = self._store_collapsed_paste(text)
        self._activate_followup_suppression(placeholder, text)
        self._bypass_paste_collapse = True
        try:
            super().insert_text_at_cursor(placeholder)
        finally:
            self._bypass_paste_collapse = False

    def expand_value(self, value: str | None = None) -> str:
        expanded = self.value if value is None else value
        for placeholder, original in sorted(self._collapsed_pastes.items(), key=lambda item: len(item[0]), reverse=True):
            expanded = expanded.replace(placeholder, original)
        return expanded

    def clear_collapsed_pastes(self) -> None:
        self._collapsed_pastes.clear()
        self._suppressed_paste_text = ""
        self._suppressed_paste_placeholder = ""
        self._suppressed_paste_offset = 0
        self._suppress_followup_until = 0.0

    def _on_paste(self, event: events.Paste) -> None:
        self.insert_pasted_text(event.text)
        event.stop()

    def _should_collapse_paste(self, text: str) -> bool:
        if not text:
            return False
        if self.PASTE_PLACEHOLDER_RE.fullmatch(text):
            return False
        return "\n" in text or len(text) >= self.PASTE_PREVIEW_THRESHOLD

    def _build_paste_placeholder(self, text: str) -> str:
        length = len(text)
        base = f"[Pasted Content {length} chars]"
        if base not in self._collapsed_pastes:
            return base
        if self._collapsed_pastes.get(base) == text:
            return base
        counter = 2
        while True:
            candidate = f"[Pasted Content {length} chars #{counter}]"
            if candidate not in self._collapsed_pastes:
                return candidate
            if self._collapsed_pastes.get(candidate) == text:
                return candidate
            counter += 1

    def _store_collapsed_paste(self, text: str) -> str:
        placeholder = self._build_paste_placeholder(text)
        self._collapsed_pastes[placeholder] = text
        return placeholder

    def _is_duplicate_paste(self, text: str) -> bool:
        now = time.monotonic()
        return (
            text == self._last_paste_text
            and (now - self._last_paste_at) <= self.PASTE_DEDUP_WINDOW_SECONDS
        )

    def _mark_recent_paste(self, text: str) -> None:
        self._last_paste_text = text
        self._last_paste_at = time.monotonic()

    def _replace_with_paste_awareness(self, text: str, start: int, end: int) -> None:
        if self._bypass_paste_collapse or not self._should_collapse_paste(text):
            super().replace(text, start, end)
            return
        placeholder = self._store_collapsed_paste(text)
        self._activate_followup_suppression(placeholder, text)
        self._bypass_paste_collapse = True
        try:
            super().replace(placeholder, start, end)
        finally:
            self._bypass_paste_collapse = False

    def _activate_followup_suppression(self, placeholder: str, text: str) -> None:
        self._suppressed_paste_text = text
        self._suppressed_paste_placeholder = placeholder
        self._suppressed_paste_offset = 0
        self._suppress_followup_until = time.monotonic() + self.PASTE_FOLLOWUP_SUPPRESSION_SECONDS

    def _should_ignore_followup_text(self, text: str) -> bool:
        if not text:
            return False
        if time.monotonic() > self._suppress_followup_until:
            return False
        if not self._suppressed_paste_text or not self._suppressed_paste_placeholder:
            return False
        if self._suppressed_paste_placeholder not in self.value:
            return False
        start = self._suppressed_paste_offset
        expected = self._suppressed_paste_text[start : start + len(text)]
        if text != expected:
            return False
        self._suppressed_paste_offset += len(text)
        return True

    def _load_history(self) -> None:
        try:
            if not self.history_path.exists():
                return
            lines = [
                line.rstrip("\n")
                for line in self.history_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except OSError:
            return
        self._history = lines[-self.history_limit :]

    def _save_history(self) -> None:
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            payload = "\n".join(self._history[-self.history_limit :])
            if payload:
                payload = f"{payload}\n"
            self.history_path.write_text(payload, encoding="utf-8")
        except OSError:
            return
