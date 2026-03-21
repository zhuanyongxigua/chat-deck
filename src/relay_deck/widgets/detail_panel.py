from __future__ import annotations

from textual.widgets import Static

from relay_deck.models import AgentRecord


class DetailPanel(Static):
    def __init__(self) -> None:
        super().__init__(id="detail-panel")
        self.show_placeholder()

    def show_placeholder(self) -> None:
        self.update("Select an agent to inspect its summary, status, and recent output.")

    def show_record(self, record: AgentRecord | None) -> None:
        if record is None:
            self.show_placeholder()
            return

        output_lines = "\n".join(record.recent_output) or "(no output yet)"
        events = "\n".join(
            f"[{event.created_at.strftime('%H:%M:%S')}] {event.type.value}: {event.message}"
            for event in list(record.recent_events)[-8:]
        ) or "(no events yet)"

        text = (
            f"Name: {record.name}\n"
            f"Tool: {record.tool_type.value}\n"
            f"State: {record.state.value}\n"
            f"Branch: {record.branch or '-'}\n"
            f"CWD: {record.cwd}\n"
            f"Unread: {record.unread_count}\n"
            f"Needs Attention: {'yes' if record.needs_attention else 'no'}\n"
            f"Completed: {'yes' if record.completed else 'no'}\n\n"
            f"Summary\n"
            f"{record.last_summary or '(no summary yet)'}\n\n"
            f"Recent Output\n"
            f"{output_lines}\n\n"
            f"Recent Events\n"
            f"{events}"
        )
        self.update(text)

