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
    args = parser.parse_args()
    if args.subcommand == "report":
        _handle_report(args)
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
