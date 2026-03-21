from __future__ import annotations

from relay_deck.adapters.tmux import TmuxAgentAdapter


class ClaudeCodeAdapter(TmuxAgentAdapter):
    def _build_command(self) -> list[str]:
        if self.spec.launch_command:
            return self.spec.launch_command
        return ["claude"]
