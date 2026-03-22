import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from textual.geometry import Offset
from textual.selection import Selection
from textual.widgets import Input, Static

from relay_deck.app import RelayDeckApp
from relay_deck.models import AgentEvent, AgentSpec, AgentState, EventType, ToolType
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

    async def test_controller_command_from_agent_view_keeps_selected_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = RelayDeckApp(
                demo=True,
                history_path=Path(temp_dir) / ".chat-deck" / "command-history.txt",
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("ctrl+1")
                await pilot.pause()
                selected_agent_id = app._selected_agent_id
                self.assertIsNotNone(selected_agent_id)

                input_widget = app.query_one(Input)
                input_widget.value = "/new codex demo-codex /tmp"
                await input_widget.action_submit()
                await pilot.pause()

                self.assertEqual(app._selected_agent_id, selected_agent_id)
                header = app.query_one("#workspace-header", Static)
                self.assertIn("@demo-codex", str(header.render()))
                footer = app.query_one("#footer-message", Static)
                self.assertIn("Agent name already exists: demo-codex", str(footer.render()))

    async def test_close_without_target_closes_selected_agent(self) -> None:
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
                input_widget.value = "/close"
                await input_widget.action_submit()
                await pilot.pause()

                self.assertIsNone(app._selected_agent_id)
                sidebar = app.query_one(AgentSidebar)
                cards = list(sidebar.query(AgentCard))
                self.assertEqual(len(cards), 1)
                self.assertEqual(cards[0].record.name, "demo-review")
                footer = app.query_one("#footer-message", Static)
                self.assertIn("Closed @demo-codex", str(footer.render()))

    async def test_ctrl_x_closes_selected_agent(self) -> None:
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

                await pilot.press("ctrl+x")
                await pilot.pause()

                self.assertIsNone(app._selected_agent_id)
                sidebar = app.query_one(AgentSidebar)
                cards = list(sidebar.query(AgentCard))
                self.assertEqual(len(cards), 1)
                self.assertEqual(cards[0].record.name, "demo-review")

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

    async def test_slash_input_shows_command_suggestions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = RelayDeckApp(
                demo=True,
                history_path=Path(temp_dir) / ".chat-deck" / "command-history.txt",
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                input_widget = app.query_one(HistoryInput)
                input_widget.value = "/"
                await pilot.pause()

                footer = app.query_one("#footer-message", Static)
                rendered = str(footer.render())
                self.assertIn("/help", rendered)
                self.assertIn("/agents", rendered)
                self.assertIn("/new", rendered)

    async def test_tab_autocompletes_current_command_suggestion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = RelayDeckApp(
                demo=True,
                history_path=Path(temp_dir) / ".chat-deck" / "command-history.txt",
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                input_widget = app.query_one(HistoryInput)
                input_widget.value = "/a"
                await pilot.pause()

                await pilot.press("tab")
                await pilot.pause()

                self.assertEqual(input_widget.value, "/agents")

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

    async def test_sidebar_background_click_keeps_selected_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = RelayDeckApp(
                demo=True,
                history_path=Path(temp_dir) / ".chat-deck" / "command-history.txt",
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("ctrl+1")
                await pilot.pause()
                selected_agent_id = app._selected_agent_id
                self.assertIsNotNone(selected_agent_id)

                await app.on_agent_sidebar_background_selected(AgentSidebar.BackgroundSelected())
                await pilot.pause()

                self.assertEqual(app._selected_agent_id, selected_agent_id)

    async def test_sidebar_width_can_be_updated_from_drag_position(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = RelayDeckApp(
                demo=True,
                history_path=Path(temp_dir) / ".chat-deck" / "command-history.txt",
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                body = app.query_one("#body")
                target_x = body.region.x + body.region.width * 0.45
                app._set_sidebar_width_from_screen_x(target_x)
                await pilot.pause()

                self.assertGreater(app._sidebar_width_percent, 40.0)
                sidebar = app.query_one(AgentSidebar)
                self.assertTrue(str(sidebar.styles.width))

    async def test_ctrl_c_copies_selected_input_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = RelayDeckApp(
                demo=True,
                history_path=Path(temp_dir) / ".chat-deck" / "command-history.txt",
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                input_widget = app.query_one(HistoryInput)
                input_widget.value = "copy this line"
                input_widget.select_all()
                with patch.object(app, "_write_system_clipboard", return_value=True):
                    app.action_copy_selection()
                self.assertEqual(app.clipboard, "copy this line")

    async def test_ctrl_c_copies_selected_chat_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = RelayDeckApp(
                demo=False,
                history_path=Path(temp_dir) / ".chat-deck" / "command-history.txt",
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                app._controller_history = [("copy me", "white")]
                app._render_main_log()
                log = app.query_one("#controller-log")
                app.screen.selections[log] = Selection.from_offsets(Offset(0, 0), Offset(7, 0))
                with patch.object(log, "get_selection", return_value=("copy me", "\n")):
                    with patch.object(app, "_write_system_clipboard", return_value=True):
                        app.action_copy_selection()
                self.assertEqual(app.clipboard, "copy me")

    async def test_ctrl_v_pastes_clipboard_into_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = RelayDeckApp(
                demo=True,
                history_path=Path(temp_dir) / ".chat-deck" / "command-history.txt",
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                input_widget = app.query_one(HistoryInput)
                input_widget.value = ""
                with patch.object(app, "_read_clipboard_text", return_value="pasted from clipboard"):
                    app.action_paste_clipboard()
                self.assertEqual(input_widget.value, "pasted from clipboard")

    async def test_large_paste_collapses_into_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = RelayDeckApp(
                demo=True,
                history_path=Path(temp_dir) / ".chat-deck" / "command-history.txt",
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                input_widget = app.query_one(HistoryInput)
                large_text = "x" * 1225
                with patch.object(app, "_read_clipboard_text", return_value=large_text):
                    app.action_paste_clipboard()
                self.assertEqual(input_widget.value, "[Pasted Content 1225 chars]")
                self.assertEqual(input_widget.expand_value(), large_text)

    async def test_collapsed_paste_expands_before_agent_send(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = RelayDeckApp(
                demo=True,
                history_path=Path(temp_dir) / ".chat-deck" / "command-history.txt",
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("ctrl+1")
                await pilot.pause()
                input_widget = app.query_one(HistoryInput)
                large_text = "x" * 1225
                input_widget.insert_pasted_text(large_text)
                send_mock = AsyncMock(return_value="Sent to @demo-codex: [Pasted Content 1225 chars]")
                app.orchestrator.send_to_agent = send_mock

                await input_widget.action_submit()
                await pilot.pause()

                send_mock.assert_awaited_once_with(
                    "demo-codex",
                    large_text,
                    display_message="[Pasted Content 1225 chars]",
                )
                self.assertEqual(input_widget.value, "")

    async def test_selected_agent_shows_spinner_on_pending_user_message(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = RelayDeckApp(
                demo=False,
                history_path=Path(temp_dir) / ".chat-deck" / "command-history.txt",
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                agent_id = await app.orchestrator.create_agent(
                    AgentSpec(name="worker", tool_type=ToolType.MOCK, cwd=Path(".").resolve())
                )
                app.orchestrator.registry.apply_event(
                    AgentEvent(
                        type=EventType.MESSAGE_SENT,
                        agent_id=agent_id,
                        message="finish the task",
                        state=AgentState.WORKING,
                    )
                )
                app._select_agent(agent_id)
                await pilot.pause()

                log = app.query_one("#controller-log", Static)
                self.assertIn("> ◐ finish the task", str(log.render()))

    async def test_spinner_disappears_after_summary_arrives(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = RelayDeckApp(
                demo=False,
                history_path=Path(temp_dir) / ".chat-deck" / "command-history.txt",
            )
            async with app.run_test() as pilot:
                await pilot.pause()
                agent_id = await app.orchestrator.create_agent(
                    AgentSpec(name="worker", tool_type=ToolType.MOCK, cwd=Path(".").resolve())
                )
                app.orchestrator.registry.apply_event(
                    AgentEvent(
                        type=EventType.MESSAGE_SENT,
                        agent_id=agent_id,
                        message="finish the task",
                        state=AgentState.WORKING,
                    )
                )
                app.orchestrator.registry.apply_event(
                    AgentEvent(
                        type=EventType.SUMMARY_UPDATED,
                        agent_id=agent_id,
                        message="Task completed successfully.",
                    )
                )
                app.orchestrator.registry.apply_event(
                    AgentEvent(
                        type=EventType.STATE_CHANGED,
                        agent_id=agent_id,
                        message="done",
                        state=AgentState.COMPLETED,
                    )
                )
                app._select_agent(agent_id)
                await pilot.pause()

                log = app.query_one("#controller-log", Static)
                rendered = str(log.render())
                self.assertIn("> finish the task", rendered)
                self.assertNotIn("> ◐ finish the task", rendered)

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
