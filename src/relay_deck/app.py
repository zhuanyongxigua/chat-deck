from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Input, RichLog, Static

from relay_deck.models import AgentEvent, AgentSpec, AgentState, EventType, ToolType
from relay_deck.orchestrator import Orchestrator
from relay_deck.widgets.agent_sidebar import AgentCard, AgentSidebar
from relay_deck.widgets.status_bar import StatusBar


class RelayDeckApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
        background: rgb(11, 17, 24);
    }

    #status-bar {
        dock: top;
        height: 1;
        background: rgb(19, 28, 38);
        color: rgb(239, 241, 245);
        padding: 0 1;
        text-style: bold;
    }

    #body {
        height: 1fr;
        margin: 0;
        padding: 0;
    }

    #agent-sidebar {
        width: 40;
        height: 1fr;
        min-width: 32;
        max-width: 48;
        padding: 0;
        background: rgb(14, 22, 31);
        border-right: solid rgb(42, 62, 82);
        overflow-y: auto;
    }

    #agent-sidebar-placeholder {
        color: rgb(130, 147, 166);
        padding: 1 1 0 1;
    }

    .agent-card {
        margin: 1 1 0 1;
        height: auto;
    }

    #main-column {
        width: 1fr;
        height: 1fr;
        padding: 1 0 0 1;
        margin: 0;
        background: rgb(15, 24, 34);
    }

    #workspace-header {
        height: 1;
        color: rgb(179, 191, 204);
        background: rgb(15, 24, 34);
        padding: 0 1 0 0;
    }

    #controller-log {
        height: 1fr;
        margin: 0;
        background: rgb(15, 24, 34);
        padding: 0;
        scrollbar-background: rgb(15, 24, 34);
        scrollbar-color: rgb(42, 62, 82);
        scrollbar-color-hover: rgb(62, 82, 102);
    }

    #input-bar {
        dock: bottom;
        height: 3;
        margin: 0;
        border-top: solid rgb(42, 62, 82);
        border-bottom: solid rgb(42, 62, 82);
        background: rgb(11, 17, 24);
        padding: 0;
    }

    #input-row {
        width: 1fr;
        height: 1;
        margin: 0 1;
        background: rgb(11, 17, 24);
    }

    #input-prompt {
        width: 2;
        color: rgb(127, 229, 178);
        text-style: bold;
    }

    #command-input {
        width: 100%;
        height: 1;
        margin: 0;
        border: none;
        background: transparent;
        color: rgb(239, 241, 245);
        padding: 0;
    }

    #command-input:focus {
        border: none;
        background: transparent;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("super+b,ctrl+b,b", "toggle_sidebar", "Toggle Sidebar"),
        ("super+0,ctrl+0,escape", "clear_selection", "Controller"),
        ("super+1,ctrl+1", "select_agent_slot(1)", "Select Agent 1"),
        ("super+2,ctrl+2", "select_agent_slot(2)", "Select Agent 2"),
        ("super+3,ctrl+3", "select_agent_slot(3)", "Select Agent 3"),
        ("super+4,ctrl+4", "select_agent_slot(4)", "Select Agent 4"),
        ("super+5,ctrl+5", "select_agent_slot(5)", "Select Agent 5"),
        ("super+6,ctrl+6", "select_agent_slot(6)", "Select Agent 6"),
        ("super+7,ctrl+7", "select_agent_slot(7)", "Select Agent 7"),
        ("super+8,ctrl+8", "select_agent_slot(8)", "Select Agent 8"),
        ("super+9,ctrl+9", "select_agent_slot(9)", "Select Agent 9"),
        ("ctrl+t", "attach_selected_session", "Attach tmux"),
        ("ctrl+l", "refresh_views", "Refresh"),
    ]

    TITLE = "Relay Deck"
    SUB_TITLE = "Multi-agent control console"

    def __init__(self, *, demo: bool = False) -> None:
        super().__init__()
        self.demo = demo
        self.orchestrator = Orchestrator()
        self._event_queue: asyncio.Queue[AgentEvent] | None = None
        self._event_task: asyncio.Task[None] | None = None
        self._animation_tick = 0
        self._sidebar_visible = True
        self._selected_agent_id: str | None = None
        self._controller_history: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        yield StatusBar()
        with Horizontal(id="body"):
            yield AgentSidebar()
            with Vertical(id="main-column"):
                yield Static(id="workspace-header")
                yield RichLog(id="controller-log", markup=True, wrap=True, auto_scroll=True)
        with Container(id="input-bar"):
            with Horizontal(id="input-row"):
                yield Static(">", id="input-prompt")
                yield Input(
                    placeholder="Type /new, /attach or @agent-name ...",
                    id="command-input",
                    compact=True,
                )

    async def on_mount(self) -> None:
        self._focus_input()
        self._event_queue = await self.orchestrator.bus.subscribe()
        self._event_task = asyncio.create_task(self._consume_events())
        self.set_interval(0.2, self._advance_animation)
        self._write_system(
            "Commands: /help, /agents, /new <codex|claude> <name> <cwd>, /attach [agent-name], @agent-name <message>"
        )
        self._write_system("The sidebar keeps all agent status visible without opening extra panes.")
        self._write_system("Claude Code and Codex workers now run inside tmux sessions.")
        self._write_system("Toggle sidebar with B or Ctrl+B. Cmd+B depends on terminal key forwarding.")
        self._write_system("Click a sidebar card or use Ctrl/Cmd+1..9 to select an agent. Ctrl+T opens its tmux session.")
        if self.demo:
            await self._bootstrap_demo()
        self._refresh_all()

    async def on_unmount(self) -> None:
        if self._event_task is not None:
            self._event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._event_task
        if self._event_queue is not None:
            await self.orchestrator.bus.unsubscribe(self._event_queue)
        await self.orchestrator.shutdown()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value
        self.query_one(Input).value = ""
        if not raw.strip():
            self._focus_input()
            return
        self._write_user(raw)
        result = self.orchestrator.router.parse(raw)
        if result.kind == "attach_agent":
            await self._handle_attach_request(result.target)
        else:
            response = await self.orchestrator.dispatch(result)
            if response:
                self._write_system(response)
        self._refresh_all()
        self._focus_input()

    async def action_refresh_views(self) -> None:
        self._refresh_all()
        self._write_system("Views refreshed")

    async def action_toggle_sidebar(self) -> None:
        self._sidebar_visible = not self._sidebar_visible
        self.query_one(AgentSidebar).display = self._sidebar_visible
        self._write_system("Sidebar shown" if self._sidebar_visible else "Sidebar hidden")
        self._refresh_all()
        self._focus_input()

    async def action_select_agent_slot(self, slot: int) -> None:
        record = self.orchestrator.registry.get_by_index(slot - 1)
        if record is None:
            self._write_system(f"No agent mapped to slot {slot}")
            return
        self._select_agent(record.agent_id)

    async def action_clear_selection(self) -> None:
        if self._selected_agent_id is None:
            return
        self._selected_agent_id = None
        self._refresh_all()
        self._focus_input()

    async def action_attach_selected_session(self) -> None:
        await self._attach_selected_session()

    async def on_agent_card_selected(self, event: AgentCard.Selected) -> None:
        self._select_agent(event.agent_id)

    async def on_agent_sidebar_background_selected(self, event: AgentSidebar.BackgroundSelected) -> None:
        await self.action_clear_selection()

    async def _consume_events(self) -> None:
        assert self._event_queue is not None
        while True:
            event = await self._event_queue.get()
            self._handle_event(event)
            self._refresh_all()

    async def _bootstrap_demo(self) -> None:
        cwd = Path.cwd()
        await self.orchestrator.create_agent(
            AgentSpec(name="demo-codex", tool_type=ToolType.MOCK, cwd=cwd)
        )
        await self.orchestrator.create_agent(
            AgentSpec(name="demo-review", tool_type=ToolType.MOCK, cwd=cwd)
        )
        await self.orchestrator.send_to_agent("demo-codex", "Scan the repository and summarize current structure")
        await self.orchestrator.send_to_agent("demo-review", "Inspect recent changes and highlight open risks")

    def _refresh_all(self) -> None:
        records = self.orchestrator.registry.list()
        if self._selected_agent_id is not None and self.orchestrator.registry.get(self._selected_agent_id) is None:
            self._selected_agent_id = None
        self.query_one(StatusBar).set_records(records, self._animation_tick)
        self.query_one(AgentSidebar).set_records(records, self._animation_tick, self._selected_agent_id)
        self._update_workspace_header()

    def _write_user(self, text: str) -> None:
        self._controller_history.append((f"> {text}", "bold cyan"))
        self.query_one(RichLog).write(Text(f"> {text}", style="bold cyan"))

    def _write_system(self, text: str) -> None:
        self._controller_history.append((text, "white"))
        self.query_one(RichLog).write(Text(text, style="white"))

    def _handle_event(self, event: AgentEvent) -> None:
        if event.type == EventType.CONTROLLER:
            self._write_system(event.message)
            return
        label = event.agent_id or "system"
        style = self._style_for_event(event)
        line = f"[{label}] {event.type.value}: {event.message}"
        self._controller_history.append((line, style))
        self.query_one(RichLog).write(Text(line, style=style))

    def _style_for_event(self, event: AgentEvent) -> str:
        if event.type == EventType.ERROR or event.state == AgentState.ERROR:
            return "bold red"
        if event.type == EventType.COMPLETED or event.state == AgentState.COMPLETED:
            return "bold green"
        if event.state == AgentState.WAITING:
            return "yellow"
        if event.type == EventType.SUMMARY_UPDATED:
            return "magenta"
        return "white"

    def _advance_animation(self) -> None:
        self._animation_tick += 1
        self._refresh_all()

    def _select_agent(self, agent_id: str) -> None:
        record = self.orchestrator.registry.get(agent_id)
        if record is None:
            self._write_system("Selected agent is no longer available")
            return
        self._selected_agent_id = agent_id
        self.orchestrator.registry.mark_read(agent_id)
        self._refresh_all()
        self._focus_input()

    def _update_workspace_header(self) -> None:
        header = self.query_one("#workspace-header", Static)
        if self._selected_agent_id is None:
            header.update("Controller")
            return
        record = self.orchestrator.registry.get(self._selected_agent_id)
        if record is None:
            header.update("Controller")
            return
        header.update(
            f"Controller  Selected @{record.name}  {record.tool_type.client_label}  Ctrl+T or /attach"
        )

    def _focus_input(self) -> None:
        self.query_one(Input).focus()

    async def _handle_attach_request(self, target: str | None) -> None:
        if target:
            with self.suspend():
                response = await self.orchestrator.attach_agent_session(target)
            if response:
                self._write_system(response)
                return
            self._write_system(f"Returned from tmux session @{target}")
            return
        await self._attach_selected_session()

    async def _attach_selected_session(self) -> None:
        if self._selected_agent_id is None:
            self._write_system("No agent selected. Click a card or use Ctrl/Cmd+1..9 first.")
            return
        record = self.orchestrator.registry.get(self._selected_agent_id)
        if record is None:
            self._write_system("Selected agent is no longer available")
            self._selected_agent_id = None
            self._refresh_all()
            return
        with self.suspend():
            response = await self.orchestrator.attach_agent_session_by_id(record.agent_id)
        if response:
            self._write_system(response)
            return
        self._write_system(f"Returned from tmux session @{record.name}")
