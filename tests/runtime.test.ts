import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { readInboxEvents } from "../src/lib/inbox";
import { inboxFilePath } from "../src/lib/paths";
import { prepareWorkerLaunchCommand, publishDoneEventFromPayload } from "../src/lib/worker-runtime";

describe("worker runtime callbacks", () => {
  let tempHome = "";
  const previousHome = process.env.CHAT_DECK_HOME;

  beforeEach(() => {
    tempHome = mkdtempSync(join(tmpdir(), "chat-deck-runtime-"));
    process.env.CHAT_DECK_HOME = tempHome;
  });

  afterEach(() => {
    if (previousHome === undefined) {
      delete process.env.CHAT_DECK_HOME;
    } else {
      process.env.CHAT_DECK_HOME = previousHome;
    }
    if (tempHome) {
      rmSync(tempHome, { recursive: true, force: true });
    }
  });

  test("injects codex notify without touching global config", () => {
    const prepared = prepareWorkerLaunchCommand("codex", "agent-1", "/tmp/demo", ["codex", "--model", "gpt-5"]);

    expect(prepared.runtimeFiles).toEqual([]);
    expect(prepared.command).toEqual([
      "codex",
      "--model",
      "gpt-5",
      "-c",
      expect.stringContaining("notify=["),
    ]);
    expect(prepared.command[4]).toContain("publish-done");
    expect(prepared.command[4]).toContain("\"codex\"");
    expect(prepared.command[4]).toContain("\"agent-1\"");
  });



  test("creates a copilot wrapper with repository-scoped hooks", () => {
    const prepared = prepareWorkerLaunchCommand("copilot", "agent-5", "/tmp/demo", ["copilot", "--model", "gpt-4.1"]);

    expect(prepared.cwd).toContain("copilot-wrapper");
    expect(prepared.runtimeFiles).toEqual([prepared.cwd!]);
    expect(prepared.command).toEqual(["copilot", "--model", "gpt-4.1", "--add-dir", "/tmp/demo"]);

    const hookFile = join(prepared.cwd!, ".github", "hooks", "chat-deck.json");
    expect(existsSync(hookFile)).toBe(true);
    const hooks = readFileSync(hookFile, "utf8");
    expect(hooks).toContain('"sessionStart"');
    expect(hooks).toContain('"agentStop"');
    expect(hooks).toContain('"/cwd /tmp/demo"');
    expect(hooks).toContain("publish-done");
    expect(hooks).toContain("agent-5");
  });

  test("writes a claude settings file with a Stop hook callback", () => {
    const prepared = prepareWorkerLaunchCommand("claude", "agent-2", "/tmp/demo", ["claude", "--model", "sonnet"]);

    expect(prepared.runtimeFiles).toHaveLength(1);
    expect(existsSync(prepared.runtimeFiles[0]!)).toBe(true);
    expect(prepared.command).toEqual(["claude", "--model", "sonnet", "--settings", prepared.runtimeFiles[0]!]);

    const settings = readFileSync(prepared.runtimeFiles[0]!, "utf8");
    expect(settings).toContain("\"Stop\"");
    expect(settings).toContain("publish-done");
    expect(settings).toContain("agent-2");
  });



  test("finds TASK_DONE content inside nested hook payload strings", () => {
    const event = publishDoneEventFromPayload("copilot", "agent-6", {
      cwd: "/tmp/demo",
      event: {
        output: {
          final:
            'Done. <TASK_DONE>{"display":"Completed the task.\\n\\n- Created the plan","summary":"Completed the task.","result":"Created the plan.","next":"Run the command."}</TASK_DONE>',
        },
      },
    });

    expect(event).not.toBeNull();
    expect(event?.tool).toBe("copilot");
    expect(event?.display).toBe("Completed the task.\n\n- Created the plan");
    expect(event?.summary).toBe("Completed the task.");
    expect(event?.result).toBe("Created the plan.");
    expect(event?.next).toBe("Run the command.");
  });

  test("publishes a task_done inbox event from callback payload", () => {
    const event = publishDoneEventFromPayload("codex", "agent-3", {
      cwd: "/tmp/demo",
      "thread-id": "thread-123",
      "last-assistant-message":
        'Done. <TASK_DONE>{"display":"Finished the review.\\n\\n- Found the root cause","summary":"Finished the review.","result":"Found the root cause.","next":"Apply the patch."}</TASK_DONE>',
    });

    expect(event).not.toBeNull();
    expect(event?.agentId).toBe("agent-3");
    expect(event?.display).toBe("Finished the review.\n\n- Found the root cause");
    expect(event?.summary).toBe("Finished the review.");
    expect(event?.result).toBe("Found the root cause.");
    expect(event?.next).toBe("Apply the patch.");
    expect(event?.sessionId).toBe("thread-123");
  });

  test("reads appended inbox events sequentially", () => {
    const event = publishDoneEventFromPayload("claude", "agent-4", {
      cwd: "/tmp/demo",
      session_id: "session-7",
      last_assistant_message:
        '<TASK_DONE>{"summary":"Completed the task.","result":"Updated the files.","next":"Run the tests."}</TASK_DONE>',
    });

    expect(event).not.toBeNull();

    if (event) {
      const { appendInboxEvent } = require("../src/lib/inbox") as typeof import("../src/lib/inbox");
      appendInboxEvent(event);
    }

    expect(existsSync(inboxFilePath())).toBe(true);
    const firstRead = readInboxEvents(0);
    expect(firstRead.events).toHaveLength(1);
    expect(firstRead.events[0]?.summary).toBe("Completed the task.");

    const secondRead = readInboxEvents(firstRead.nextOffset);
    expect(secondRead.events).toEqual([]);
  });
});
