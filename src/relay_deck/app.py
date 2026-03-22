from __future__ import annotations

import asyncio
import contextlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.message import Message
from textual.widgets import Input, Static

from relay_deck.models import AgentEvent, AgentSpec, AgentState, EventType, ToolType, display_state_label
from relay_deck.orchestrator import Orchestrator
from relay_deck.runtime_events import default_task_done_inbox_path
from relay_deck.widgets.agent_sidebar import AgentCard, AgentSidebar
from relay_deck.widgets.history_input import HistoryInput
from relay_deck.widgets.status_bar import StatusBar


class SidebarResizer(Static):
    class Dragged(Message):
        def __init__(self, screen_x: float) -> None:
            self.screen_x = screen_x
            super().__init__()

    def __init__(self) -> None:
        super().__init__("", id="sidebar-resizer")
        self._dragging = False

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self._dragging = True
        self.capture_mouse(True)
        self.add_class("-dragging")
        event.stop()
        self.post_message(self.Dragged(event.screen_x if event.screen_x is not None else self.region.x + event.x))

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if not self._dragging:
            return
        event.stop()
        self.post_message(self.Dragged(event.screen_x if event.screen_x is not None else self.region.x + event.x))

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.capture_mouse(False)
        self.remove_class("-dragging")
        event.stop()


