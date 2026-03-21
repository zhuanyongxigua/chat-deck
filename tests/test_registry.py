from pathlib import Path
import unittest

from relay_deck.models import AgentEvent, AgentState, EventType, ToolType
from relay_deck.registry import AgentRegistry


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = AgentRegistry()
        self.record = self.registry.register(
            agent_id="abc123",
            name="api-agent",
            tool_type=ToolType.CODEX,
            cwd=Path("/tmp/api-agent"),
            branch="main",
        )

    def test_apply_summary_event_updates_unread_and_summary(self) -> None:
        self.registry.apply_event(
            AgentEvent(
                type=EventType.SUMMARY_UPDATED,
                agent_id="abc123",
                message="Completed API scaffold",
            )
        )
        record = self.registry.get("abc123")
        assert record is not None
        self.assertEqual(record.last_summary, "Completed API scaffold")
        self.assertEqual(record.unread_count, 1)

    def test_output_event_appends_transcript(self) -> None:
        self.registry.apply_event(
            AgentEvent(
                type=EventType.OUTPUT,
                agent_id="abc123",
                message="streaming output",
                state=AgentState.WORKING,
                payload={"stream": "stdout"},
            )
        )
        record = self.registry.get("abc123")
        assert record is not None
        self.assertEqual(record.transcript[-1].text, "streaming output")

    def test_apply_state_change_marks_attention(self) -> None:
        self.registry.apply_event(
            AgentEvent(
                type=EventType.STATE_CHANGED,
                agent_id="abc123",
                message="Waiting for review",
                state=AgentState.WAITING,
            )
        )
        record = self.registry.get("abc123")
        assert record is not None
        self.assertEqual(record.state, AgentState.WAITING)
        self.assertTrue(record.needs_attention)

    def test_get_by_index_returns_sorted_agent(self) -> None:
        self.registry.register(
            agent_id="zzz999",
            name="zeta-agent",
            tool_type=ToolType.CLAUDE,
            cwd=Path("/tmp/zeta-agent"),
            branch=None,
        )
        record = self.registry.get_by_index(0)
        assert record is not None
        self.assertEqual(record.name, "api-agent")

    def test_first_message_generates_display_name(self) -> None:
        self.registry.apply_event(
            AgentEvent(
                type=EventType.MESSAGE_SENT,
                agent_id="abc123",
                message="Scan the repository and summarize current structure",
                state=AgentState.WORKING,
            )
        )
        record = self.registry.get("abc123")
        assert record is not None
        self.assertEqual(record.display_name, "Repository Structure")

    def test_new_message_resets_completed_flag(self) -> None:
        self.registry.apply_event(
            AgentEvent(
                type=EventType.STATE_CHANGED,
                agent_id="abc123",
                message="done",
                state=AgentState.COMPLETED,
            )
        )
        self.registry.apply_event(
            AgentEvent(
                type=EventType.MESSAGE_SENT,
                agent_id="abc123",
                message="continue with the remaining test failures",
                state=AgentState.WORKING,
            )
        )
        record = self.registry.get("abc123")
        assert record is not None
        self.assertFalse(record.completed)
        self.assertEqual(record.state, AgentState.WORKING)

    def test_status_bar_text_uses_tokens(self) -> None:
        self.registry.apply_event(
            AgentEvent(
                type=EventType.STATE_CHANGED,
                agent_id="abc123",
                message="done",
                state=AgentState.COMPLETED,
            )
        )
        bar_text = self.registry.status_bar_text()
        self.assertIn("api-agent:C", bar_text)


if __name__ == "__main__":
    unittest.main()
