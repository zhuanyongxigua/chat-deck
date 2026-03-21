from pathlib import Path
import tempfile
import unittest

from relay_deck.controller import ControllerInterpreter
from relay_deck.models import ToolType
from relay_deck.orchestrator import Orchestrator


class ControllerInterpreterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.interpreter = ControllerInterpreter()

    def test_interprets_english_create_request(self) -> None:
        result = self.interpreter.interpret("create a codex agent named api-agent for /tmp/project")
        assert result is not None
        self.assertEqual(result.kind, "create_agent")
        self.assertEqual(result.tool_type, ToolType.CODEX)
        self.assertEqual(result.name, "api-agent")
        self.assertEqual(result.cwd, Path("/tmp/project"))

    def test_interprets_chinese_create_request(self) -> None:
        result = self.interpreter.interpret("帮我创建一个 claude 会话 叫review-agent 在 /tmp/review")
        assert result is not None
        self.assertEqual(result.tool_type, ToolType.CLAUDE)
        self.assertEqual(result.name, "review-agent")
        self.assertEqual(result.cwd, Path("/tmp/review"))


class FakeTmuxManager:
    async def is_available(self) -> bool:
        return True

    async def create_session(self, *, session_name: str, cwd: Path, command: list[str]) -> None:
        return None

    async def destroy_session(self, session_name: str) -> None:
        return None

    async def has_session(self, session_name: str) -> bool:
        return True

    async def send_text(self, session_name: str, text: str) -> None:
        return None

    async def send_interrupt(self, session_name: str) -> None:
        return None

    async def attach_session(self, session_name: str) -> None:
        return None

    async def capture_snapshot(self, session_name: str, *, lines: int = 120) -> list[str]:
        return []

    async def pane_state(self, session_name: str):
        from relay_deck.tmux_manager import TmuxPaneState

        return TmuxPaneState(session_exists=True)


class OrchestratorNaturalLanguageTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_input_creates_agent_from_natural_language(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator = Orchestrator(tmux=FakeTmuxManager())
            message = await orchestrator.handle_input(f"创建一个 codex 会话 在 {temp_dir}")
            self.assertIn("Created Codex agent", message)
            created = orchestrator.registry.get_by_name(f"{Path(temp_dir).name}-codex")
            self.assertIsNotNone(created)
            await orchestrator.shutdown()


if __name__ == "__main__":
    unittest.main()
