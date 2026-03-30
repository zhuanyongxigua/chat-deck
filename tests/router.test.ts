import { describe, expect, test } from "bun:test";

import { parseUserInput } from "../src/lib/router";

describe("parseUserInput", () => {
  test("parses slash commands for agent creation with client args", () => {
    expect(parseUserInput("/new codex worker /tmp/demo --model gpt-5 --profile fast")).toEqual({
      kind: "create_agent",
      tool: "codex",
      name: "worker",
      cwd: "/tmp/demo",
      launchCommand: ["codex", "--model", "gpt-5", "--profile", "fast"],
    });
  });

  test("accepts the legacy explicit client command form", () => {
    expect(parseUserInput("/new claude reviewer /tmp/repo -- claude --dangerously-skip-permissions")).toEqual({
      kind: "create_agent",
      tool: "claude",
      name: "reviewer",
      cwd: "/tmp/repo",
      launchCommand: ["claude", "--dangerously-skip-permissions"],
    });
  });



  test("parses slash commands for copilot agents", () => {
    expect(parseUserInput("/new copilot helper /tmp/demo --model gpt-4.1")).toEqual({
      kind: "create_agent",
      tool: "copilot",
      name: "helper",
      cwd: "/tmp/demo",
      launchCommand: ["copilot", "--model", "gpt-4.1"],
    });
  });

  test("parses direct agent messages", () => {
    expect(parseUserInput("@api-agent summarize the current status")).toEqual({
      kind: "agent_message",
      target: "api-agent",
      message: "summarize the current status",
    });
  });

  test("returns a helpful error for unsupported tools", () => {
    expect(parseUserInput("/new mock demo /tmp/demo")).toEqual({
      kind: "invalid",
      message: "Unsupported client: mock. Use codex, claude, or copilot.",
    });
  });

  test("parses close with optional target", () => {
    expect(parseUserInput("/close @worker-2")).toEqual({
      kind: "close_agent",
      target: "worker-2",
    });
  });
});
