---
title: pastey design
summary: A Claude Code plugin that opens generated documents and copy/paste snippets in the user's editor automatically.
status: draft
created: 2026-10-04
backlog: [B01]
---

# pastey design

## Goal

Anything Claude produces for a human to read or reuse opens in the user's editor of
choice (VS Code by default) without being asked. Two kinds of output:

- **File output** — specs, plans and other human-readable files Claude writes.
- **Pasteable text** — SQL, command lines, config blocks and similar, which today exist
  only in chat.

Success: the user never scrolls the terminal or hunts for a path to read a document or
copy a snippet.

## Approach

One opening mechanism, one convention.

- A Claude Code `PostToolUse` hook on `Write` and `Edit` runs an opener script that
  decides, deterministically, whether to open the written file.
- A skill teaches Claude to save pasteable text as a snippet *file*, so the same hook
  opens it. Claude's only discretionary act is choosing to write a snippet; opening is
  never left to Claude.

Rejected: skill-instructions-only (non-deterministic: Claude forgets or over-opens) and
a VS Code extension watching the filesystem (heavy, VS Code-only).

## Packaging

A Claude Code plugin, so one install enables the skill and hook for every project.

```
.claude-plugin/plugin.json
hooks/hooks.json          PostToolUse, matcher Write|Edit → opener
skills/pastey/SKILL.md    snippet convention
scripts/pastey_open.py    the opener (Python, stdlib only, run with uv)
config/defaults.toml      default editor, allow and deny globs
```

Open item for the plan: confirm the plugin hook format (`hooks/hooks.json`, matcher and
command variables) against current Claude Code documentation before implementing.

## The opener

Reads the hook JSON from stdin (tool name, file path, session id). Always exits 0 and
prints nothing, so it never blocks or clutters Claude.

1. Normalize the path relative to the project root.
2. Match **deny** first, then **allow**. No allow match → exit silently.
3. Consult the session record (a JSON file in the temp dir keyed by session id,
   written atomically).
   - New file created by `Write` → open.
   - Edit or overwrite → open only if the file is not yet in the session record.
4. Launch `<editor> -r <path>` (reuse the current window) and record the path.

The editor CLI cannot report open tabs, so "re-open only if not already open" is
approximated by the session record: a tab the user closes mid-session stays closed until
the next session.

## Configuration

TOML, layered: plugin defaults ← `~/.pastey.toml` (user) ← `.pastey.toml` (project).

- `editor` — any command; default `code`.
- `allow` / `deny` — globs relative to the project root.

Defaults:

- allow: `docs/**/*.md`, `snippets/**`, `README.md`, the specs and plans directories.
- deny: `docs/site/**`, `docs/roadmap.md` (generated, rewritten on every build).
- Everything not allowed is denied, so source code never opens.
- HTML is **not** allowed by default; a project opts in via `.pastey.toml`.

## Snippet convention (the skill)

When Claude produces text the user will copy or run, it saves it with `Write` to
`snippets/NNNN-meaningful-name.<ext>` inside the project:

- `NNNN` is the next number, from the existing files in `snippets/` (history is kept;
  nothing is overwritten).
- The name says what the snippet does (`0003-orders-by-region.sql`).
- The extension matches the content (`.sql`, `.ps1`, `.sh`, `.json`) for syntax
  highlighting.
- Snippets are project artifacts and are kept, not temp files.
- Claude also gives a one-line pointer in chat naming the file.

## Errors

- Editor not on PATH: log one line to `%TEMP%\pastey\pastey.log`; do nothing else.
- Any unexpected exception: logged, exit 0.
- Parallel or subagent writes: each file is its own invocation; the record is written
  atomically; a rare double open is harmless.

## Testing

- Unit tests: glob matching (deny before allow), layered config, open-once logic, with
  the editor launch injected and mocked.
- End-to-end: pipe a sample hook payload into the script with a stub editor command that
  logs its arguments; assert it runs for an allowed path and not for a denied one.
- Manual smoke test in a real Claude Code session: write a spec, write a snippet.

## Non-goals

- Opening source code or generated files by default.
- Detecting open or closed editor tabs.
- Opening text that never becomes a file, other than through the snippet convention.
