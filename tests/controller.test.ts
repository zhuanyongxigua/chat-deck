import { describe, expect, test } from "bun:test";

import { interpretControllerMessage } from "../src/lib/controller";

describe("interpretControllerMessage", () => {
  test("detects English create requests", () => {
    expect(interpretControllerMessage("create a codex session named billing-agent in /tmp/billing")).toEqual({
      kind: "create_agent",
      tool: "codex",
      cwd: "/tmp/billing",
      name: "billing-agent",
      message: "create a codex session named billing-agent in /tmp/billing",
    });
  });

  test("detects Chinese create requests", () => {
    expect(interpretControllerMessage("帮我创建一个 claude 会话 在 /tmp/review")).toEqual({
      kind: "create_agent",
      tool: "claude",
      cwd: "/tmp/review",
      name: "review-claude",
      message: "帮我创建一个 claude 会话 在 /tmp/review",
    });
  });

  test("derives a name from the working directory when none is provided", () => {
    expect(interpretControllerMessage("start a codex session in /Users/demo/project-alpha")).toEqual({
      kind: "create_agent",
      tool: "codex",
      cwd: "/Users/demo/project-alpha",
      name: "project-alpha-codex",
      message: "start a codex session in /Users/demo/project-alpha",
    });
  });



  test("detects Copilot create requests", () => {
    expect(interpretControllerMessage("create a copilot session in /tmp/copilot-demo")).toEqual({
      kind: "create_agent",
      tool: "copilot",
      cwd: "/tmp/copilot-demo",
      name: "copilot-demo-copilot",
      message: "create a copilot session in /tmp/copilot-demo",
    });
  });

  test("ignores unrelated controller chat", () => {
    expect(interpretControllerMessage("what sessions are currently active?")).toBeNull();
  });
});
