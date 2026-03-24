import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { HISTORY_LIMIT, historyFilePath, loadHistory, rememberHistory } from "../src/lib/history";

describe("history storage", () => {
  let tempHome = "";
  const previousHome = process.env.CHAT_DECK_HOME;

  beforeEach(() => {
    tempHome = mkdtempSync(join(tmpdir(), "chat-deck-history-"));
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

  test("returns an empty history when the file is missing", () => {
    expect(loadHistory()).toEqual([]);
  });

  test("persists history under the chat-deck home directory", () => {
    const history = rememberHistory([], " /agents   ");

    expect(history).toEqual([" /agents"]);
    expect(existsSync(historyFilePath())).toBe(true);
    expect(readFileSync(historyFilePath(), "utf8")).toBe(" /agents\n");
  });

  test("deduplicates consecutive entries and enforces the history limit", () => {
    const seeded = Array.from({ length: HISTORY_LIMIT }, (_, index) => `cmd-${index}`);
    const withDuplicate = rememberHistory(seeded, `cmd-${HISTORY_LIMIT - 1}`);
    const withOverflow = rememberHistory(withDuplicate, "cmd-overflow");

    expect(withDuplicate).toEqual(seeded);
    expect(withOverflow).toHaveLength(HISTORY_LIMIT);
    expect(withOverflow.at(0)).toBe("cmd-1");
    expect(withOverflow.at(-1)).toBe("cmd-overflow");
    expect(loadHistory()).toEqual(withOverflow);
  });
});
