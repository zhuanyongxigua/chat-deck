import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdtempSync, mkdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { findCodexPromptSubmission, waitForCodexPromptSubmission } from "../src/lib/codex-session";

describe("codex session helpers", () => {
  let tempHome = "";
  const previousHome = process.env.HOME;

  beforeEach(() => {
    tempHome = mkdtempSync(join(tmpdir(), "chat-deck-codex-home-"));
    process.env.HOME = tempHome;
  });

  afterEach(() => {
    if (previousHome === undefined) {
      delete process.env.HOME;
    } else {
      process.env.HOME = previousHome;
    }

    if (tempHome) {
      rmSync(tempHome, { recursive: true, force: true });
    }
  });

  test("finds a submitted prompt for the matching cwd", () => {
    const codexDir = join(tempHome, ".codex");
    const sessionsDir = join(codexDir, "sessions", "2026", "04", "06");
    mkdirSync(sessionsDir, { recursive: true });
    writeFileSync(
      join(codexDir, "history.jsonl"),
      `${JSON.stringify({ session_id: "session-1", ts: 1_777_000_000, text: "hello" })}\n`,
      "utf8",
    );
    writeFileSync(
      join(sessionsDir, "rollout-2026-04-06T10-00-00-session-1.jsonl"),
      `${JSON.stringify({ payload: { cwd: "/tmp/demo" } })}\n`,
      "utf8",
    );

    expect(findCodexPromptSubmission("/tmp/demo", "hello", 1_776_999_999_000)).toEqual({
      sessionId: "session-1",
      tsMs: 1_777_000_000_000,
    });
  });

  test("ignores a matching prompt from a different cwd", () => {
    const codexDir = join(tempHome, ".codex");
    const sessionsDir = join(codexDir, "sessions", "2026", "04", "06");
    mkdirSync(sessionsDir, { recursive: true });
    writeFileSync(
      join(codexDir, "history.jsonl"),
      `${JSON.stringify({ session_id: "session-2", ts: 1_777_000_001, text: "hello" })}\n`,
      "utf8",
    );
    writeFileSync(
      join(sessionsDir, "rollout-2026-04-06T10-00-01-session-2.jsonl"),
      `${JSON.stringify({ payload: { cwd: "/tmp/other" } })}\n`,
      "utf8",
    );

    expect(findCodexPromptSubmission("/tmp/demo", "hello", 1_776_999_999_000)).toBeNull();
  });

  test("matches prompts when Chat Deck cwd is a symlink to the rollout cwd", () => {
    const codexDir = join(tempHome, ".codex");
    const sessionsDir = join(codexDir, "sessions", "2026", "04", "06");
    const realProjectDir = join(tempHome, "workspace", "real-project");
    const linkedProjectDir = join(tempHome, "workspace", "linked-project");
    mkdirSync(sessionsDir, { recursive: true });
    mkdirSync(realProjectDir, { recursive: true });
    symlinkSync(realProjectDir, linkedProjectDir);
    writeFileSync(
      join(codexDir, "history.jsonl"),
      `${JSON.stringify({ session_id: "session-2b", ts: 1_777_000_001, text: "hello" })}\n`,
      "utf8",
    );
    writeFileSync(
      join(sessionsDir, "rollout-2026-04-06T10-00-01-session-2b.jsonl"),
      `${JSON.stringify({ payload: { cwd: realProjectDir } })}\n`,
      "utf8",
    );

    expect(findCodexPromptSubmission(linkedProjectDir, "hello", 1_776_999_999_000)).toEqual({
      sessionId: "session-2b",
      tsMs: 1_777_000_001_000,
    });
  });

  test("waits until a prompt appears in Codex history", async () => {
    const codexDir = join(tempHome, ".codex");
    const sessionsDir = join(codexDir, "sessions", "2026", "04", "06");
    mkdirSync(sessionsDir, { recursive: true });
    writeFileSync(join(codexDir, "history.jsonl"), "", "utf8");

    const pending = waitForCodexPromptSubmission("/tmp/demo", "hello", 1_776_999_999_000, {
      timeoutMs: 300,
      pollMs: 20,
    });

    setTimeout(() => {
      writeFileSync(
        join(codexDir, "history.jsonl"),
        `${JSON.stringify({ session_id: "session-3", ts: 1_777_000_002, text: "hello" })}\n`,
        "utf8",
      );
      writeFileSync(
        join(sessionsDir, "rollout-2026-04-06T10-00-02-session-3.jsonl"),
        `${JSON.stringify({ payload: { cwd: "/tmp/demo" } })}\n`,
        "utf8",
      );
    }, 30);

    await expect(pending).resolves.toEqual({
      sessionId: "session-3",
      tsMs: 1_777_000_002_000,
    });
  });
});
