---
title: Product
summary: What it does, for whom, and what it deliberately does not do.
order: 10
---

# Product

## Purpose

Claude Code output that a human needs to read or reuse — specs, plans, reports, SQL
queries, shell commands — scrolls away in the terminal or sits in a file the user has to
go find. pastey makes Claude surface that output in the user's editor of choice (usually
VS Code) automatically, so reading and copy/pasting it is one step. It is for users of
Claude Code who work alongside an editor.

## Capabilities

Built and verified in a real session (G01):

- Opens documents Claude writes (`docs/**/*.md`, specs, plans, `README.md`) in the
  user's editor when they are created, and on first edit per session.
- Has Claude save copy/paste text (SQL, command lines, config) as numbered, highlighted
  files in `snippets/`, which open the same way.
- Editor is configurable (default VS Code); what opens is an allowlist, tunable per
  user and per project in `.pastey.toml`. Generated files and HTML do not open by default.

## Non-goals

- Opening source code or generated files by default.
- Detecting open or closed editor tabs.
- Opening text that never becomes a file, other than through the snippet convention.
