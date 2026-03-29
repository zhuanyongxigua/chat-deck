import { execFile, spawnSync } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export interface CommandResult {
  ok: boolean;
  code: number;
  stdout: string;
  stderr: string;
}

export interface PaneState {
  sessionExists: boolean;
  paneDead: boolean;
  exitStatus: number | null;
}

async function runCommand(
  binary: string,
  args: string[],
  options: { cwd?: string; check?: boolean } = {},
): Promise<CommandResult> {
  try {
    const { stdout = "", stderr = "" } = await execFileAsync(binary, args, {
      cwd: options.cwd,
      encoding: "utf8",
    });
    return { ok: true, code: 0, stdout: stdout.toString(), stderr: stderr.toString() };
  } catch (error) {
    const err = error as {
      code?: number | string;
      stdout?: string | Buffer;
      stderr?: string | Buffer;
      message?: string;
    };
    const code = typeof err.code === "number" ? err.code : 1;
    const stdout = err.stdout ? err.stdout.toString() : "";
    const stderr = err.stderr ? err.stderr.toString() : err.message || "";
    if (options.check !== false) {
      throw new Error(stderr || `${binary} ${args.join(" ")} failed`);
    }
    return { ok: false, code, stdout, stderr };
  }
}

function shellEscape(value: string): string {
  return `'${value.replace(/'/g, `'\"'\"'`)}'`;
}

function shellCommand(command: string[]): string {
  return `exec ${command.map(shellEscape).join(" ")}`;
}

export async function commandExists(binary: string): Promise<boolean> {
  const result = await runCommand("which", [binary], { check: false });
  return result.ok;
}

export async function isTmuxAvailable(): Promise<boolean> {
  return commandExists("tmux");
}

export async function detectGitBranch(cwd: string): Promise<string | null> {
  const result = await runCommand("git", ["rev-parse", "--abbrev-ref", "HEAD"], {
    cwd,
    check: false,
  });
  if (!result.ok) {
    return null;
  }
  return result.stdout.trim() || null;
}

export async function createTmuxSession(sessionName: string, cwd: string, command: string[]): Promise<void> {
  await runCommand("tmux", ["new-session", "-d", "-s", sessionName, "-c", cwd, shellCommand(command)]);
  await runCommand("tmux", ["set-window-option", "-t", sessionName, "remain-on-exit", "on"], {
    check: false,
  });
}

export async function destroyTmuxSession(sessionName: string): Promise<void> {
  await runCommand("tmux", ["kill-session", "-t", sessionName], { check: false });
}

export async function tmuxHasSession(sessionName: string): Promise<boolean> {
  const result = await runCommand("tmux", ["has-session", "-t", sessionName], { check: false });
  return result.ok;
}

export async function sendTextToTmux(sessionName: string, text: string): Promise<void> {
  if (text) {
    await runCommand("tmux", ["send-keys", "-t", sessionName, "-l", text]);
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  await runCommand("tmux", ["send-keys", "-t", sessionName, "C-m"]);
}

export async function sendKeysToTmux(sessionName: string, keys: string[]): Promise<void> {
  if (!keys.length) {
    return;
  }
  await runCommand("tmux", ["send-keys", "-t", sessionName, ...keys]);
}

export async function captureTmuxSnapshot(sessionName: string, lines = 180): Promise<string[]> {
  const result = await runCommand(
    "tmux",
    ["capture-pane", "-p", "-J", "-S", `-${Math.max(lines, 1)}`, "-t", sessionName],
    { check: false },
  );
  if (!result.ok) {
    return [];
  }
  return result.stdout.split(/\r?\n/);
}

export async function getTmuxPaneState(sessionName: string): Promise<PaneState> {
  if (!(await tmuxHasSession(sessionName))) {
    return { sessionExists: false, paneDead: false, exitStatus: null };
  }
  const result = await runCommand(
    "tmux",
    ["display-message", "-p", "-t", sessionName, "#{pane_dead} #{pane_dead_status}"],
    { check: false },
  );
  if (!result.ok) {
    return { sessionExists: false, paneDead: false, exitStatus: null };
  }
  const [deadToken, statusToken] = result.stdout.trim().split(/\s+/);
  return {
    sessionExists: true,
    paneDead: deadToken === "1",
    exitStatus: statusToken ? Number.parseInt(statusToken, 10) || 0 : null,
  };
}

export function attachTmuxSession(sessionName: string): CommandResult {
  const child = spawnSync("tmux", ["attach-session", "-t", sessionName], {
    stdio: "inherit",
  });
  return {
    ok: child.status === 0,
    code: child.status ?? 1,
    stdout: "",
    stderr: child.error?.message ?? "",
  };
}
