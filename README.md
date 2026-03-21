# Relay Deck

Relay Deck is a Python TUI for supervising multiple independent coding-agent sessions from a single terminal interface.

## Current MVP

- Textual-based main console
- Agent registry with status, summary, unread counters, and recent output
- Async orchestrator with event bus
- `@agent-name` routing from the main input box
- tmux-backed worker sessions for Codex and Claude Code
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

Real Claude Code and Codex workers require `tmux` to be installed and available on `PATH`. The `--demo` mode still works without `tmux`.

## Main Commands

- `/help`
- `/new codex api-agent /path/to/project`
- `/new claude review-agent /path/to/project`
- `/attach api-agent`
- `/agents`
- `@api-agent summarize the current progress`
- `@review-agent continue with the remaining test failures`

## Notes

- The current MVP uses tmux as the worker-session substrate rather than trying to embed full CLI TUIs inside Textual.
- The UI focuses on status visibility, routing, and pane snapshots rather than full terminal emulation.
- Clicking a sidebar card or using `Ctrl/Cmd+1..9` selects an agent. `Ctrl+T` or `/attach <agent-name>` opens the real tmux session.
- Agent cards show the client type explicitly. The current user-facing clients are `Codex` and `Claude Code`.
- If `tmux`, `codex`, or `claude` is missing, the agent will surface an error state in the UI.
