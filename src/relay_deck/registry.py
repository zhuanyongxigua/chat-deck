from __future__ import annotations

import copy
from pathlib import Path

from relay_deck.models import (
    AgentEvent,
    AgentRecord,
    AgentState,
    ConsoleLine,
    EventType,
    ToolType,
    derive_display_name,
    humanize_handle,
    utc_now,
)


class AgentRegistry:
    def __init__(self) -> None:
        self._records: dict[str, AgentRecord] = {}

    def register(
        self,
        *,
        agent_id: str,
        name: str,
        tool_type: ToolType,
        cwd: Path,
        branch: str | None,
    ) -> AgentRecord:
        record = AgentRecord(
            agent_id=agent_id,
            name=name,
            tool_type=tool_type,
            cwd=cwd,
            display_name=humanize_handle(name),
            branch=branch,
        )
        self._records[agent_id] = record
        return record

    def get(self, agent_id: str) -> AgentRecord | None:
        record = self._records.get(agent_id)
        if record is None:
            return None
        return copy.deepcopy(record)

    def get_by_name(self, name: str) -> AgentRecord | None:
        for record in self._records.values():
            if record.name == name:
                return copy.deepcopy(record)
        return None

    def list(self) -> list[AgentRecord]:
        return sorted(
            (copy.deepcopy(record) for record in self._records.values()),
            key=lambda item: (item.name.lower(), item.agent_id),
        )

    def mark_read(self, agent_id: str) -> None:
        record = self._records.get(agent_id)
        if record is not None:
            record.unread_count = 0

    def apply_event(self, event: AgentEvent) -> None:
        if event.type == EventType.CONTROLLER:
            return
        if event.agent_id is None:
            return

        record = self._records.get(event.agent_id)
        if record is None:
            return

        record.last_event_at = event.created_at
        record.recent_events.append(event)
        transcript_line = self._transcript_line_for_event(event)
        if transcript_line is not None:
            record.transcript.append(transcript_line)

        if event.type == EventType.OUTPUT:
            if event.message.strip():
                record.recent_output.append(event.message.rstrip())
            record.unread_count += 1
        elif event.type == EventType.SUMMARY_UPDATED:
            record.last_summary = event.message
            record.unread_count += 1
            record.awaiting_result = False
            if event.message:
                record.chat_transcript.append(ConsoleLine(text=event.message, style="white"))
        elif event.type == EventType.MESSAGE_SENT:
            record.state = AgentState.WORKING
            record.needs_attention = False
            record.completed = False
            record.awaiting_result = True
            record.recent_output.clear()
            if not record.recent_output and not record.last_summary:
                record.display_name = derive_display_name(event.message, record.display_name or humanize_handle(record.name))
            record.chat_transcript.append(ConsoleLine(text=f"> {event.message}", style="bold cyan"))
        elif event.type == EventType.STATE_CHANGED and event.state is not None:
            record.state = event.state
            record.needs_attention = event.state in {
                AgentState.WAITING,
                AgentState.BLOCKED,
                AgentState.ERROR,
            }
            record.completed = event.state == AgentState.COMPLETED
        elif event.type == EventType.COMPLETED:
            record.state = AgentState.COMPLETED
            record.completed = True
            record.needs_attention = False
            record.awaiting_result = False
            record.unread_count += 1
        elif event.type == EventType.ERROR:
            record.state = AgentState.ERROR
            record.needs_attention = True
            record.awaiting_result = False
            if event.message:
                record.last_summary = event.message
                record.chat_transcript.append(ConsoleLine(text=event.message, style="bold red"))
            record.unread_count += 1

        if event.payload.get("branch"):
            record.branch = str(event.payload["branch"])
        if event.payload.get("session_name"):
            record.session_name = str(event.payload["session_name"])

    def status_bar_text(self) -> str:
        records = self.list()
        if not records:
            return "No agents running"
        return " | ".join(record.bar_token() for record in records)

    def controller_event(self, message: str) -> AgentEvent:
        return AgentEvent(
            type=EventType.CONTROLLER,
            agent_id=None,
            message=message,
            created_at=utc_now(),
        )

    def get_by_index(self, index: int) -> AgentRecord | None:
        records = self.list()
        if index < 0 or index >= len(records):
            return None
        return records[index]

    def _transcript_line_for_event(self, event: AgentEvent) -> ConsoleLine | None:
        if event.type == EventType.MESSAGE_SENT:
            return ConsoleLine(text=f"> {event.message}", style="bold cyan")
        if event.type == EventType.OUTPUT:
            stream = event.payload.get("stream")
            if stream == "stderr":
                return ConsoleLine(text=event.message, style="yellow")
            return ConsoleLine(text=event.message, style="white")
        if event.type == EventType.ERROR:
            return ConsoleLine(text=event.message, style="bold red")
        if event.type == EventType.COMPLETED:
            return ConsoleLine(text=event.message, style="bold green")
        if event.type == EventType.STARTED:
            return ConsoleLine(text=event.message, style="dim")
        return None
