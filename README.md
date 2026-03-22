# Chat Deck

> Chat-first multi-agent console for Claude Code and Codex, built with Python, Textual, and tmux.

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

## What Chat Deck Does

- Manage multiple agents from one controller UI
- Support real workers from:
  - Claude Code
  - Codex
- Run each agent in its own tmux session
- Keep session state visible in a persistent sidebar
- Talk to the currently selected agent in a chat-style main pane
- Receive task summaries back in the panel instead of attaching to tmux for every result
- Support structured completion messages via:

```xml
<TASK_DONE>{"summary":"...","result":"...","next":"..."}</TASK_DONE>
```

- Inject Claude hooks and Codex notify handlers temporarily, without modifying global `~/.claude` or `~/.codex`
- Fold large pasted content in the UI and restore it on send
- Show loading state in both the sidebar and the active chat view
- Resize the sidebar with the mouse

---

## Current Features

### Multi-agent chat controller

- Single main UI for managing multiple agent sessions
- Always-visible session cards in the sidebar
- Session cards include:
  - name
  - client
  - working directory
  - status

### Chat-first interaction

- Main content area is a chat with the selected agent
- Raw execution logs are not the primary view
- Agents return summaries to the chat when they finish work

### tmux-backed workers

- Each agent runs in an independent tmux session
- Workers can run in completely different directories
- You can still jump into the native CLI when needed

### Structured completion flow

- Claude and Codex can send task-complete summaries back to the panel
- Completion is currently driven by the `<TASK_DONE>...</TASK_DONE>` protocol

### Input and usability

- Mouse selection works in the content area
- `Ctrl+C` copies
- `Ctrl+V` pastes
- Large pasted content is collapsed visually and restored when sent
- Typing `/` shows command suggestions
- `Tab` autocompletes the current command suggestion

---

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Chat Deck depends on `tmux` for real Claude Code and Codex worker sessions. Install it separately before launching the app normally:

```bash
brew install tmux
```

If you plan to use real workers, make sure these are on `PATH` as well:

```bash
which tmux
which claude
which codex
```

---

## Run

```bash
chat-deck
```

Demo mode still works without `tmux`:

```bash
chat-deck --demo
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

Chat Deck will still inject its own runtime notify / settings hooks after your custom arguments.

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

## How It Works

Chat Deck has two layers.

### 1. Controller UI

The controller is built with Python + Textual.

It is responsible for:

- showing agent status
- routing messages
- displaying summaries
- managing the active chat view

### 2. Real worker sessions

Claude Code and Codex run as real CLI workers inside tmux.

Chat Deck does not replace those CLIs. It manages them, talks to them, and summarizes them.

When you need the native interface, you can attach to the worker's tmux session with `Ctrl+T`.

---

## Why Not Just tmux or Terminal Tabs?

tmux manages terminals.

Chat Deck manages agent conversations.

That means:

- status is visible without hunting for the right pane
- you can talk to an agent directly from the controller
- you get task summaries back in chat
- you only attach to the native CLI when you actually need it

---

## Current Limitations

- The controller does not yet use a full LLM-powered orchestration layer
- Codex fine-grained semantic state is not yet connected through the full app-server path
- Completion summaries currently depend on the worker emitting the `TASK_DONE` protocol correctly
- The main UI is chat-first, not an embedded native Claude / Codex terminal

---

## Roadmap

- Add a smarter controller agent
- Improve Codex semantic status integration
- Make completion summaries more robust than protocol-only detection
- Add richer session history and summary browsing
- Explore embedded terminal support later, without making it the core UX

---

## Design Principles

- Chat first, terminal second
- Summaries over raw logs
- Native CLI only when needed
- No global config pollution
- One controller, many long-running workers

---

## Who Is This For?

Chat Deck is for developers who:

- run multiple Claude Code or Codex sessions at once
- want one place to see session state
- prefer conversation and summaries over watching terminal output
- still want native tmux-backed CLI sessions available on demand

---

## Project Status

Chat Deck is currently focused on a local-first workflow:

- Python + Textual for the controller
- tmux for long-running worker sessions
- Claude Code and Codex as the first supported workers

Packaging, installation, and broader distribution are still evolving.

---

## License

[MIT](./LICENSE)
