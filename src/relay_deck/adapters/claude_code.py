from __future__ import annotations

from relay_deck.adapters.cli import CliAgentAdapter


class ClaudeCodeAdapter(CliAgentAdapter):
    def _build_command(self) -> list[str]:
        if self.spec.launch_command:
            return self.spec.launch_command
        return ["claude"]