class RelayDeckApp(App[None]):
    WORKING_SPINNER_FRAMES = ("◐", "◓", "◑", "◒")
    COMMAND_SPECS = [
        ("/help", "Show available commands"),
        ("/agents", "List current agents"),
        ("/new", "Create a Claude or Codex agent"),
        ("/attach", "Open the selected agent tmux session"),
        ("/close", "Close the selected or named agent"),
    ]

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
        width: 32%;
        height: 100%;
        min-width: 32;
        padding: 0;
        background: rgb(14, 22, 31);
        overflow-y: auto;
    }

    #sidebar-resizer {
        width: 1;
        height: 100%;
        background: rgb(42, 62, 82);
    }

    #sidebar-resizer:hover {
        background: rgb(88, 119, 150);
    }

    #sidebar-resizer.-dragging {
        background: rgb(127, 179, 255);
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
        padding: 0 0 0 1;
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

    #log-scroll {
        height: 1fr;
        margin: 0;
        background: rgb(15, 24, 34);
        padding: 0;
        scrollbar-background: rgb(15, 24, 34);
        scrollbar-color: rgb(42, 62, 82);
        scrollbar-color-hover: rgb(62, 82, 102);
    }

    #controller-log {
        width: 1fr;
        height: auto;
        min-height: 100%;
        margin: 0;
        padding: 0;
        background: rgb(15, 24, 34);
        color: rgb(239, 241, 245);
    }

    #footer-stack {
        height: 5;
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
        height: 2;
        margin: 0 1;
        padding: 0;
        content-align: left middle;
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
        ("ctrl+c", "copy_selection", "Copy"),
        ("ctrl+v", "paste_clipboard", "Paste"),
        Binding("ctrl+x", "close_selected_agent", "Close Agent", priority=True, show=False),
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
        done_inbox_path = history_path.parent / "inbox.jsonl" if history_path is not None else default_task_done_inbox_path()
        self.orchestrator = Orchestrator(done_inbox_path=done_inbox_path)
        self._event_queue: asyncio.Queue[AgentEvent] | None = None
        self._event_task: asyncio.Task[None] | None = None
        self._animation_timer = None
        self._animation_tick = 0
        self._sidebar_visible = True
        self._sidebar_width_percent = 32.0
        self._selected_agent_id: str | None = None
        self._controller_history: list[tuple[str, str]] = []
        self._footer_message = ""
        self._footer_error = False
        self._command_matches: list[tuple[str, str]] = []
        self._command_match_index = 0

    def compose(self) -> ComposeResult:
        yield StatusBar()
        with Horizontal(id="body"):
            yield AgentSidebar()
            yield SidebarResizer()
            with Vertical(id="workspace"):
                with Vertical(id="main-column"):
                    yield Static(id="workspace-header")
                    with VerticalScroll(id="log-scroll"):
                        yield Static(id="controller-log")
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
        self._apply_sidebar_width()
        self._write_system(
            "Commands: /help, /agents, /new <codex|claude> <name> <cwd> [client args...], /attach [agent-name], /close [agent-name], @agent-name <message>"
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
        display_text = event.value
        input_widget = self.query_one(HistoryInput)
        actual_text = input_widget.expand_value(display_text)
        input_widget.remember(display_text)
        input_widget.value = ""
        input_widget.clear_collapsed_pastes()
        self._update_command_suggestions("")
        if self._selected_agent_id is not None and not display_text.startswith("/") and not display_text.startswith("@") and not actual_text.strip():
            await self._send_to_selected_agent("")
            self._refresh_all()
            self._focus_input()
            return
        if not actual_text.strip():
            self._focus_input()
            return
        if self._selected_agent_id is not None and not display_text.startswith("/") and not display_text.startswith("@"):
            await self._send_to_selected_agent(actual_text, display_text=display_text)
        else:
            self._write_user(display_text)
            result = self.orchestrator.router.parse(actual_text)
            if result.kind == "close_agent" and result.target is None and self._selected_agent_id is not None:
                selected = self.orchestrator.registry.get(self._selected_agent_id)
                if selected is not None:
                    result.target = selected.name
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

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "command-input":
            return
        self._update_command_suggestions(event.value)

    async def on_history_input_command_suggestion_requested(self, event: HistoryInput.CommandSuggestionRequested) -> None:
        if not self._command_matches:
            return
        input_widget = self.query_one(HistoryInput)
        current_value = input_widget.value.strip()
        selected_command, _ = self._command_matches[self._command_match_index]
        if current_value == selected_command and len(self._command_matches) > 1:
            step = -1 if event.reverse else 1
            self._command_match_index = (self._command_match_index + step) % len(self._command_matches)
            selected_command, _ = self._command_matches[self._command_match_index]
        suffix = " " if selected_command in {"/new", "/attach", "/close"} else ""
        input_widget.value = f"{selected_command}{suffix}"
        input_widget.cursor_position = len(input_widget.value)
        self._update_command_suggestions(input_widget.value)

    def action_copy_selection(self) -> None:
        input_widget = self.query_one(HistoryInput)
        copied_text = self.screen.get_selected_text() or input_widget.selected_text
        if not copied_text:
            self._set_footer_message("Nothing selected to copy")
            return
        self.copy_to_clipboard(copied_text)
        self._write_system_clipboard(copied_text)
        self._set_footer_message("Copied selection")

    def action_paste_clipboard(self) -> None:
        text = self._read_clipboard_text()
        if not text:
            self._set_footer_message("Clipboard is empty")
            return
        input_widget = self.query_one(HistoryInput)
        input_widget.focus()
        input_widget.insert_pasted_text(text)
        self._set_footer_message("")

    async def action_toggle_sidebar(self) -> None:
        self._sidebar_visible = not self._sidebar_visible
        self.query_one(AgentSidebar).display = self._sidebar_visible
        self.query_one(SidebarResizer).display = self._sidebar_visible
        if self._sidebar_visible:
            self._apply_sidebar_width()
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

    async def action_close_selected_agent(self) -> None:
        if self._selected_agent_id is None:
            self._set_footer_message("No active agent to close")
            self._focus_input()
            return
        response = await self.orchestrator.close_agent_by_id(self._selected_agent_id)
        self._selected_agent_id = None
        if response:
            self._write_system(response)
        self._render_main_log()
        self._refresh_all()
        self._focus_input()

    async def on_agent_card_selected(self, event: AgentCard.Selected) -> None:
        self._select_agent(event.agent_id)

    async def on_agent_sidebar_background_selected(self, event: AgentSidebar.BackgroundSelected) -> None:
        self._focus_input()

    async def on_sidebar_resizer_dragged(self, event: SidebarResizer.Dragged) -> None:
        self._set_sidebar_width_from_screen_x(event.screen_x)

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
            self._render_main_log()

    def _write_system(self, text: str) -> None:
        self._controller_history.append((text, "white"))
        self._set_footer_message(text, error=self._looks_like_error(text))
        if self._selected_agent_id is None:
            self._render_main_log()

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
            self._render_main_log()
            return
        if event.agent_id == self._selected_agent_id:
            self._render_main_log()

    def _style_for_event(self, event: AgentEvent) -> str:
        if event.type == EventType.ERROR or event.state == AgentState.ERROR:
            return "bold red"
        if event.type == EventType.COMPLETED or event.state == AgentState.COMPLETED:
            return "bold green"
        if event.state in {AgentState.WAITING, AgentState.WORKING}:
            return "yellow"
        if event.type == EventType.SUMMARY_UPDATED:
            return "magenta"
        return "white"

    def _advance_animation(self) -> None:
        self._animation_tick += 1
        with contextlib.suppress(NoMatches):
            self._refresh_all()
            if self._selected_agent_id is not None and self._selected_agent_needs_spinner():
                self._render_main_log()

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
            f"@{record.name}  {record.tool_type.client_label}  {display_state_label(record.state)}  Esc returns to controller  Ctrl+T opens tmux"
        )

    def _focus_input(self) -> None:
        self.query_one(HistoryInput).focus()
        self._update_input_placeholder()

    def _set_sidebar_width_from_screen_x(self, screen_x: float) -> None:
        body = self.query_one("#body", Horizontal)
        body_width = max(body.region.width, 1)
        relative_x = max(0.0, min(screen_x - body.region.x, float(body_width)))
        percent = relative_x / body_width * 100.0
        min_percent = min(70.0, max(16.0, (32 / body_width) * 100.0))
        self._sidebar_width_percent = max(min_percent, min(percent, 70.0))
        self._apply_sidebar_width()

    def _apply_sidebar_width(self) -> None:
        sidebar = self.query_one(AgentSidebar)
        sidebar.styles.width = f"{self._sidebar_width_percent:.1f}%"

    def _read_clipboard_text(self) -> str:
        system_clipboard = self._read_system_clipboard()
        if system_clipboard:
            return system_clipboard
        return self.clipboard

    def _read_system_clipboard(self) -> str:
        if sys.platform == "darwin" and shutil.which("pbpaste"):
            try:
                result = subprocess.run(
                    ["pbpaste"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError:
                return ""
            if result.returncode == 0:
                return result.stdout
        return ""

    def _write_system_clipboard(self, text: str) -> bool:
        if sys.platform == "darwin" and shutil.which("pbcopy"):
            try:
                result = subprocess.run(
                    ["pbcopy"],
                    input=text,
                    text=True,
                    capture_output=True,
                    check=False,
                )
            except OSError:
                return False
            return result.returncode == 0
        return False

    def _set_footer_message(self, text: str, *, error: bool = False) -> None:
        self._footer_message = text
        self._footer_error = error
        self._render_footer()

    def _render_footer(self) -> None:
        widget = self.query_one("#footer-message", Static)
        if self._command_matches:
            widget.set_class(False, "error")
            widget.update(self._compose_command_suggestions())
            return
        widget.set_class(self._footer_error, "error")
        widget.update(self._footer_message)

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
        log = self.query_one("#controller-log", Static)
        scroll = self.query_one("#log-scroll", VerticalScroll)
        if self._selected_agent_id is None:
            log.update(self._compose_lines(self._controller_history))
            scroll.scroll_end(animate=False, immediate=True, x_axis=False)
            self._update_input_placeholder()
            return
        record = self.orchestrator.registry.get(self._selected_agent_id)
        if record is None:
            self._selected_agent_id = None
            log.update(self._compose_lines(self._controller_history))
            scroll.scroll_end(animate=False, immediate=True, x_axis=False)
            self._update_input_placeholder()
            return
        if record.chat_transcript:
            log.update(self._compose_agent_chat(record))
        else:
            log.update(Text(f"@{record.name} selected. Waiting for the next agent result...", style="dim"))
        scroll.scroll_end(animate=False, immediate=True, x_axis=False)
        self._update_input_placeholder()

    def _compose_lines(self, lines: Iterable[tuple[str, str]]) -> Text:
        content = Text()
        for index, (text, style) in enumerate(lines):
            if index:
                content.append("\n")
            content.append(text, style=style)
        return content

    def _compose_agent_chat(self, record) -> Text:
        content = Text()
        last_user_line_index = self._last_user_chat_line_index(record)
        show_working_spinner = self._record_needs_spinner(record)
        spinner = self.WORKING_SPINNER_FRAMES[self._animation_tick % len(self.WORKING_SPINNER_FRAMES)]

        for index, line in enumerate(record.chat_transcript):
            if index:
                content.append("\n")
            if show_working_spinner and index == last_user_line_index and line.text.startswith("> "):
                content.append("> ", style="bold cyan")
                content.append(spinner, style="bold green")
                content.append(" ", style="bold cyan")
                content.append(line.text[2:], style=line.style)
                continue
            content.append(line.text, style=line.style)
        return content

    def _last_user_chat_line_index(self, record) -> int | None:
        for index in range(len(record.chat_transcript) - 1, -1, -1):
            if record.chat_transcript[index].text.startswith("> "):
                return index
        return None

    def _record_needs_spinner(self, record) -> bool:
        return record.awaiting_result and record.state in {AgentState.WORKING, AgentState.WAITING}

    def _selected_agent_needs_spinner(self) -> bool:
        if self._selected_agent_id is None:
            return False
        record = self.orchestrator.registry.get(self._selected_agent_id)
        if record is None:
            return False
        return self._record_needs_spinner(record)

    def _update_command_suggestions(self, value: str) -> None:
        text = value.strip()
        if not text.startswith("/") or " " in text:
            self._command_matches = []
            self._command_match_index = 0
            self._render_footer()
            return
        prefix = text
        matches = [item for item in self.COMMAND_SPECS if item[0].startswith(prefix)]
        if not matches and prefix == "/":
            matches = list(self.COMMAND_SPECS)
        if not matches:
            self._command_matches = []
            self._command_match_index = 0
            self._render_footer()
            return
        current_command = self._command_matches[self._command_match_index][0] if self._command_matches else None
        self._command_matches = matches
        if current_command is not None:
            for index, item in enumerate(matches):
                if item[0] == current_command:
                    self._command_match_index = index
                    break
            else:
                self._command_match_index = 0
        else:
            self._command_match_index = 0
        self._render_footer()

    def _compose_command_suggestions(self) -> Text:
        text = Text()
        text.append("Commands: ", style="dim")
        for index, (command, _description) in enumerate(self._command_matches):
            if index:
                text.append("  ", style="dim")
            style = "bold #7FB3FF"
            if index == self._command_match_index:
                style = "bold #7FE5B2"
                text.append("[", style="dim")
                text.append(command, style=style)
                text.append("]", style="dim")
            else:
                text.append(command, style=style)
        if self._command_matches:
            text.append("\n", style="dim")
            text.append(self._command_matches[self._command_match_index][1], style="dim")
            text.append("  Tab to autocomplete", style="dim")
        return text

    async def _send_to_selected_agent(self, text: str, *, display_text: str | None = None) -> None:
        if self._selected_agent_id is None:
            return
        record = self.orchestrator.registry.get(self._selected_agent_id)
        if record is None:
            self._write_system("Selected agent is no longer available")
            self._selected_agent_id = None
            self._render_main_log()
            return
        response = await self.orchestrator.send_to_agent(record.name, text, display_message=display_text)
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
