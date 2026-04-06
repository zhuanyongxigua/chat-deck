import { describe, expect, test } from "bun:test";

import { detectBlockedPrompt } from "../src/lib/agent-prompts";

describe("detectBlockedPrompt", () => {
  test("detects Codex trust confirmation", () => {
    expect(
      detectBlockedPrompt(
        "codex",
        "You are in /private/tmp/demo\n\nDo you trust the contents of this directory?\n\n1. Yes, continue",
      ),
    ).toContain("Codex is waiting");
  });

  test("detects Claude workspace trust confirmation", () => {
    expect(
      detectBlockedPrompt(
        "claude",
        "Do you trust the files in this folder?\nYes, proceed\nNo, exit",
      ),
    ).toContain("Claude is waiting");
  });

  test("detects Copilot folder trust confirmation", () => {
    expect(
      detectBlockedPrompt(
        "copilot",
        "Confirm folder trust\nDo you trust the files in this folder?\nYes, and remember this folder for future sessions",
      ),
    ).toContain("Copilot is waiting");
  });

  test("ignores unrelated output", () => {
    expect(detectBlockedPrompt("claude", "Everything is ready.")).toBeNull();
  });
});
