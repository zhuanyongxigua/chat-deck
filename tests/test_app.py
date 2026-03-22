import asyncio
from pathlib import Path
import tempfile
import unittest

from textual.widgets import Input, Static

from relay_deck.app import RelayDeckApp
from relay_deck.models import AgentSpec, ToolType
from relay_deck.widgets.agent_sidebar import AgentCard, AgentSidebar
from relay_deck.widgets.history_input import HistoryInput


class AppSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_selecting_agent_switches_main_view_and_plain_input_targets_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = RelayDeckApp(
                demo=True,
                history_path=Path(temp_dir) / ".chat-deck" / "command-history.txt",
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("ctrl+1")
                await pilot.pause()

                self.assertIsNotNone(app._selected_agent_id)
                header = app.query_one("#workspace-header", Static)
                self.assertIn("@demo-codex", str(header.render()))

                input_widget = app.query_one(Input)
                self.assertIn("Message @demo-codex", input_widget.placeholder)

                await app._send_to_selected_agent("continue with the remaining work")
                await asyncio.sleep(0.1)
                record = app.orchestrator.registry.get(app._selected_agent_id or "")
                assert record is not None
                chat_text = "\n".join(line.text for line in record.chat_transcript)
                self.assertIn("> continue with the remaining work", chat_text)
                self.assertIn("Handled: continue with the remaining work", chat_text)
                self.assertNotIn("Mock agent working", chat_text)

    async def test_controller_command_from_agent_view_returns_to_controller(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = RelayDeckApp(
                demo=True,
                history_path=Path(temp_dir) / ".chat-deck" / "command-history.txt",
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("ctrl+1")
                await pilot.pause()
                self.assertIsNotNone(app._selected_agent_id)

                input_widget = app.query_one(Input)
                input_widget.value = "/new codex demo-codex /tmp"
                await input_widget.action_submit()
                await pilot.pause()

                self.assertIsNone(app._selected_agent_id)
                footer = app.query_one("#footer-message", Static)
                self.assertIn("Agent name already exists: demo-codex", str(footer.render()))

    async def test_input_history_uses_up_and_down(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / ".chat-deck" / "command-history.txt"
            app = RelayDeckApp(demo=True, history_path=history_path)
            async with app.run_test() as pilot:
                await pilot.pause()
                input_widget = app.query_one(HistoryInput)

                input_widget.value = "/agents"
                await input_widget.action_submit()
                await pilot.pause()

                input_widget.value = "/help"
                await input_widget.action_submit()
                await pilot.pause()

                await pilot.press("up")
                await pilot.pause()
                self.assertEqual(input_widget.value, "/help")

                await pilot.press("up")
                await pilot.pause()
                self.assertEqual(input_widget.value, "/agents")

                await pilot.press("down")
                await pilot.pause()
                self.assertEqual(input_widget.value, "/help")

            second_widget = HistoryInput(history_path=history_path)
            self.assertEqual(second_widget._history, ["/agents", "/help"])

    async def test_sidebar_shows_all_agents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = RelayDeckApp(
                demo=False,
                history_path=Path(temp_dir) / ".chat-deck" / "command-history.txt",
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                await app.orchestrator.create_agent(
                    AgentSpec(name="one", tool_type=ToolType.MOCK, cwd=Path(".").resolve())
                )
                await app.orchestrator.create_agent(
                    AgentSpec(name="two", tool_type=ToolType.MOCK, cwd=Path(".").resolve())
                )
                await pilot.pause()

                sidebar = app.query_one(AgentSidebar)
                cards = list(sidebar.query(AgentCard))
                self.assertEqual(len(cards), 2)
                self.assertEqual([card.record.name for card in cards], ["one", "two"])

    async def test_footer_stack_lives_under_workspace_not_sidebar(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = RelayDeckApp(
                demo=True,
                history_path=Path(temp_dir) / ".chat-deck" / "command-history.txt",
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                footer = app.query_one("#footer-stack")
                self.assertIsNotNone(footer.parent)
                self.assertEqual(footer.parent.id, "workspace")

    def test_history_input_persists_only_the_latest_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / ".chat-deck" / "command-history.txt"
            widget = HistoryInput(history_path=history_path, history_limit=3)
            widget.remember("one")
            widget.remember("two")
            widget.remember("three")
            widget.remember("four")

            reloaded = HistoryInput(history_path=history_path, history_limit=3)
            self.assertEqual(reloaded._history, ["two", "three", "four"])


if __name__ == "__main__":
    unittest.main()
