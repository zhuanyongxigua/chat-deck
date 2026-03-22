from __future__ import annotations

import json
import os
import shlex
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from relay_deck.models import utc_now


@dataclass(slots=True)
class WorkerReport:
    agent_id: str
    source: str
    event_name: str
    message: str = ""
    summary: str = ""
    state: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "source": self.source,
            "event_name": self.event_name,
            "message": self.message,
            "summary": self.summary,
            "state": self.state,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkerReport:
        created_at_raw = data.get("created_at")
        created_at = utc_now()
        if isinstance(created_at_raw, str):
            try:
                created_at = datetime.fromisoformat(created_at_raw)
            except ValueError:
                created_at = utc_now()
        return cls(
            agent_id=str(data["agent_id"]),
            source=str(data["source"]),
            event_name=str(data["event_name"]),
            message=str(data.get("message") or ""),
            summary=str(data.get("summary") or ""),
            state=str(data["state"]) if data.get("state") is not None else None,
            payload=dict(data.get("payload") or {}),
            created_at=created_at,
        )


class RuntimeEventInbox:
    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = runtime_dir
        self.events_dir = runtime_dir / "events"
        self.agent_artifacts_dir = runtime_dir / "agents"

    def ensure(self) -> None:
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.agent_artifacts_dir.mkdir(parents=True, exist_ok=True)

    def agent_dir(self, agent_id: str) -> Path:
        path = self.agent_artifacts_dir / agent_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_report(self, report: WorkerReport) -> Path:
        self.ensure()
        final_path = self.events_dir / f"{report.created_at.timestamp():020.6f}-{uuid.uuid4().hex}.json"
        temp_path = final_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(report.to_dict(), ensure_ascii=True), encoding="utf-8")
        os.replace(temp_path, final_path)
        return final_path

    def drain(self) -> list[WorkerReport]:
        self.ensure()
        reports: list[WorkerReport] = []
        for path in sorted(self.events_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                reports.append(WorkerReport.from_dict(payload))
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass
            finally:
                path.unlink(missing_ok=True)
        return reports


def build_report_argv(
    *,
    python_executable: str,
    runtime_dir: Path,
    agent_id: str,
    source: str,
    event_name: str,
    state: str | None = None,
    message: str | None = None,
    summary: str | None = None,
    expect_payload_json: bool = False,
) -> list[str]:
    argv = [
        python_executable,
        "-m",
        "relay_deck",
        "report",
        "--runtime-dir",
        str(runtime_dir),
        "--agent-id",
        agent_id,
        "--source",
        source,
        "--event",
        event_name,
    ]
    if state is not None:
        argv.extend(["--state", state])
    if message is not None:
        argv.extend(["--message", message])
    if summary is not None:
        argv.extend(["--summary", summary])
    if expect_payload_json:
        argv.append("--payload-json")
    return argv


def build_report_command(
    *,
    python_executable: str,
    runtime_dir: Path,
    agent_id: str,
    source: str,
    event_name: str,
    state: str | None = None,
    message: str | None = None,
    summary: str | None = None,
    expect_payload_json: bool = False,
) -> str:
    return shlex.join(
        build_report_argv(
            python_executable=python_executable,
            runtime_dir=runtime_dir,
            agent_id=agent_id,
            source=source,
            event_name=event_name,
            state=state,
            message=message,
            summary=summary,
            expect_payload_json=expect_payload_json,
        )
    )


def build_codex_notify_argv(
    *,
    python_executable: str,
    runtime_dir: Path,
    agent_id: str,
    event_name: str = "agent-turn-complete",
) -> list[str]:
    return [
        python_executable,
        "-m",
        "relay_deck",
        "codex-notify",
        "--runtime-dir",
        str(runtime_dir),
        "--agent-id",
        agent_id,
        "--event",
        event_name,
    ]
