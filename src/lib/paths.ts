import { homedir } from "node:os";
import { join } from "node:path";

export function chatDeckHome(): string {
  return process.env.CHAT_DECK_HOME || homedir();
}

export function chatDeckDir(): string {
  return join(chatDeckHome(), ".chat-deck");
}

export function historyFilePath(): string {
  return join(chatDeckDir(), "command-history.txt");
}

export function runtimeDirPath(): string {
  return join(chatDeckDir(), "runtime");
}

export function agentRuntimeDir(agentId: string): string {
  return join(runtimeDirPath(), agentId);
}

export function inboxFilePath(): string {
  return join(chatDeckDir(), "inbox.jsonl");
}
