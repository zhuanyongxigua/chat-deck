import { describe, expect, test } from "bun:test";

import { isTmuxCliReadyCommand } from "../src/lib/tmux";

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
