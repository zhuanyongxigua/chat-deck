from __future__ import annotations

from textual.widgets import DataTable

from relay_deck.models import AgentRecord


class AgentTable(DataTable):
    def __init__(self) -> None:
        super().__init__(id="agent-table", cursor_type="row")
        self.zebra_stripes = True
        self.add_columns("Name", "Tool", "State", "Unread", "Project")

    def refresh_records(self, records: list[AgentRecord]) -> None:
        self.clear(columns=False)
        for record in records:
            self.add_row(
                record.name,
                record.tool_type.value,
                record.state.value,
                str(record.unread_count),
                str(record.cwd),
                key=record.agent_id,
            )
