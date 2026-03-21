from __future__ import annotations

import argparse
import json
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
