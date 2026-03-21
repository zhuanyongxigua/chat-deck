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
        ("super+0,ctrl+0,escape", "detach_agent", "Controller"),
        ("super+1,ctrl+1", "attach_agent_slot(1)", "Agent 1"),
        ("super+2,ctrl+2", "attach_agent_slot(2)", "Agent 2"),
        ("super+3,ctrl+3", "attach_agent_slot(3)", "Agent 3"),
        ("super+4,ctrl+4", "attach_agent_slot(4)", "Agent 4"),
        ("super+5,ctrl+5", "attach_agent_slot(5)", "Agent 5"),
        ("super+6,ctrl+6", "attach_agent_slot(6)", "Agent 6"),
        ("super+7,ctrl+7", "attach_agent_slot(7)", "Agent 7"),
        ("super+8,ctrl+8", "attach_agent_slot(8)", "Agent 8"),
        ("super+9,ctrl+9", "attach_agent_slot(9)", "Agent 9"),
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
        self._active_agent_id: str | None = None
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
                    placeholder="Type /new ... or @agent-name ...",
                    id="command-input",
                    compact=True,
                )

    async def on_mount(self) -> None:
        self.query_one(Input).focus()
        self._event_queue = await self.orchestrator.bus.subscribe()
        self._event_task = asyncio.create_task(self._consume_events())
        self.set_interval(0.2, self._advance_animation)
        self._write_system(
            "Commands: /help, /agents, /new <codex|claude> <name> <cwd>, @agent-name <message>"
        )
        self._write_system("The sidebar keeps all agent status visible without opening extra panes.")
        self._write_system("Toggle sidebar with B or Ctrl+B. Cmd+B depends on terminal key forwarding.")
        self._write_system("Click a sidebar card or use Ctrl/Cmd+1..9 to attach to an agent session.")
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
        if self._active_agent_id is not None:
            await self._send_to_active_agent(raw)
        else:
            self._write_user(raw)
            response = await self.orchestrator.handle_input(raw)
            if response:
                self._write_system(response)
        self._refresh_all()

    async def action_refresh_views(self) -> None:
        self._refresh_all()
        self._write_system("Views refreshed")

    async def action_toggle_sidebar(self) -> None:
        self._sidebar_visible = not self._sidebar_visible
        self.query_one(AgentSidebar).display = self._sidebar_visible
        self._write_system("Sidebar shown" if self._sidebar_visible else "Sidebar hidden")
        self._refresh_all()

    async def action_attach_agent_slot(self, slot: int) -> None:
        record = self.orchestrator.registry.get_by_index(slot - 1)
        if record is None:
            self._write_system(f"No agent mapped to slot {slot}")
            return
        self._attach_agent(record.agent_id)

    async def action_detach_agent(self) -> None:
        if self._active_agent_id is None:
            return
        self._active_agent_id = None
        self.query_one(Input).placeholder = "Type /new ... or @agent-name ..."
        self._write_system("Returned to controller view")
        self._render_workspace()
        self._refresh_all()

    async def on_agent_card_selected(self, event: AgentCard.Selected) -> None:
        self._attach_agent(event.agent_id)

    async def on_agent_sidebar_background_selected(self, event: AgentSidebar.BackgroundSelected) -> None:
        await self.action_detach_agent()

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
        self.query_one(StatusBar).set_records(records, self._animation_tick)
        self.query_one(AgentSidebar).set_records(records, self._animation_tick, self._active_agent_id)
        self._update_workspace_header()

    def _write_user(self, text: str) -> None:
        self._controller_history.append((f"> {text}", "bold cyan"))
        if self._active_agent_id is None:
            self.query_one(RichLog).write(Text(f"> {text}", style="bold cyan"))

    def _write_system(self, text: str) -> None:
        self._controller_history.append((text, "white"))
        if self._active_agent_id is None:
            self.query_one(RichLog).write(Text(text, style="white"))

    def _handle_event(self, event: AgentEvent) -> None:
        if event.type == EventType.CONTROLLER:
            self._write_system(event.message)
            return
        if self._active_agent_id is None:
            label = event.agent_id or "system"
            style = self._style_for_event(event)
            line = f"[{label}] {event.type.value}: {event.message}"
            self._controller_history.append((line, style))
            self.query_one(RichLog).write(Text(line, style=style))
            return

        if event.agent_id == self._active_agent_id:
            self.orchestrator.registry.mark_read(self._active_agent_id)
            if event.type in {
                EventType.MESSAGE_SENT,
                EventType.OUTPUT,
                EventType.ERROR,
                EventType.COMPLETED,
                EventType.STARTED,
            }:
                self._append_active_agent_line(event)

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

    async def _send_to_active_agent(self, raw: str) -> None:
        if not raw.strip():
            return
        record = self.orchestrator.registry.get(self._active_agent_id) if self._active_agent_id else None
        if record is None:
            self._write_system("Active agent is no longer available")
            self._active_agent_id = None
            self._render_workspace()
            return
        response = await self.orchestrator.send_to_agent(record.name, raw)
        if not response.startswith(f"Sent to @{record.name}:"):
            self._write_system(response)

    def _attach_agent(self, agent_id: str) -> None:
        record = self.orchestrator.registry.get(agent_id)
        if record is None:
            self._write_system("Selected agent is no longer available")
            return
        self._active_agent_id = agent_id
        self.orchestrator.registry.mark_read(agent_id)
        self.query_one(Input).placeholder = f"Attached to @{record.name}. Enter sends input directly. Esc detaches."
        self._render_workspace()
        self._refresh_all()

    def _render_workspace(self) -> None:
        log = self.query_one(RichLog)
        log.clear()

        if self._active_agent_id is None:
            for line, style in self._controller_history:
                log.write(Text(line, style=style), scroll_end=False)
            return

        record = self.orchestrator.registry.get(self._active_agent_id)
        if record is None:
            self._active_agent_id = None
            self._render_workspace()
            return
        for line in record.transcript:
            log.write(Text(line.text, style=line.style), scroll_end=False)

    def _update_workspace_header(self) -> None:
        header = self.query_one("#workspace-header", Static)
        if self._active_agent_id is None:
            header.update("Controller")
            return
        record = self.orchestrator.registry.get(self._active_agent_id)
        if record is None:
            header.update("Controller")
            return
        header.update(
            f"Attached to @{record.name}  {record.tool_type.client_label}  {record.cwd}  Esc to detach"
        )

    def _append_active_agent_line(self, event: AgentEvent) -> None:
        record = self.orchestrator.registry.get(self._active_agent_id) if self._active_agent_id else None
        if record is None or not record.transcript:
            return
        line = record.transcript[-1]
        self.query_one(RichLog).write(Text(line.text, style=line.style))
