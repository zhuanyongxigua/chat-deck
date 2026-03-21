from __future__ import annotations

import unittest

from relay_deck.__main__ import _ensure_tmux_available, _tmux_install_hint


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


if __name__ == "__main__":
    unittest.main()
