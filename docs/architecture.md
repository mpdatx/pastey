---
title: Architecture
summary: How the pieces fit together, and where each lives in the code.
order: 20
---

# Architecture

## Overview

pastey is a Claude Code plugin with one opening mechanism. When Claude writes a file
(`Write`, `Edit`, `MultiEdit`), a `PostToolUse` hook runs the opener, which checks the
path against allow/deny globs and launches the editor. Pasteable text that would
otherwise exist only in chat reaches the same path through the skill, which has Claude
save it as `snippets/NNNN-name.<ext>`; the hook then opens it like any other file.

```
Claude writes file ──▶ PostToolUse hook ──▶ pastey_open.py ──▶ editor CLI
Claude has copy/paste text ──▶ skill ──▶ writes snippets/NNNN-….ext ──▶ (same hook)
```

Design: [pastey design spec](superpowers/specs/2026-10-04-pastey-design.md).

## Components

### Matching and config (`scripts/pastey_open.py`, `config/defaults.toml`)

`matches(rel, globs)` implements `**`, `*` and `?` globs anchored at the project root
(case-insensitive on Windows). `load_config` merges `config/defaults.toml`, the user
file (`~/.pastey.toml`, or `$PASTEY_USER_CONFIG`) and the project `.pastey.toml`:
`editor` and `editor_args` override, `allow` and `deny` lists are additive. A malformed
layer is skipped and reported through `on_error`.

### Opener (`scripts/pastey_open.py`)

`main()` reads the hook JSON on stdin and calls `handle()`, which resolves the written
path against `$CLAUDE_PROJECT_DIR` (else the payload `cwd`), applies deny-then-allow,
consults the per-session record (`%TEMP%\pastey\session-<id>.json`, atomic writes) and
launches `<editor> <editor_args> <path>` without waiting for it (its stdio is discarded;
it is not otherwise detached from the hook's process). A `Write` whose `tool_response.type`
is `create` always opens; other writes open once per session. `main()` always returns 0;
errors go to `%TEMP%\pastey\pastey.log`. Set `PASTEY_DEBUG=1` to log each raw payload.
`PASTEY_STATE_DIR` and `PASTEY_USER_CONFIG` relocate the state directory and user config
(used by the tests).

Paths and housekeeping:

- A relative `file_path` resolves against the project root, not the hook's working
  directory. A path is matched as written first, so a symlinked `docs/` or `snippets/`
  that points outside the project still counts as inside it; the fully resolved path is
  the fallback. The session-record key is `os.path.normcase`d, so on Windows `DOCS/A.md`
  and `docs/a.md` are one file.
- Session records older than 7 days are deleted whenever a record is saved. `pastey.log`
  is rotated to `pastey.log.1` once it passes 1 MB (one previous log is kept).
- Globs read `\` as `/` and drop a leading `./`; `[abc]` sets are not supported.
- `"shell": "bash"` in `hooks.json` was confirmed working in a real session (G01).

Three Windows-driven safeguards, each found by review and pinned by a test:

- Hook stdin is read as bytes and decoded as UTF-8, not with the locale encoding, so
  non-ASCII paths arrive intact.
- On Windows the editor resolves to `code.cmd`, which runs through `cmd.exe`. If the path
  to open contains any of `& | < > ^ % "`, `launch` refuses (`ValueError`, logged) rather
  than let a crafted filename execute commands.
- Config layers are read as UTF-8 (a BOM is accepted) and type-checked: `editor` must be
  a string and `editor_args`, `allow`, `deny` lists of strings. A layer that fails to
  decode, parse or validate is skipped whole and logged; the other layers still apply.

### Plugin wiring (`.claude-plugin/plugin.json`, `hooks/hooks.json`)

The plugin is named `pastey`. `hooks.json` registers one `PostToolUse` hook on
`Write|Edit|MultiEdit` that runs `uv run --no-project ${CLAUDE_PLUGIN_ROOT}/scripts/pastey_open.py`
under bash. The script's PEP 723 header requires Python 3.11+, which `uv` provides.

### Skill (`skills/pastey/SKILL.md`)

Instructions only, no code. It tells Claude when copy/paste text deserves a snippet file,
how to pick the next 4-digit number from `snippets/`, how to name it
(`NNNN-what-it-does.<ext>`, extension chosen for syntax highlighting), to use `Write` so
the hook sees it, to never overwrite earlier snippets, and to say which file it wrote.
If the write is blocked (e.g. by the permission mode) it must say no file exists and fall
back to printing the text; the hook can only react to writes that happen.

## Code pointers

| Area | Where |
|---|---|
| Opener, glob matching, config loading | `scripts/pastey_open.py` |
| Default editor, allow and deny globs | `config/defaults.toml` |
| Hook registration | `hooks/hooks.json` |
| Plugin manifest | `.claude-plugin/plugin.json` |
| Snippet convention | `skills/pastey/SKILL.md` |
| Tests (unit, end-to-end with a stub editor) | `tests/` |
