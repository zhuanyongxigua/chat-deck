from __future__ import annotations

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from textual import events
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Static

from relay_deck.models import AgentRecord, AgentState, display_state_label


class AgentCard(Static):
    SPINNER_FRAMES = ("◐", "◓", "◑", "◒")

    class Selected(Message):
        def __init__(self, agent_id: str) -> None:
            self.agent_id = agent_id
            super().__init__()

    def __init__(self, record: AgentRecord, *, animation_tick: int = 0, active: bool = False) -> None:
        super().__init__(classes="agent-card")
        self.record = record
        self.animation_tick = animation_tick
        self.active = active
        self.can_focus = False
        self._refresh_content()

    def update_card(self, record: AgentRecord, *, animation_tick: int, active: bool) -> None:
        self.record = record
        self.animation_tick = animation_tick
        self.active = active
        self._refresh_content()

    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.post_message(self.Selected(self.record.agent_id))

    def _refresh_content(self) -> None:
        dot, dot_style = self._status_dot(self.record.state, self.animation_tick)
        status_label = self._status_label(self.record.state)

        handle = Text.assemble(("@", "bold white"), (self.record.name, "bold cyan"))
        client = Text.assemble(("client ", "dim"), (self.record.tool_type.client_label, "white"))
        directory = Text.assemble(("dir ", "dim"), (str(self.record.cwd), "white"))
        status = Text.assemble((dot, dot_style), ("  ", ""), (status_label, "white"))

        self.update(
            Panel(
                Group(handle, client, directory, status),
                box=box.ROUNDED,
                border_style=self._border_style(self.record.state, self.active),
                padding=(0, 1),
            )
        )

    def _status_dot(self, state: AgentState, animation_tick: int) -> tuple[str, str]:
        if state == AgentState.ERROR:
            return "●", "bold red"
        if state == AgentState.COMPLETED:
            return "●", "bold green"
        if state == AgentState.IDLE:
            return "●", "bold yellow"
        if state in {AgentState.WAITING, AgentState.WORKING}:
            return self.SPINNER_FRAMES[animation_tick % len(self.SPINNER_FRAMES)], "bold green"
        return ("●" if animation_tick % 2 == 0 else " ", "bold green")

    def _status_label(self, state: AgentState) -> str:
        if state == AgentState.COMPLETED:
            return "ready"
        if state == AgentState.ERROR:
            return "error"
        if state == AgentState.BLOCKED:
            return "blocked"
        if state == AgentState.IDLE:
            return "idle"
        return display_state_label(state)

    def _border_style(self, state: AgentState, active: bool) -> str:
        if active:
            return "#3E7F5D"
        return "#7FB3FF"


class AgentSidebar(VerticalScroll):
    class BackgroundSelected(Message):
        pass

    def __init__(self) -> None:
        super().__init__(id="agent-sidebar")
        self._cards: dict[str, AgentCard] = {}
        self._order: list[str] = []
        self._placeholder = Static(
            "No agents yet.\n\nUse /new <codex|claude> <name> <cwd>\nor say: create a codex session in /path/to/project",
            id="agent-sidebar-placeholder",
        )

    def on_mount(self) -> None:
        self.mount(self._placeholder)

    def set_records(self, records: list[AgentRecord], animation_tick: int, active_agent_id: str | None) -> None:
        incoming_order = [record.agent_id for record in records]

        if not records:
            for card in self._cards.values():
                card.remove()
            self._cards.clear()
            self._order = []
            if self._placeholder.parent is None:
                self.mount(self._placeholder)
            return

        if self._placeholder.parent is not None:
            self._placeholder.remove()

        removed = set(self._cards) - set(incoming_order)
        for agent_id in removed:
            self._cards.pop(agent_id).remove()

        for record in records:
            card = self._cards.get(record.agent_id)
            if card is None:
                card = AgentCard(
                    record,
                    animation_tick=animation_tick,
                    active=record.agent_id == active_agent_id,
                )
                self._cards[record.agent_id] = card
                self.mount(card)
            else:
                card.update_card(record, animation_tick=animation_tick, active=record.agent_id == active_agent_id)

        if incoming_order:
            first_card = self._cards[incoming_order[0]]
            mounted_cards = [child for child in self.children if isinstance(child, AgentCard)]
            if mounted_cards and mounted_cards[0] is not first_card:
                self.move_child(first_card, before=mounted_cards[0])

            previous = first_card
            for agent_id in incoming_order[1:]:
                card = self._cards[agent_id]
                self.move_child(card, after=previous)
                previous = card

        self._order = list(incoming_order)

    def on_click(self, event: events.Click) -> None:
        if isinstance(getattr(event, "widget", None), AgentCard):
            return
        self.post_message(self.BackgroundSelected())
