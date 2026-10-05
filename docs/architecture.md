---
title: Architecture
summary: How the pieces fit together, and where each lives in the code.
order: 20
---

# Architecture

## Overview

Not designed yet. The deliverable is a Claude Code skill (instructions Claude follows,
possibly with helper scripts or hooks) that opens output in the user's editor. The
design will be brainstormed and recorded as a spec under `docs/superpowers/specs/`.

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
launches `<editor> <editor_args> <path>` detached. A `Write` whose `tool_response.type`
is `create` always opens; other writes open once per session. `main()` always returns 0;
errors go to `%TEMP%\pastey\pastey.log`. Set `PASTEY_DEBUG=1` to log each raw payload.
`PASTEY_STATE_DIR` and `PASTEY_USER_CONFIG` relocate the state directory and user config
(used by the tests).

### Plugin wiring (`.claude-plugin/plugin.json`, `hooks/hooks.json`)

The plugin is named `pastey`. `hooks.json` registers one `PostToolUse` hook on
`Write|Edit|MultiEdit` that runs `uv run --no-project ${CLAUDE_PLUGIN_ROOT}/scripts/pastey_open.py`
under bash. The script's PEP 723 header requires Python 3.11+, which `uv` provides.

## Code pointers

| Area | Where |
|---|---|
| Skill and helpers | `skills/` (planned) |
