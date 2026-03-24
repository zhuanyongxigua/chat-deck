import { describe, expect, test } from "bun:test";

import { copyTextToClipboard } from "../src/lib/clipboard";

describe("clipboard helper", () => {
  test("uses pbcopy on macOS before falling back to OSC52", () => {
    const calls: Array<{ command: string; args: string[]; text: string }> = [];

    const copied = copyTextToClipboard("hello", {
      platform: "darwin",
      runCommand: (command, args, text) => {
        calls.push({ command, args, text });
        return command === "pbcopy";
      },
      osc52Copy: () => false,
    });

    expect(copied).toBe(true);
    expect(calls).toEqual([{ command: "pbcopy", args: [], text: "hello" }]);
  });

  test("falls back to OSC52 when native clipboard commands fail", () => {
    let osc52Calls = 0;

    const copied = copyTextToClipboard("hello", {
      platform: "linux",
      runCommand: () => false,
      osc52Copy: () => {
        osc52Calls += 1;
        return true;
      },
    });

    expect(copied).toBe(true);
    expect(osc52Calls).toBe(1);
  });
});

