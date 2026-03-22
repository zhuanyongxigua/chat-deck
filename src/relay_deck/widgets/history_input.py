from __future__ import annotations

from pathlib import Path

from textual.binding import Binding
from textual.message import Message
from textual.widgets import Input


def default_history_path() -> Path:
    return Path.home() / ".chat-deck" / "command-history.txt"


class HistoryInput(Input):
    PASTE_PREVIEW_THRESHOLD = 120

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
        start, end = self.selection
        if self._should_collapse_paste(text):
            placeholder = self._build_paste_placeholder(text)
            self._collapsed_pastes[placeholder] = text
            self.replace(placeholder, start, end)
            return
        self.replace(text, start, end)

    def expand_value(self, value: str | None = None) -> str:
        expanded = self.value if value is None else value
        for placeholder, original in sorted(self._collapsed_pastes.items(), key=lambda item: len(item[0]), reverse=True):
            expanded = expanded.replace(placeholder, original)
        return expanded

    def clear_collapsed_pastes(self) -> None:
        self._collapsed_pastes.clear()

    def _on_paste(self, event) -> None:
        self.insert_pasted_text(event.text)
        event.stop()

    def _should_collapse_paste(self, text: str) -> bool:
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
