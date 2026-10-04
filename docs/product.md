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

Nothing is built yet. Intended scope (see the backlog for status):

- Open generated documents (specs, plans, any human-readable artifact file) in the
  user's editor when they are written.
- Surface generated copy/paste text (SQL, command lines, snippets) in the editor as well.
- Respect the user's editor choice, defaulting to VS Code.

## Non-goals

To be settled during design; recorded in [Decisions](decisions.md) as they are made.
