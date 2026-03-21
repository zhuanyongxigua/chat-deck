import asyncio
import unittest

from textual.widgets import Input, Static

from relay_deck.app import RelayDeckApp


class AppSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_selecting_agent_switches_main_view_and_plain_input_targets_agent(self) -> None:
        app = RelayDeckApp(demo=True)
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
            transcript_text = "\n".join(line.text for line in record.transcript)
            self.assertIn("Handled: continue with the remaining work", transcript_text)


if __name__ == "__main__":
    unittest.main()
