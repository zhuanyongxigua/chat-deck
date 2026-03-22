from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import sys
from pathlib import Path

from relay_deck.runtime_events import (
    RuntimeEventInbox,
    TaskDoneEvent,
    TaskDoneInbox,
    TurnResult,
    WorkerReport,
)


DONE_RE = re.compile(r"<TASK_DONE>\s*(\{.*?\})\s*</TASK_DONE>", re.S)


def _read_optional_json(stdin_data: str, payload_json: str | None) -> dict[str, object]:
    if payload_json:
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            raise ValueError("--payload-json must decode to an object")
        return payload
    text = stdin_data.strip()
    if not text:
        return {}
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("stdin payload must decode to an object")
    return payload


def _find_nested_value(payload: object, candidate_keys: set[str]) -> object | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in candidate_keys:
                return value
        for value in payload.values():
            found = _find_nested_value(value, candidate_keys)
            if found is not None:
                return found
        return None
    if isinstance(payload, list):
        for value in payload:
            found = _find_nested_value(value, candidate_keys)
            if found is not None:
                return found
    return None


def _handle_report(args: argparse.Namespace) -> None:
    stdin_data = sys.stdin.read()
    try:
        payload = _read_optional_json(stdin_data, args.payload_json)
    except ValueError as exc:
        raise SystemExit(f"Invalid report payload: {exc}") from exc
    report = WorkerReport(
        agent_id=args.agent_id,
        source=args.source,
        event_name=args.event_name,
        message=args.message or "",
        summary=args.summary or "",
        state=args.state,
        payload=payload,
    )
    inbox = RuntimeEventInbox(Path(args.runtime_dir).expanduser())
    inbox.write_report(report)


def _find_nested_string(payload: object, candidate_keys: set[str]) -> str | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in candidate_keys and isinstance(value, str) and value.strip():
                return value.strip()
        for value in payload.values():
            found = _find_nested_string(value, candidate_keys)
            if found:
                return found
        return None
    if isinstance(payload, list):
        for value in payload:
            found = _find_nested_string(value, candidate_keys)
            if found:
                return found
    return None


