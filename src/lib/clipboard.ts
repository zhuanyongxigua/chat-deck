import { spawnSync } from "node:child_process";

type CommandRunner = (command: string, args: string[], text: string) => boolean;

interface ClipboardOptions {
  platform?: NodeJS.Platform;
  osc52Copy?: () => boolean;
  runCommand?: CommandRunner;
}

function defaultRunCommand(command: string, args: string[], text: string): boolean {
  const result = spawnSync(command, args, {
    input: text,
    encoding: "utf8",
  });
  return !result.error && result.status === 0;
}

function commandCandidates(platform: NodeJS.Platform): Array<[string, string[]]> {
  if (platform === "darwin") {
    return [["pbcopy", []]];
  }
  if (platform === "win32") {
    return [["clip", []]];
  }
  return [
    ["wl-copy", []],
    ["xclip", ["-selection", "clipboard"]],
    ["xsel", ["--clipboard", "--input"]],
  ];
}

export function copyTextToClipboard(text: string, options: ClipboardOptions = {}): boolean {
  if (!text) {
    return false;
  }

  const platform = options.platform ?? process.platform;
  const runCommand = options.runCommand ?? defaultRunCommand;

  for (const [command, args] of commandCandidates(platform)) {
    try {
      if (runCommand(command, args, text)) {
        return true;
      }
    } catch {
      // Try the next clipboard command candidate.
    }
  }

  return options.osc52Copy?.() ?? false;
}

