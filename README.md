# Relay Deck

Relay Deck is a Python TUI for supervising multiple independent coding-agent sessions from a single terminal interface.

## Current MVP

- Textual-based main console
- Agent registry with status, summary, unread counters, and recent output
- Async orchestrator with event bus
- `@agent-name` routing from the main input box
- CLI adapters for Codex and Claude Code
- Expandable adapter architecture for future tools

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run

```bash
relay-deck
```

## Main Commands

- `/help`
- `/new codex api-agent /path/to/project`
- `/new claude review-agent /path/to/project`
- `/agents`
- `@api-agent summarize the current progress`
- `@review-agent continue with the remaining test failures`

## Notes

- The first MVP uses subprocess-backed adapters rather than a terminal emulator.
- The UI focuses on status visibility, routing, and summary flow rather than full transcript embedding.
- Agent cards show the client type explicitly. The current user-facing clients are `Codex` and `Claude Code`.
- If the `codex` or `claude` executable is missing, the agent will surface an error state in the UI.
