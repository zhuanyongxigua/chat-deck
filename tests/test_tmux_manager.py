from __future__ import annotations

import unittest

from relay_deck.tmux_manager import TmuxCommandResult, TmuxManager


class RecordingTmuxManager(TmuxManager):
    def __init__(self) -> None:
        super().__init__(submit_delay=0)
        self.calls: list[tuple[str, ...]] = []

    async def _run(self, *args: str, check: bool = True) -> TmuxCommandResult:
        self.calls.append(args)
        return TmuxCommandResult(returncode=0, stdout="", stderr="")


class TmuxManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_text_uses_literal_input_then_carriage_return(self) -> None:
        tmux = RecordingTmuxManager()
        await tmux.send_text("session-1", "hello world")
        self.assertEqual(
            tmux.calls,
            [
                ("send-keys", "-t", "session-1", "-l", "hello world"),
                ("send-keys", "-t", "session-1", "C-m"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