def _extract_text_fragments(payload: object) -> list[str]:
    fragments: list[str] = []
    if isinstance(payload, str):
        text = payload.strip()
        if text:
            fragments.append(text)
        return fragments
    if isinstance(payload, list):
        for value in payload:
            fragments.extend(_extract_text_fragments(value))
        return fragments
    if not isinstance(payload, dict):
        return fragments

    content = payload.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                text = item["text"].strip()
                if text:
                    fragments.append(text)
            else:
                fragments.extend(_extract_text_fragments(item))
    for key in (
        "text",
        "summary",
        "body",
        "output_text",
        "outputText",
        "last_assistant_message",
        "lastAssistantMessage",
        "assistant_message",
        "assistantMessage",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            fragments.append(value.strip())
    return fragments


def _extract_assistant_summary(payload: object) -> str:
    if isinstance(payload, dict):
        role = str(payload.get("role") or "").lower()
        if role in {"assistant", "model"}:
            fragments = _extract_text_fragments(payload)
            if fragments:
                return "\n".join(dict.fromkeys(fragments))
        for value in payload.values():
            found = _extract_assistant_summary(value)
            if found:
                return found
        return ""
    if isinstance(payload, list):
        for value in payload:
            found = _extract_assistant_summary(value)
            if found:
                return found
    return ""


def _codex_notify_state(event_name: str) -> str:
    normalized = event_name.strip().lower()
    if "error" in normalized or "fail" in normalized:
        return "error"
    if "complete" in normalized or "done" in normalized:
        return "completed"
    return "working"


def _build_codex_notify_report(args: argparse.Namespace) -> WorkerReport:
    payload = _read_optional_json("", args.payload_json or "")
    summary = _extract_assistant_summary(payload) or _find_nested_string(
        payload,
        {
            "last_assistant_message",
            "lastAssistantMessage",
            "assistant_message",
            "assistantMessage",
            "summary",
        },
    ) or ""
    message = _find_nested_string(
        payload,
        {
            "message",
            "status_message",
            "statusMessage",
            "reason",
            "title",
        },
    )
    if not message:
        message = "Codex completed its current turn" if _codex_notify_state(args.event_name) == "completed" else (
            f"Codex reported {args.event_name}"
        )
    return WorkerReport(
        agent_id=args.agent_id,
        source="codex",
        event_name=args.event_name,
        message=message,
        summary=summary,
        state=_codex_notify_state(args.event_name),
        payload=payload,
    )


def _handle_codex_notify(args: argparse.Namespace) -> None:
    try:
        report = _build_codex_notify_report(args)
    except ValueError as exc:
        raise SystemExit(f"Invalid Codex notify payload: {exc}") from exc
    inbox = RuntimeEventInbox(Path(args.runtime_dir).expanduser())
    inbox.write_report(report)


def _handle_turn_result(args: argparse.Namespace) -> None:
    result = TurnResult(
        agent_id=args.agent_id,
        turn_id=args.turn_id,
        status=args.status,
        summary=args.summary,
        next_step=args.next_step or "",
        risks=list(args.risks or []),
    )
    inbox = RuntimeEventInbox(Path(args.runtime_dir).expanduser())
    inbox.write_turn_result(result)


def _extract_last_assistant_message(payload: dict[str, object]) -> str:
    found = _find_nested_value(
        payload,
        {
            "last_assistant_message",
            "last-assistant-message",
            "lastAssistantMessage",
            "assistant_message",
            "assistant-message",
            "assistantMessage",
        },
    )
    return str(found or "").strip()


def _format_task_done_event(done: dict[str, object], *, agent_id: str, tool: str, payload: dict[str, object], message: str) -> TaskDoneEvent:
    session_id = str(
        payload.get("session_id")
        or payload.get("session-id")
        or payload.get("thread-id")
        or payload.get("thread_id")
        or ""
    )
    return TaskDoneEvent(
        agent_id=agent_id,
        tool=tool,
        summary=str(done.get("summary") or ""),
        result=str(done.get("result") or ""),
        next_step=str(done.get("next") or done.get("next_step") or ""),
        cwd=str(payload.get("cwd") or ""),
        session_id=session_id,
        raw_message=message,
    )


def _publish_task_done_if_present(*, tool: str, agent_id: str, payload: dict[str, object], inbox_path: str | None) -> None:
    message = _extract_last_assistant_message(payload)
    match = DONE_RE.search(message)
    if not match:
        return
    try:
        done_payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return
    if not isinstance(done_payload, dict):
        return
    event = _format_task_done_event(done_payload, agent_id=agent_id, tool=tool, payload=payload, message=message)
    TaskDoneInbox(Path(inbox_path).expanduser() if inbox_path else None).append(event)


def _write_runtime_report(*, runtime_dir: str, report: WorkerReport) -> None:
    inbox = RuntimeEventInbox(Path(runtime_dir).expanduser())
    inbox.write_report(report)


def _build_claude_stop_report(*, agent_id: str, event_name: str, payload: dict[str, object]) -> WorkerReport:
    if event_name == "Stop":
        return WorkerReport(
            agent_id=agent_id,
            source="claude",
            event_name=event_name,
            message="Claude completed its current turn",
            state="completed",
            payload=payload,
        )
    if event_name == "Notification":
        return WorkerReport(
            agent_id=agent_id,
            source="claude",
            event_name=event_name,
            payload=payload,
        )
    if event_name == "PermissionRequest":
        return WorkerReport(
            agent_id=agent_id,
            source="claude",
            event_name=event_name,
            message="Claude is waiting for permission",
            state="waiting",
            payload=payload,
        )
    if event_name == "SessionEnd":
        return WorkerReport(
            agent_id=agent_id,
            source="claude",
            event_name=event_name,
            message=str(payload.get("reason") or "Claude session ended"),
            payload=payload,
        )
    return WorkerReport(
        agent_id=agent_id,
        source="claude",
        event_name=event_name,
        payload=payload,
    )


def _handle_publish_done(args: argparse.Namespace) -> None:
    if args.tool == "claude":
        payload = _read_optional_json(sys.stdin.read(), args.payload_json or args.payload_json_positional)
        report = _build_claude_stop_report(
            agent_id=args.agent_id,
            event_name=args.event_name,
            payload=payload,
        )
    elif args.tool == "codex":
        payload = _read_optional_json("", args.payload_json or args.payload_json_positional or "")
        report = WorkerReport(
            agent_id=args.agent_id,
            source="codex",
            event_name=args.event_name,
            message="Codex completed its current turn" if _codex_notify_state(args.event_name) == "completed" else f"Codex reported {args.event_name}",
            state=_codex_notify_state(args.event_name),
            payload=payload,
        )
    else:
        raise SystemExit(f"Unknown tool: {args.tool}")
    _write_runtime_report(runtime_dir=args.runtime_dir, report=report)
    _publish_task_done_if_present(
        tool=args.tool,
        agent_id=args.agent_id,
        payload=payload,
        inbox_path=args.inbox,
    )


def _read_os_release() -> str:
    path = Path("/etc/os-release")
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _tmux_install_hint(*, system_name: str | None = None, os_release_text: str | None = None) -> str:
    normalized_system = (system_name or platform.system()).strip().lower()
    release = (os_release_text or _read_os_release()).lower()
    if normalized_system == "darwin":
        return "Install tmux first: brew install tmux"
    if normalized_system == "linux":
        if "ubuntu" in release or "debian" in release:
            return "Install tmux first: sudo apt install tmux"
        if "fedora" in release or "rhel" in release or "centos" in release:
            return "Install tmux first: sudo dnf install tmux"
        if "arch" in release:
            return "Install tmux first: sudo pacman -S tmux"
        return "Install tmux with your distro package manager and make sure it is on PATH."
    return "Install tmux and make sure it is on PATH."


def _ensure_tmux_available(*, demo: bool, which=shutil.which) -> None:
    if demo:
        return
    if which("tmux"):
        return
    raise SystemExit(
        "tmux is required to run Relay Deck outside demo mode.\n"
        f"{_tmux_install_hint()}\n"
        "Use `relay-deck --demo` if you only want to preview the UI.\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Relay Deck TUI")
    subparsers = parser.add_subparsers(dest="subcommand")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Start the TUI with two simulated agents so the layout and event flow can be exercised without external CLIs.",
    )
    report_parser = subparsers.add_parser(
        "report",
        help="Write a semantic worker report into a Relay Deck runtime directory.",
    )
    report_parser.add_argument("--runtime-dir", required=True)
    report_parser.add_argument("--agent-id", required=True)
    report_parser.add_argument("--source", required=True)
    report_parser.add_argument("--event", dest="event_name", required=True)
    report_parser.add_argument("--message")
    report_parser.add_argument("--summary")
    report_parser.add_argument("--state")
    report_parser.add_argument("--payload-json")
    codex_notify_parser = subparsers.add_parser(
        "codex-notify",
        help="Translate a Codex notify callback into a Relay Deck runtime report.",
    )
    codex_notify_parser.add_argument("--runtime-dir", required=True)
    codex_notify_parser.add_argument("--agent-id", required=True)
    codex_notify_parser.add_argument("--event", dest="event_name", default="agent-turn-complete")
    codex_notify_parser.add_argument("payload_json", nargs="?")
    turn_result_parser = subparsers.add_parser(
        "turn-result",
        help="Write a structured per-turn result for a worker into a Relay Deck runtime directory.",
    )
    turn_result_parser.add_argument("--runtime-dir", required=True)
    turn_result_parser.add_argument("--agent-id", required=True)
    turn_result_parser.add_argument("--turn-id", required=True)
    turn_result_parser.add_argument("--status", default="completed")
    turn_result_parser.add_argument("--summary", required=True)
    turn_result_parser.add_argument("--next-step")
    turn_result_parser.add_argument("--risk", dest="risks", action="append", default=[])
    publish_done_parser = subparsers.add_parser(
        "publish-done",
        help="Handle Claude/Codex completion callbacks and publish TASK_DONE payloads into the local inbox.",
    )
    publish_done_parser.add_argument("--tool", choices=("claude", "codex"), required=True)
    publish_done_parser.add_argument("--runtime-dir", required=True)
    publish_done_parser.add_argument("--agent-id", required=True)
    publish_done_parser.add_argument("--event", dest="event_name", required=True)
    publish_done_parser.add_argument("--inbox")
    publish_done_parser.add_argument("--payload-json")
    publish_done_parser.add_argument("payload_json_positional", nargs="?")
    args = parser.parse_args()
    if args.subcommand == "report":
        _handle_report(args)
        return
    if args.subcommand == "codex-notify":
        _handle_codex_notify(args)
        return
    if args.subcommand == "turn-result":
        _handle_turn_result(args)
        return
    if args.subcommand == "publish-done":
        _handle_publish_done(args)
        return
    _ensure_tmux_available(demo=args.demo)
    try:
        from relay_deck.app import RelayDeckApp
    except ModuleNotFoundError as exc:
        if exc.name == "textual":
            parser.exit(
                1,
                "Missing dependency: textual. Install project dependencies with `pip install -e .`.\n",
            )
        raise

    app = RelayDeckApp(demo=args.demo)
    app.run()


if __name__ == "__main__":
    main()
