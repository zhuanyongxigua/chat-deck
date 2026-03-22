from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from relay_deck.models import AgentRecord, AgentState


class StatusBar(Static):
    DEFAULT_TEXT = "No agents running"
    SPINNER_FRAMES = ("◐", "◓", "◑", "◒")

    def __init__(self) -> None:
        super().__init__(self.DEFAULT_TEXT, id="status-bar")

    def set_records(self, records: list[AgentRecord], animation_tick: int) -> None:
        if not records:
            self.update(self.DEFAULT_TEXT)
            return

        text = Text()
        for index, record in enumerate(records):
            if index:
                text.append("   ", style="dim")
            dot, style = self._status_dot(record.state, animation_tick)
            text.append(dot, style=style)
            text.append(" ")
            text.append(f"@{record.name}", style="bold white")
        self.update(text)

    def _status_dot(self, state: AgentState, animation_tick: int) -> tuple[str, str]:
        if state == AgentState.ERROR:
            return "●", "bold red"
        if state == AgentState.COMPLETED:
            return "●", "bold green"
        if state == AgentState.IDLE:
            return "●", "bold yellow"
        if state == AgentState.WAITING:
            return self.SPINNER_FRAMES[animation_tick % len(self.SPINNER_FRAMES)], "bold yellow"
        if state == AgentState.UNKNOWN:
            return "●" if animation_tick % 2 == 0 else " ", "bold green"
        return "●" if animation_tick % 2 == 0 else " ", "bold green"
