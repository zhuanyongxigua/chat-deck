# AGENTS.md

## Context Hub

When working with external APIs, SDKs, or tools that may have changed, prefer `chub` before guessing from memory.

- Search available docs: `chub search "<provider or topic>"`
- Fetch the current doc: `chub get <id> --lang py`
- Use `--lang js` when the task is JavaScript or TypeScript instead of Python
- If you only need a specific reference file, use `--file`; use `--full` only when the full doc set is necessary
- If unsure how the CLI works, run: `chub help`

Examples:

```bash
chub search openai
chub get openai/chat --lang py
```

If you discover a useful workaround or caveat while implementing something, save it locally so it appears in future sessions:

```bash
chub annotate <id> "<note>"
```

Useful maintenance commands:

- List local annotations: `chub annotate --list`
- Clear an annotation: `chub annotate <id> --clear`
- Send doc feedback: `chub feedback <id> up`

For this repository, prefer `chub` when implementing or updating integrations with external services such as OpenAI, Claude-related tooling, Codex-related tooling, or other third-party APIs.
