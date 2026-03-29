import { describe, expect, test } from "bun:test";

import { looksLikeCodexTranscript } from "../src/lib/codex-ui";

describe("codex transcript detection", () => {
  test("detects the transcript viewer footer", () => {
    expect(
      looksLikeCodexTranscript(`
/ T R A N S C R I P T /
q to quit   esc to edit prev
      `),
    ).toBe(true);
  });

  test("does not flag the normal codex home screen", () => {
    expect(
      looksLikeCodexTranscript(`
>_ OpenAI Codex (v0.116.0)
model: gpt-5.4
directory: ~/Documents/Code/vite
      `),
    ).toBe(false);
  });
});
