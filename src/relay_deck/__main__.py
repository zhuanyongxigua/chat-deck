from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from pathlib import Path

from relay_deck.runtime_events import RuntimeEventInbox, WorkerReport


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


def _codex_notify_state(event_name: str) -> str:
    normalized = event_name.strip().lower()
    if "error" in normalized or "fail" in normalized:
        return "error"
    if "complete" in normalized or "done" in normalized:
        return "completed"
    return "working"


def _build_codex_notify_report(args: argparse.Namespace) -> WorkerReport:
    payload = _read_optional_json("", args.payload_json or "")
    summary = _find_nested_string(
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
    args = parser.parse_args()
    if args.subcommand == "report":
        _handle_report(args)
        return
    if args.subcommand == "codex-notify":
        _handle_codex_notify(args)
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
