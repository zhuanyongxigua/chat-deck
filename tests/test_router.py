from pathlib import Path
import unittest

from relay_deck.models import ToolType
from relay_deck.router import InputRouter


class RouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = InputRouter()

    def test_parse_agent_message(self) -> None:
        result = self.router.parse("@api-agent summarize progress")
        self.assertEqual(result.kind, "agent_message")
        self.assertEqual(result.target, "api-agent")
        self.assertEqual(result.message, "summarize progress")

    def test_parse_new_command(self) -> None:
        result = self.router.parse("/new codex api-agent ~/work/api")
        self.assertEqual(result.kind, "create_agent")
        self.assertEqual(result.tool_type, ToolType.CODEX)
        self.assertEqual(result.name, "api-agent")
        self.assertEqual(result.cwd, Path("~/work/api").expanduser())

    def test_invalid_command(self) -> None:
        result = self.router.parse("/unknown")
        self.assertEqual(result.kind, "invalid")

    def test_reject_mock_client_in_user_command(self) -> None:
        result = self.router.parse("/new mock demo-agent /tmp")
        self.assertEqual(result.kind, "invalid")
        self.assertIn("Unsupported client", result.message)


if __name__ == "__main__":
    unittest.main()
