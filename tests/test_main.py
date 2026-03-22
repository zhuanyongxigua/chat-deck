from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from relay_deck.__main__ import _build_codex_notify_report, _ensure_tmux_available, _handle_publish_done, _tmux_install_hint
from relay_deck.runtime_events import RuntimeEventInbox, TaskDoneInbox


class MainModuleTests(unittest.TestCase):
    def test_tmux_install_hint_for_macos(self) -> None:
        self.assertEqual(
            _tmux_install_hint(system_name="Darwin"),
            "Install tmux first: brew install tmux",
        )

    def test_tmux_install_hint_for_debian_family(self) -> None:
        hint = _tmux_install_hint(system_name="Linux", os_release_text="ID=ubuntu")
        self.assertEqual(hint, "Install tmux first: sudo apt install tmux")

    def test_ensure_tmux_available_skips_demo(self) -> None:
        _ensure_tmux_available(demo=True, which=lambda _: None)

    def test_ensure_tmux_available_raises_when_missing(self) -> None:
        with self.assertRaises(SystemExit) as context:
            _ensure_tmux_available(demo=False, which=lambda _: None)
        self.assertIn("tmux is required", str(context.exception))

    def test_build_codex_notify_report_extracts_summary_from_payload(self) -> None:
        report = _build_codex_notify_report(
            Namespace(
                runtime_dir="/tmp/runtime",
                agent_id="xyz789",
                event_name="agent-turn-complete",
                payload_json=(
                    '{"message":"Turn finished","turn":{"last_assistant_message":"Refactored auth flow and '
                    'added regression tests."}}'
                ),
            )
        )
        self.assertEqual(report.source, "codex")
        self.assertEqual(report.event_name, "agent-turn-complete")
        self.assertEqual(report.state, "completed")
        self.assertEqual(report.message, "Turn finished")
        self.assertEqual(report.summary, "Refactored auth flow and added regression tests.")

    def test_build_codex_notify_report_extracts_assistant_content_blocks(self) -> None:
        report = _build_codex_notify_report(
            Namespace(
                runtime_dir="/tmp/runtime",
                agent_id="xyz789",
                event_name="agent-turn-complete",
                payload_json=(
                    '{"turn":{"messages":[{"role":"assistant","content":['
                    '{"type":"output_text","text":"Refactored billing service."},'
                    '{"type":"output_text","text":"Added regression coverage for invoice retries."}'
                    ']}]}}'
                ),
            )
        )
        self.assertEqual(
            report.summary,
            "Refactored billing service.\nAdded regression coverage for invoice retries.",
        )

    def test_publish_done_writes_task_done_event_into_inbox(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_dir = Path(temp_dir) / "runtime"
            inbox_path = Path(temp_dir) / "inbox.jsonl"
            _handle_publish_done(
                Namespace(
                    tool="codex",
                    runtime_dir=str(runtime_dir),
                    agent_id="xyz789",
                    event_name="agent-turn-complete",
                    inbox=str(inbox_path),
                    payload_json=None,
                    payload_json_positional=(
                        '{"last-assistant-message":"All done.\\n<TASK_DONE>{\\"summary\\":\\"Finished auth refactor\\",'
                        '\\"result\\":\\"Tests now pass\\",\\"next\\":\\"Merge the branch\\"}</TASK_DONE>"}'
                    ),
                )
            )
            task_done_events = TaskDoneInbox(inbox_path).drain()
            self.assertEqual(len(task_done_events), 1)
            self.assertEqual(task_done_events[0].summary, "Finished auth refactor")
            reports = RuntimeEventInbox(runtime_dir).drain()
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0].event_name, "agent-turn-complete")


if __name__ == "__main__":
    unittest.main()
