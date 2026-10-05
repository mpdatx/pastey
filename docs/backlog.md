---
title: Backlog
summary: Open work. Closed items move to the archive.
order: 90
---

# Backlog

Each item is `## Bnn. Title` followed by one line, then free prose:

    Status: open · Added: YYYY-MM-DD · Spec: superpowers/specs/… · Source: TODO.md

`Status` and `Added` are required. Statuses: open, in-progress, blocked, done, dropped.
Done and dropped items are moved to the [archive](backlog-archive.md) by the pre-commit
hook. IDs are never reused.

## B01. Build the pastey plugin
Status: blocked · Gate: G01 · Spec: superpowers/specs/2026-10-04-pastey-design.md · Added: 2026-10-04

Implement the plugin described in the spec: hook, opener script, skill, layered config.
Done when a spec write and a snippet write each open in VS Code in a real Claude Code
session, and the unit and end-to-end tests pass.
