from __future__ import annotations

from textual.binding import Binding
from textual.widgets import Input


class HistoryInput(Input):
    BINDINGS = [
        *Input.BINDINGS,
        Binding("up", "history_previous", "Previous history", show=False),
        Binding("down", "history_next", "Next history", show=False),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._history: list[str] = []
        self._history_index: int | None = None
        self._history_draft = ""

    def remember(self, value: str) -> None:
        text = value.rstrip("\n")
        if not text.strip():
            self.reset_history_navigation()
            return
        if not self._history or self._history[-1] != text:
            self._history.append(text)
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

    def _apply_history_value(self, value: str) -> None:
        self.value = value
        self.cursor_position = len(self.value)
