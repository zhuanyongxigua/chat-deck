# Chat Deck

> Chat-first multi-agent console for Claude Code and Codex, built with Bun, OpenTUI, and tmux.

Chat Deck lets you manage multiple Claude Code and Codex agents from one terminal UI. Each agent runs in its own isolated tmux session and can work in a completely different directory. Instead of staring at raw terminal logs, you talk to the selected agent in a chat-style pane and receive structured task summaries back when work is done.

![Chat Deck screenshot](./assets/chat-deck-screenshot.png)

> Status: alpha / experimental
>
> Package and CLI name: `chat-deck`

[简体中文 README](./README.zh-CN.md)

---

## Why Chat Deck?

Running several Claude Code or Codex sessions across projects is easy. Keeping them visible, switchable, and conversation-first is not.

tmux and terminal tabs are great at managing terminals. Chat Deck sits one layer above that: it gives you a chat-first controller, per-agent status, direct agent addressing, and structured completion summaries.

---

## Tech Stack

- Bun
- TypeScript
- OpenTUI
- tmux

---

## Current OpenTUI Rewrite

The project has been rewritten around OpenTUI instead of Python/Textual.

The current TypeScript rewrite keeps the core Chat Deck workflow:

- Persistent sidebar with session status
- Chat-style main pane for the selected agent
- tmux-backed Claude Code and Codex workers
- `/new`, `/agents`, `/close`, `/attach`, and `@agent-name ...`
- `Ctrl+1..9`, `Ctrl+T`, `Ctrl+X`, `Ctrl+B`, `Esc`
- Natural-language create requests such as `create a codex session in /path/to/project`
- Structured completion parsing via `<TASK_DONE>...</TASK_DONE>`

Some richer Python-era behaviors are intentionally not carried over yet and will need to be rebuilt natively in TypeScript.

---

## Prerequisites

You need these tools on your machine:

```bash
which bun
which zig
which tmux
which claude
which codex
```

If you only want to inspect the code, `bun` and `zig` are the main requirements for the TUI itself. If you want real workers, `tmux` plus `claude` and/or `codex` must also be installed.

---

## Install

Clone the repository and install dependencies:

```bash
git clone git@github.com:zhuanyongxigua/chat-deck.git
cd chat-deck
bun install
```

If you want the `chat-deck` command available globally from this checkout:

```bash
bun link
```

---

## Run

Run directly from the repo:

```bash
bun run dev
```

`bun run dev` now watches `src/` and automatically restarts Chat Deck when files change.

Or, after linking:

```bash
chat-deck
```

For a single non-watch launch:

```bash
bun run start
```

---

## Validate

Run the minimal test suite:

```bash
bun test
```

Run a type check:

```bash
bun run check
```

---

## Commands

### Create agents

```bash
/new codex <name> <cwd>
/new claude <name> <cwd>
```

You can also pass client-specific startup arguments directly after the working directory:

```bash
/new codex worker /path/to/project --model gpt-5 --profile fast
/new claude reviewer /path/to/project --dangerously-skip-permissions
```

### Session management

- `/agents` lists current agents
- `/attach [agent-name]` opens the selected or named agent in native tmux
- `/close` closes the current active agent
- `/close <agent-name>` closes a specific agent and kills its tmux session

### Message routing

- `@agent-name ...` sends a message directly to a specific agent

---

## Shortcuts

- `Ctrl+1..9` selects an agent
- `Ctrl+T` attaches to the current agent's native tmux session
- `Ctrl+X` closes the current active agent and kills its tmux session
- `Ctrl+B` hides or shows the sidebar
- `Esc` returns to the controller

---

## Current Limitations

- The richer Claude hook and Codex notify/app-server pipeline has not yet been reimplemented in the OpenTUI version
- The current completion flow still depends on workers emitting the `TASK_DONE` protocol correctly
- The OpenTUI rewrite has not been validated in this repository yet because Bun/Zig are not installed in the current environment

---

## License

MIT
