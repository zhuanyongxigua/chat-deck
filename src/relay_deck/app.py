from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import Input, RichLog, Static

from relay_deck.models import AgentEvent, AgentSpec, AgentState, EventType, ToolType
from relay_deck.orchestrator import Orchestrator
from relay_deck.widgets.agent_sidebar import AgentCard, AgentSidebar
from relay_deck.widgets.history_input import HistoryInput
from relay_deck.widgets.status_bar import StatusBar


class RelayDeckApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
        background: rgb(11, 17, 24);
        overflow-x: hidden;
        overflow-y: hidden;
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 0;
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
        overflow-x: hidden;
        overflow-y: hidden;
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 0;
    }

    #agent-sidebar {
        width: 40;
        height: 100%;
        min-width: 32;
        max-width: 48;
        padding: 0;
        background: rgb(14, 22, 31);
        border-right: solid rgb(42, 62, 82);
        overflow-y: auto;
    }

    #workspace {
        width: 1fr;
        height: 100%;
        margin: 0;
        padding: 0;
        background: rgb(15, 24, 34);
        overflow-x: hidden;
        overflow-y: hidden;
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 0;
    }

    #agent-sidebar-placeholder {
        color: rgb(130, 147, 166);
        padding: 1 1 0 1;
    }

    .agent-card {
        margin: 0 1 0 1;
        height: auto;
    }

    #main-column {
        width: 1fr;
        height: 1fr;
        padding: 1 0 0 1;
        margin: 0;
        background: rgb(15, 24, 34);
        overflow-x: hidden;
        overflow-y: hidden;
        scrollbar-size-vertical: 0;
        scrollbar-size-horizontal: 0;
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

    #footer-stack {
        height: 4;
        margin: 0;
        padding: 0;
        background: rgb(11, 17, 24);
    }

    #input-bar {
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

    #footer-message {
        height: 1;
        margin: 0 1;
        padding: 0;
        color: rgb(209, 216, 224);
        background: rgb(11, 17, 24);
    }

    #footer-message.error {
        color: rgb(255, 111, 111);
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

    def __init__(
        self,
        *,
        demo: bool = False,
        history_path: Path | None = None,
        history_limit: int = 100,
    ) -> None:
        super().__init__()
        self.demo = demo
        self.history_path = history_path
        self.history_limit = history_limit
        self.orchestrator = Orchestrator()
        self._event_queue: asyncio.Queue[AgentEvent] | None = None
        self._event_task: asyncio.Task[None] | None = None
        self._animation_timer = None
        self._animation_tick = 0
        self._sidebar_visible = True
        self._selected_agent_id: str | None = None
        self._controller_history: list[tuple[str, str]] = []
        self._footer_message = ""

    def compose(self) -> ComposeResult:
        yield StatusBar()
        with Horizontal(id="body"):
            yield AgentSidebar()
            with Vertical(id="workspace"):
                with Vertical(id="main-column"):
                    yield Static(id="workspace-header")
                    yield RichLog(id="controller-log", markup=True, wrap=True, auto_scroll=True)
                with Vertical(id="footer-stack"):
                    with Container(id="input-bar"):
                        with Horizontal(id="input-row"):
                            yield Static(">", id="input-prompt")
                            yield HistoryInput(
                                placeholder="Type /new, /attach or @agent-name ...",
                                id="command-input",
                                compact=True,
                                history_path=self.history_path,
                                history_limit=self.history_limit,
                            )
                    yield Static("", id="footer-message")

    async def on_mount(self) -> None:
        await self.orchestrator.start()
        self._focus_input()
        self._event_queue = await self.orchestrator.bus.subscribe()
        self._event_task = asyncio.create_task(self._consume_events())
        self._animation_timer = self.set_interval(0.2, self._advance_animation)
        self._write_system(
            "Commands: /help, /agents, /new <codex|claude> <name> <cwd>, /attach [agent-name], @agent-name <message>"
        )
        self._write_system("The sidebar keeps all agent status visible without opening extra panes.")
        self._write_system("Claude Code and Codex workers now run inside tmux sessions.")
        self._write_system("Toggle sidebar with B or Ctrl+B. Cmd+B depends on terminal key forwarding.")
        self._write_system("Click a sidebar card or use Ctrl/Cmd+1..9 to select an agent. Ctrl+T opens its tmux session.")
        self._write_system("When an agent is selected, plain input goes to that agent. Press Esc to return to controller.")
        if self.demo:
            await self._bootstrap_demo()
        self._render_main_log()
        self._refresh_all()

    async def on_unmount(self) -> None:
        if self._animation_timer is not None:
            self._animation_timer.stop()
            self._animation_timer = None
        if self._event_task is not None:
            self._event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._event_task
        if self._event_queue is not None:
            await self.orchestrator.bus.unsubscribe(self._event_queue)
        await self.orchestrator.shutdown()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value
        input_widget = self.query_one(HistoryInput)
        input_widget.remember(raw)
        input_widget.value = ""
        if self._selected_agent_id is not None and not raw.startswith("/") and not raw.startswith("@") and not raw.strip():
            await self._send_to_selected_agent("")
            self._refresh_all()
            self._focus_input()
            return
        if not raw.strip():
            self._focus_input()
            return
        if self._selected_agent_id is not None and (raw.startswith("/") or raw.startswith("@")):
            self._selected_agent_id = None
            self._render_main_log()
        if self._selected_agent_id is not None and not raw.startswith("/") and not raw.startswith("@"):
            await self._send_to_selected_agent(raw)
        else:
            self._write_user(raw)
            result = self.orchestrator.router.parse(raw)
            if result.kind == "attach_agent":
                await self._handle_attach_request(result.target)
            else:
                previous_agent_id = None
                if result.kind == "create_agent" and result.name:
                    existing = self.orchestrator.registry.get_by_name(result.name)
                    previous_agent_id = existing.agent_id if existing is not None else None
                response = await self.orchestrator.dispatch(result)
                if response:
                    self._write_system(response)
                if result.kind == "create_agent" and result.name and response.startswith("Created "):
                    record = self.orchestrator.registry.get_by_name(result.name)
                    if record is not None and record.agent_id != previous_agent_id:
                        self._select_agent(record.agent_id)
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
        self._render_main_log()
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
            self._render_main_log()
        self.query_one(StatusBar).set_records(records, self._animation_tick)
        self.query_one(AgentSidebar).set_records(records, self._animation_tick, self._selected_agent_id)
        self._update_workspace_header()

    def _write_user(self, text: str) -> None:
        self._controller_history.append((f"> {text}", "bold cyan"))
        self._set_footer_message("")
        if self._selected_agent_id is None:
            self.query_one(RichLog).write(Text(f"> {text}", style="bold cyan"))

    def _write_system(self, text: str) -> None:
        self._controller_history.append((text, "white"))
        self._set_footer_message(text, error=self._looks_like_error(text))
        if self._selected_agent_id is None:
            self.query_one(RichLog).write(Text(text, style="white"))

    def _handle_event(self, event: AgentEvent) -> None:
        if event.type == EventType.CONTROLLER:
            self._write_system(event.message)
            return
        label = event.agent_id or "system"
        style = self._style_for_event(event)
        line = f"[{label}] {event.type.value}: {event.message}"
        self._controller_history.append((line, style))
        if event.type == EventType.ERROR or event.state == AgentState.ERROR:
            self._set_footer_message(event.message, error=True)
        if self._selected_agent_id is None:
            self.query_one(RichLog).write(Text(line, style=style))
            return
        if event.agent_id == self._selected_agent_id:
            self._render_main_log()

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
        with contextlib.suppress(NoMatches):
            self._refresh_all()

    def _select_agent(self, agent_id: str) -> None:
        record = self.orchestrator.registry.get(agent_id)
        if record is None:
            self._write_system("Selected agent is no longer available")
            return
        self._selected_agent_id = agent_id
        self.orchestrator.registry.mark_read(agent_id)
        self._render_main_log()
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
            f"@{record.name}  {record.tool_type.client_label}  {record.state.value}  Esc returns to controller  Ctrl+T opens tmux"
        )

    def _focus_input(self) -> None:
        self.query_one(HistoryInput).focus()
        self._update_input_placeholder()

    def _set_footer_message(self, text: str, *, error: bool = False) -> None:
        self._footer_message = text
        widget = self.query_one("#footer-message", Static)
        widget.set_class(error, "error")
        widget.update(text)

    def _looks_like_error(self, text: str) -> bool:
        lowered = text.lower()
        error_markers = (
            "error",
            "failed",
            "unknown",
            "does not exist",
            "already exists",
            "required",
            "invalid",
            "unsupported",
        )
        return any(marker in lowered for marker in error_markers)

    def _update_input_placeholder(self) -> None:
        input_widget = self.query_one(HistoryInput)
        if self._selected_agent_id is None:
            input_widget.placeholder = "Ask controller, create agents naturally, or use /new /attach @agent-name ..."
            return
        record = self.orchestrator.registry.get(self._selected_agent_id)
        if record is None:
            input_widget.placeholder = "Ask controller, create agents naturally, or use /new /attach @agent-name ..."
            return
        input_widget.placeholder = f"Message @{record.name} directly, or press Esc to return to controller"

    def _render_main_log(self) -> None:
        log = self.query_one(RichLog)
        log.clear()
        if self._selected_agent_id is None:
            for text, style in self._controller_history:
                log.write(Text(text, style=style))
            self._update_input_placeholder()
            return
        record = self.orchestrator.registry.get(self._selected_agent_id)
        if record is None:
            self._selected_agent_id = None
            for text, style in self._controller_history:
                log.write(Text(text, style=style))
            self._update_input_placeholder()
            return
        if record.chat_transcript:
            for line in record.chat_transcript:
                log.write(Text(line.text, style=line.style))
        else:
            log.write(Text(f"@{record.name} selected. Waiting for the next agent result...", style="dim"))
        self._update_input_placeholder()

    async def _send_to_selected_agent(self, text: str) -> None:
        if self._selected_agent_id is None:
            return
        record = self.orchestrator.registry.get(self._selected_agent_id)
        if record is None:
            self._write_system("Selected agent is no longer available")
            self._selected_agent_id = None
            self._render_main_log()
            return
        response = await self.orchestrator.send_to_agent(record.name, text)
        if response.startswith("Unknown agent") or response.endswith("is not attached"):
            self._write_system(response)
            self._selected_agent_id = None
            self._render_main_log()
            return

    async def _handle_attach_request(self, target: str | None) -> None:
        if target:
            self._write_system(f"Attaching @{target}. Detach with Ctrl+B then d to return.")
            with self.suspend():
                response = await self.orchestrator.attach_agent_session(target)
            if response:
                self._write_system(response)
                return
            self._write_system(f"Returned from tmux session @{target}")
            self._render_main_log()
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
        self._write_system(f"Attaching @{record.name}. Detach with Ctrl+B then d to return.")
        with self.suspend():
            response = await self.orchestrator.attach_agent_session_by_id(record.agent_id)
        if response:
            self._write_system(response)
            return
        self._write_system(f"Returned from tmux session @{record.name}")
        self._render_main_log()
