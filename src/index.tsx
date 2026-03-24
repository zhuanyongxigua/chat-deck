import { createCliRenderer } from "@opentui/core";
import { createRoot } from "@opentui/react";

import { ChatDeckApp } from "./app";
import { publishDoneFromArgs } from "./lib/worker-runtime";

const args = process.argv.slice(2);

if (args[0] === "publish-done") {
  process.exit(await publishDoneFromArgs(args.slice(1)));
}

const renderer = await createCliRenderer({
  exitOnCtrlC: false,
  useMouse: true,
  enableMouseMovement: true,
  autoFocus: true,
  onDestroy: () => {
    process.exit(0);
  },
});

createRoot(renderer).render(<ChatDeckApp />);
