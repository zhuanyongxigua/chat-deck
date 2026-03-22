from __future__ import annotations

from textual.widgets import Static

from relay_deck.models import AgentRecord, display_state_label


class DetailPanel(Static):
    def __init__(self) -> None:
        super().__init__(id="detail-panel")
        self.show_placeholder()

    def show_placeholder(self) -> None:
        self.update("Select an agent to inspect its summary, recent events, and tmux snapshot.")

    def show_record(self, record: AgentRecord | None, *, snapshot_lines: list[str] | None = None) -> None:
        if record is None:
            self.show_placeholder()
            return

        summary = record.last_summary or "(no summary yet)"
        recent_events = "\n".join(
            f"[{event.created_at.strftime('%H:%M:%S')}] {event.type.value}: {event.message}"
            for event in list(record.recent_events)[-6:]
        ) or "(no events yet)"
        snapshot = "\n".join(snapshot_lines or []) or "(no snapshot yet)"
        transcript = "\n".join(line.text for line in list(record.transcript)[-6:]) or "(no transcript yet)"
        text = "\n".join(
            [
                f"State: {display_state_label(record.state)}",
                f"Client: {record.tool_type.client_label}",
                f"Branch: {record.branch or '-'}",
                f"CWD: {record.cwd}",
                f"Session: {record.session_name or '-'}",
                "",
                "Summary",
                summary,
                "",
                "Recent Events",
                recent_events,
                "",
                "Pane Snapshot",
                snapshot,
                "",
                "Transcript Tail",
                transcript,
            ]
        )

        self.update(text)
