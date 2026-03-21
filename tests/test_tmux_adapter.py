from pathlib import Path
import asyncio
import unittest

from relay_deck.adapters.tmux import TmuxAgentAdapter
from relay_deck.models import AgentSpec, EventType, ToolType
from relay_deck.orchestrator import Orchestrator
from relay_deck.tmux_manager import TmuxPaneState


class FakeTmuxManager:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.created: list[dict[str, object]] = []
        self.sent: list[tuple[str, str]] = []
        self.interrupts: list[str] = []
        self.destroyed: list[str] = []
        self.attached: list[str] = []
        self._snapshots: list[list[str]] = [[]]
        self._last_snapshot: list[str] = []
        self._pane_states: list[TmuxPaneState] = [TmuxPaneState(session_exists=True)]

    async def is_available(self) -> bool:
        return self.available

    async def create_session(self, *, session_name: str, cwd: Path, command: list[str]) -> None:
        self.created.append(
            {
                "session_name": session_name,
                "cwd": cwd,
                "command": command,
            }
        )

    async def destroy_session(self, session_name: str) -> None:
        self.destroyed.append(session_name)

    async def has_session(self, session_name: str) -> bool:
        return True

    async def send_text(self, session_name: str, text: str) -> None:
        self.sent.append((session_name, text))

    async def send_interrupt(self, session_name: str) -> None:
        self.interrupts.append(session_name)

    async def attach_session(self, session_name: str) -> None:
        self.attached.append(session_name)

    async def capture_snapshot(self, session_name: str, *, lines: int = 120) -> list[str]:
        if self._snapshots:
            self._last_snapshot = self._snapshots.pop(0)
        return list(self._last_snapshot)

    async def pane_state(self, session_name: str) -> TmuxPaneState:
        if self._pane_states:
            return self._pane_states.pop(0)
        return TmuxPaneState(session_exists=True)

    def queue_snapshots(self, *snapshots: list[str]) -> None:
        self._snapshots = list(snapshots)
        if snapshots:
            self._last_snapshot = list(snapshots[-1])

    def queue_pane_states(self, *states: TmuxPaneState) -> None:
        self._pane_states = list(states)


class TmuxAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.events = []
        self.tmux = FakeTmuxManager()

    async def _emit(self, event) -> None:
        self.events.append(event)

    def _make_adapter(self, **kwargs) -> TmuxAgentAdapter:
        spec = AgentSpec(
            name="api-agent",
            tool_type=ToolType.CODEX,
            cwd=Path("/tmp"),
            launch_command=["codex", "--help"],
            agent_id="abc123",
        )
        return TmuxAgentAdapter(spec, self._emit, self.tmux, poll_interval=0.01, **kwargs)

    async def test_start_creates_tmux_session_and_emits_started(self) -> None:
        adapter = self._make_adapter()
        await adapter.start()
        await asyncio.sleep(0.02)
        await adapter.stop()

        self.assertEqual(len(self.tmux.created), 1)
        self.assertEqual(self.tmux.created[0]["command"], ["codex", "--help"])
        started = next(event for event in self.events if event.type == EventType.STARTED)
        self.assertEqual(started.payload["session_name"], "relay-codex-api-agent-abc123")

    async def test_snapshot_delta_emits_output_events(self) -> None:
        self.tmux.queue_snapshots(["Booting Codex"], ["Booting Codex", "Planning next step"])
        self.tmux.queue_pane_states(
            TmuxPaneState(session_exists=True),
            TmuxPaneState(session_exists=True),
            TmuxPaneState(session_exists=True),
        )
        adapter = self._make_adapter()
        await adapter.start()
        await asyncio.sleep(0.04)
        await adapter.stop()

        output_messages = [event.message for event in self.events if event.type == EventType.OUTPUT]
        self.assertIn("Booting Codex", output_messages)
        self.assertIn("Planning next step", output_messages)

    async def test_dead_pane_maps_to_completed_event(self) -> None:
        self.tmux.queue_snapshots([])
        self.tmux.queue_pane_states(TmuxPaneState(session_exists=True, pane_dead=True, exit_status=0))
        adapter = self._make_adapter()
        await adapter.start()
        await asyncio.sleep(0.02)

        completed = next(event for event in self.events if event.type == EventType.COMPLETED)
        self.assertEqual(completed.message, "tmux pane exited with code 0")


class OrchestratorTmuxRequirementTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_real_agent_when_tmux_is_missing(self) -> None:
        orchestrator = Orchestrator(tmux=FakeTmuxManager(available=False))
        message = await orchestrator.handle_input("/new codex api-agent .")
        self.assertIn("tmux is required", message)

    async def test_attach_agent_session_uses_session_name_from_registry(self) -> None:
        tmux = FakeTmuxManager()
        orchestrator = Orchestrator(tmux=tmux)
        await orchestrator.create_agent(
            AgentSpec(
                name="api-agent",
                tool_type=ToolType.CODEX,
                cwd=Path(".").resolve(),
                launch_command=["codex", "--help"],
                agent_id="abc123",
            )
        )
        response = await orchestrator.attach_agent_session("api-agent")
        self.assertEqual(response, "")
        self.assertEqual(tmux.attached, ["relay-codex-api-agent-abc123"])
        await orchestrator.shutdown()


if __name__ == "__main__":
    unittest.main()
