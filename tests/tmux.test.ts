import { describe, expect, test } from "bun:test";

import { isCopilotPromptReadySnapshot, isTmuxCliReadyCommand } from "../src/lib/tmux";

describe("isTmuxCliReadyCommand", () => {
  test("treats shells and bootstrap commands as not ready", () => {
    expect(isTmuxCliReadyCommand("zsh")).toBe(false);
    expect(isTmuxCliReadyCommand("/bin/zsh")).toBe(false);
    expect(isTmuxCliReadyCommand("env")).toBe(false);
    expect(isTmuxCliReadyCommand(null)).toBe(false);
  });

  test("treats real CLI processes as ready", () => {
    expect(isTmuxCliReadyCommand("node")).toBe(true);
    expect(isTmuxCliReadyCommand("codex")).toBe(true);
    expect(isTmuxCliReadyCommand("copilot")).toBe(true);
    expect(isTmuxCliReadyCommand("claude")).toBe(true);
  });
});

describe("isCopilotPromptReadySnapshot", () => {
  test("detects the visible Copilot input prompt", () => {
    expect(
      isCopilotPromptReadySnapshot(
        [
          "● Environment loaded: 1 MCP server, 1 skill",
          "",
          " /tmp/demo         Claude Sonnet 4.6 (medium)",
          "────────────────────────────────────────────────────────────────────────────────",
          "❯  Type @ to mention files, # for issues/PRs, / for commands, or ? for",
          "  shortcuts",
          "────────────────────────────────────────────────────────────────────────────────",
          " shift+tab switch mode · ctrl+q enqueue                                   Remaining reqs.: 99%",
        ].join("\n"),
      ),
    ).toBe(true);
  });

  test("does not treat the Copilot loading screen as ready", () => {
    expect(
      isCopilotPromptReadySnapshot(
        [
          "GitHub Copilot v1.0.18",
          "",
          "◉ Loading environment: 1 skill",
          "",
          " /tmp/demo",
        ].join("\n"),
      ),
    ).toBe(false);
  });
});
