from __future__ import annotations

import unittest
from argparse import Namespace

from relay_deck.__main__ import _build_codex_notify_report, _ensure_tmux_available, _tmux_install_hint


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


if __name__ == "__main__":
    unittest.main()
