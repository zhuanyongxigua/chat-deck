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


@dataclass(slots=True)
class TurnResult:
    agent_id: str
    turn_id: str
    status: str
    summary: str
    next_step: str = ""
    risks: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "turn_id": self.turn_id,
            "status": self.status,
            "summary": self.summary,
            "next_step": self.next_step,
            "risks": self.risks,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TurnResult:
        created_at_raw = data.get("created_at")
        created_at = utc_now()
        if isinstance(created_at_raw, str):
            try:
                created_at = datetime.fromisoformat(created_at_raw)
            except ValueError:
                created_at = utc_now()
        risks_raw = data.get("risks") or []
        risks = [str(item) for item in risks_raw if str(item).strip()]
        return cls(
            agent_id=str(data["agent_id"]),
            turn_id=str(data["turn_id"]),
            status=str(data.get("status") or "completed"),
            summary=str(data.get("summary") or ""),
            next_step=str(data.get("next_step") or ""),
            risks=risks,
            created_at=created_at,
        )


@dataclass(slots=True)
class TaskDoneEvent:
    agent_id: str
    tool: str
    summary: str
    result: str = ""
    next_step: str = ""
    cwd: str = ""
    session_id: str = ""
    raw_message: str = ""
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "tool": self.tool,
            "summary": self.summary,
            "result": self.result,
            "next_step": self.next_step,
            "cwd": self.cwd,
            "session_id": self.session_id,
            "raw_message": self.raw_message,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskDoneEvent:
        created_at_raw = data.get("created_at")
        created_at = utc_now()
        if isinstance(created_at_raw, str):
            try:
                created_at = datetime.fromisoformat(created_at_raw)
            except ValueError:
                created_at = utc_now()
        return cls(
            agent_id=str(data["agent_id"]),
            tool=str(data.get("tool") or ""),
            summary=str(data.get("summary") or ""),
            result=str(data.get("result") or ""),
            next_step=str(data.get("next_step") or ""),
            cwd=str(data.get("cwd") or ""),
            session_id=str(data.get("session_id") or ""),
            raw_message=str(data.get("raw_message") or ""),
            created_at=created_at,
        )


class RuntimeEventInbox:
    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = runtime_dir
        self.events_dir = runtime_dir / "events"
        self.turn_results_dir = runtime_dir / "turn-results"
        self.agent_artifacts_dir = runtime_dir / "agents"

    def ensure(self) -> None:
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.turn_results_dir.mkdir(parents=True, exist_ok=True)
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

    def write_turn_result(self, result: TurnResult) -> Path:
        self.ensure()
        final_path = self.turn_results_dir / f"{result.created_at.timestamp():020.6f}-{result.turn_id}.json"
        temp_path = final_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(result.to_dict(), ensure_ascii=True), encoding="utf-8")
        os.replace(temp_path, final_path)
        return final_path

    def drain_turn_results(self) -> list[TurnResult]:
        self.ensure()
        results: list[TurnResult] = []
        for path in sorted(self.turn_results_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                results.append(TurnResult.from_dict(payload))
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass
            finally:
                path.unlink(missing_ok=True)
        return results


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


def build_turn_result_argv(
    *,
    python_executable: str,
    runtime_dir: Path,
    agent_id: str,
    turn_id: str,
    status: str,
    summary: str,
    next_step: str | None = None,
    risks: list[str] | None = None,
) -> list[str]:
    argv = [
        python_executable,
        "-m",
        "relay_deck",
        "turn-result",
        "--runtime-dir",
        str(runtime_dir),
        "--agent-id",
        agent_id,
        "--turn-id",
        turn_id,
        "--status",
        status,
        "--summary",
        summary,
    ]
    if next_step:
        argv.extend(["--next-step", next_step])
    for risk in risks or []:
        argv.extend(["--risk", risk])
    return argv


def default_task_done_inbox_path() -> Path:
    return Path.home() / ".chat-deck" / "inbox.jsonl"


class TaskDoneInbox:
    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or default_task_done_inbox_path()).expanduser()

    def ensure(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(self, event: TaskDoneEvent) -> None:
        self.ensure()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def drain(self) -> list[TaskDoneEvent]:
        self.ensure()
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            return []
        if not text.strip():
            return []
        self.path.write_text("", encoding="utf-8")
        events: list[TaskDoneEvent] = []
        for raw_line in text.splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                payload = json.loads(raw_line)
                events.append(TaskDoneEvent.from_dict(payload))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
        return events
