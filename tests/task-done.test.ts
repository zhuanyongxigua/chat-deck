import { describe, expect, test } from "bun:test";

import { buildTaskDonePrompt, formatTaskDone, parseTaskDone } from "../src/lib/task-done";

describe("task done protocol helpers", () => {
  test("builds a prompt that requires a structured completion block", () => {
    const prompt = buildTaskDonePrompt("What kind of project is this?");

    expect(prompt).toContain("What kind of project is this?");
    expect(prompt).toContain("<TASK_DONE>");
    expect(prompt).toContain('"display"');
    expect(prompt).toContain("escape line breaks inside strings as \\\\n");
    expect(prompt).toContain("same language as the user's message");
    expect(prompt).toContain("make reasonable assumptions and continue autonomously");
  });

  test("parses the last valid TASK_DONE block in a snapshot", () => {
    const parsed = parseTaskDone(`
      interim output
      <TASK_DONE>{"summary":"first","result":"one","next":"next one"}</TASK_DONE>
      more output
      <TASK_DONE>{"summary":"second","result":"two","next":"next two"}</TASK_DONE>
    `);

    expect(parsed).not.toBeNull();
    expect(parsed?.payload).toEqual({
      summary: "second",
      result: "two",
      next: "next two",
    });
  });

  test("returns null for invalid TASK_DONE payloads", () => {
    expect(parseTaskDone(`<TASK_DONE>{not-json}</TASK_DONE>`)).toBeNull();
  });

  test("formats only non-empty sections", () => {
    expect(
      formatTaskDone({
        summary: "Completed the initial review.",
        result: "",
        next: "Run the integration tests next.",
      }),
    ).toBe("Completed the initial review.\n\nRun the integration tests next.");
  });

  test("prefers formatted display content when present", () => {
    expect(
      formatTaskDone({
        display: "Prepared the demo directories:\n\n- /tmp/chat-deck-codex-demo\n- /tmp/chat-deck-claude-demo",
        summary: "ignore",
        result: "ignore",
        next: "ignore",
      }),
    ).toBe("Prepared the demo directories:\n\n- /tmp/chat-deck-codex-demo\n- /tmp/chat-deck-claude-demo");
  });
});
