from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from relay_deck.models import AgentSpec, ToolType
from relay_deck.orchestrator import Orchestrator
from relay_deck.runtime_events import RuntimeEventInbox, TurnResult, WorkerReport
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

    def test_write_turn_result_and_drain_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            inbox = RuntimeEventInbox(Path(temp_dir))
            inbox.write_turn_result(
                TurnResult(
                    agent_id="abc123",
                    turn_id="turn-1",
                    status="completed",
                    summary="Fixed the billing reconciliation path.",
                    next_step="Run the billing integration tests.",
                    risks=["Needs a production backfill."],
                )
            )
            results = inbox.drain_turn_results()
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].agent_id, "abc123")
            self.assertEqual(results[0].turn_id, "turn-1")
            self.assertEqual(results[0].summary, "Fixed the billing reconciliation path.")


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
            stop_command = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
            self.assertIn("publish-done", stop_command)
            await orchestrator.shutdown()

    async def test_codex_agent_writes_notify_command_and_uses_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator = Orchestrator(tmux=FakeTmuxManager(), runtime_dir=Path(temp_dir))
            await orchestrator.create_agent(
                spec=AgentSpec(
                    name="codex-agent",
                    tool_type=ToolType.CODEX,
                    cwd=Path(".").resolve(),
                    agent_id="xyz789",
                )
            )
            command = orchestrator.tmux.created[0]["command"]
            self.assertEqual(command[0], "codex")
            self.assertEqual(command[1], "-c")
            self.assertTrue(str(command[2]).startswith("notify="))
            notify_command = json.loads(str(command[2])[len("notify=") :])
            self.assertEqual(notify_command[0], sys.executable)
            self.assertEqual(
                notify_command[1:6],
                ["-m", "relay_deck", "publish-done", "--tool", "codex"],
            )
            self.assertIn("--runtime-dir", notify_command)
            self.assertIn(temp_dir, notify_command)
            self.assertIn("--agent-id", notify_command)
            self.assertIn("xyz789", notify_command)
            self.assertIn("agent-turn-complete", notify_command)
            await orchestrator.shutdown()

    async def test_codex_custom_launch_command_keeps_args_and_injects_notify(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator = Orchestrator(tmux=FakeTmuxManager(), runtime_dir=Path(temp_dir))
            await orchestrator.create_agent(
                spec=AgentSpec(
                    name="codex-agent",
                    tool_type=ToolType.CODEX,
                    cwd=Path(".").resolve(),
                    launch_command=["codex", "--model", "gpt-5", "--profile", "fast"],
                    agent_id="xyz789",
                )
            )
            command = orchestrator.tmux.created[0]["command"]
            self.assertEqual(command[:5], ["codex", "--model", "gpt-5", "--profile", "fast"])
            self.assertEqual(command[5], "-c")
            self.assertTrue(str(command[6]).startswith("notify="))
            await orchestrator.shutdown()

    async def test_claude_custom_launch_command_keeps_args_and_injects_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator = Orchestrator(tmux=FakeTmuxManager(), runtime_dir=Path(temp_dir))
            await orchestrator.create_agent(
                spec=AgentSpec(
                    name="claude-agent",
                    tool_type=ToolType.CLAUDE,
                    cwd=Path(".").resolve(),
                    launch_command=["claude", "--dangerously-skip-permissions"],
                    agent_id="abc123",
                )
            )
            command = orchestrator.tmux.created[0]["command"]
            self.assertEqual(command[:2], ["claude", "--dangerously-skip-permissions"])
            self.assertEqual(command[2], "--settings")
            self.assertTrue(str(command[3]).endswith("claude-settings.json"))
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

    async def test_runtime_report_keeps_codex_summary_on_completion(self) -> None:
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
                    event_name="agent-turn-complete",
                    message="Codex completed its current turn",
                    summary="Updated billing tests and fixed flaky snapshot assertions.",
                    state="completed",
                    payload={"summary": "Updated billing tests and fixed flaky snapshot assertions."},
                )
            )
            await orchestrator.poll_runtime_reports_once()
            record = orchestrator.registry.get("xyz789")
            assert record is not None
            self.assertEqual(record.state.value, "completed")
            self.assertEqual(record.last_summary, "Updated billing tests and fixed flaky snapshot assertions.")

    async def test_turn_result_updates_summary_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator = Orchestrator(tmux=FakeTmuxManager(), runtime_dir=Path(temp_dir))
            orchestrator.registry.register(
                agent_id="abc123",
                name="claude-agent",
                tool_type=ToolType.CLAUDE,
                cwd=Path(temp_dir),
                branch=None,
            )
            orchestrator.runtime.write_turn_result(
                TurnResult(
                    agent_id="abc123",
                    turn_id="turn-1",
                    status="completed",
                    summary="Implemented the new retry guard.",
                    next_step="Run the flaky integration suite.",
                    risks=["May still retry too aggressively under load."],
                )
            )
            await orchestrator.poll_runtime_reports_once()
            record = orchestrator.registry.get("abc123")
            assert record is not None
            self.assertEqual(record.state.value, "completed")
            self.assertIn("Implemented the new retry guard.", record.last_summary)
            self.assertIn("Run the flaky integration suite.", record.last_summary)
            self.assertNotIn("Next:", record.last_summary)


if __name__ == "__main__":
    unittest.main()
