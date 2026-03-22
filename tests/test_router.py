import unittest

from relay_deck.router import InputRouter


class RouterTests(unittest.TestCase):
    def test_close_command_parses_agent_name(self) -> None:
        router = InputRouter()
        result = router.parse("/close @api-agent")
        self.assertEqual(result.kind, "close_agent")
        self.assertEqual(result.target, "api-agent")

    def test_new_command_parses_client_args_without_repeating_executable(self) -> None:
        router = InputRouter()
        result = router.parse("/new codex api-agent /tmp/project --model gpt-5 --profile fast")
        self.assertEqual(result.kind, "create_agent")
        self.assertEqual(result.name, "api-agent")
        self.assertEqual(result.launch_command, ["codex", "--model", "gpt-5", "--profile", "fast"])

    def test_new_command_keeps_backward_compatible_double_dash_syntax(self) -> None:
        router = InputRouter()
        result = router.parse("/new codex api-agent /tmp/project -- codex --model gpt-5 --profile fast")
        self.assertEqual(result.kind, "create_agent")
        self.assertEqual(result.launch_command, ["codex", "--model", "gpt-5", "--profile", "fast"])


if __name__ == "__main__":
    unittest.main()
