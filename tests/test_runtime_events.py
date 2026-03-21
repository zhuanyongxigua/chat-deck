from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from relay_deck.models import AgentSpec, ToolType
from relay_deck.orchestrator import Orchestrator
from relay_deck.runtime_events import RuntimeEventInbox, WorkerReport
from relay_deck.tmux_manager import TmuxPaneState


class FakeTmuxManager:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.created: list[dict[str, object]] = []
        self.attached: list[str] = []

    async def is_available(self) -> bool:
        return self.available

    async def create_session(self, *, session_name: str, cwd: Path, command: list[str]) -> None:
        self.created.append({"session_name": session_name, "cwd": cwd, "command": command})

    async def destroy_session(self, session_name: str) -> None:
        return None

    async def has_session(self, session_name: str) -> bool:
        return True

    async def send_text(self, session_name: str, text: str) -> None:
        return None

    async def send_interrupt(self, session_name: str) -> None:
        return None

    async def attach_session(self, session_name: str) -> None:
        self.attached.append(session_name)

    async def capture_snapshot(self, session_name: str, *, lines: int = 120) -> list[str]:
        return []

    async def pane_state(self, session_name: str) -> TmuxPaneState:
        return TmuxPaneState(session_exists=True)


class RuntimeEventInboxTests(unittest.TestCase):
    def test_write_report_and_drain_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            inbox = RuntimeEventInbox(Path(temp_dir))
            inbox.write_report(
                WorkerReport(
                    agent_id="abc123",
                    source="claude",
                    event_name="Stop",
                    message="done",
                )
            )
            reports = inbox.drain()
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0].agent_id, "abc123")
            self.assertEqual(reports[0].event_name, "Stop")


class OrchestratorSemanticStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_claude_agent_writes_hook_settings_and_uses_them(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator = Orchestrator(tmux=FakeTmuxManager(), runtime_dir=Path(temp_dir))
            await orchestrator.create_agent(
                spec=AgentSpec(
                    name="claude-agent",
                    tool_type=ToolType.CLAUDE,
                    cwd=Path(".").resolve(),
                    agent_id="abc123",
                )
            )
            command = orchestrator.tmux.created[0]["command"]
            self.assertEqual(command[0], "claude")
            self.assertEqual(command[1], "--settings")
            settings_path = Path(command[2])
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            self.assertEqual(
                sorted(settings["hooks"].keys()),
                ["Notification", "PermissionRequest", "SessionEnd", "Stop"],
            )
            await orchestrator.shutdown()

    async def test_runtime_report_maps_claude_waiting_and_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator = Orchestrator(tmux=FakeTmuxManager(), runtime_dir=Path(temp_dir))
            orchestrator.registry.register(
                agent_id="abc123",
                name="claude-agent",
                tool_type=ToolType.CLAUDE,
                cwd=Path(temp_dir),
                branch=None,
            )
            orchestrator.runtime.write_report(
                WorkerReport(
                    agent_id="abc123",
                    source="claude",
                    event_name="Notification",
                    payload={
                        "title": "Action Required",
                        "message": "Approve command execution",
                    },
                )
            )
            await orchestrator.poll_runtime_reports_once()
            record = orchestrator.registry.get("abc123")
            assert record is not None
            self.assertEqual(record.state.value, "waiting")
            self.assertIn("Approve command execution", record.recent_events[-1].message)

            orchestrator.runtime.write_report(
                WorkerReport(
                    agent_id="abc123",
                    source="claude",
                    event_name="Stop",
                    message="Claude completed its current turn",
                )
            )
            await orchestrator.poll_runtime_reports_once()
            record = orchestrator.registry.get("abc123")
            assert record is not None
            self.assertEqual(record.state.value, "completed")

    async def test_runtime_report_maps_codex_thread_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator = Orchestrator(tmux=FakeTmuxManager(), runtime_dir=Path(temp_dir))
            orchestrator.registry.register(
                agent_id="xyz789",
                name="codex-agent",
                tool_type=ToolType.CODEX,
                cwd=Path(temp_dir),
                branch=None,
            )
            orchestrator.runtime.write_report(
                WorkerReport(
                    agent_id="xyz789",
                    source="codex",
                    event_name="thread/status/changed",
                    payload={
                        "status": {
                            "type": "active",
                            "activeFlags": ["waitingOnApproval"],
                        }
                    },
                )
            )
            await orchestrator.poll_runtime_reports_once()
            record = orchestrator.registry.get("xyz789")
            assert record is not None
            self.assertEqual(record.state.value, "waiting")
            self.assertTrue(record.needs_attention)


if __name__ == "__main__":
    unittest.main()
