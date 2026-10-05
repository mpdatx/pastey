---
title: Decisions
summary: Why things are the way they are. Records are never rewritten; superseded ones are marked.
order: 30
---

# Decisions

Each record is `## Dnn. Title` followed by **Context**, **Decision**, **Why** and
**Consequences** paragraphs. When a decision is reversed, add `Status: superseded by Dmm`
directly under its heading and write the new record; do not edit the old text. IDs are
never reused.

## D01. Open files with a hook, not skill instructions

**Context:** Output must open automatically; Claude is unreliable at remembering to.
**Decision:** A `PostToolUse` hook on `Write|Edit` opens allowlisted files. Pasteable
text is saved as a snippet file so the same hook opens it.
**Why:** Deterministic for files; one mechanism for both output kinds.
**Consequences:** Only text that becomes a file is opened; Claude must choose to write
snippets.

## D02. Allowlist, and no HTML by default

**Context:** Claude writes many files, and source code must never pop open.
**Decision:** Open only files matching an allow glob (docs markdown, snippets, README,
specs, plans); deny generated files. HTML is not allowed by default (user's call).
**Why:** Predictable, tunable per project.
**Consequences:** Projects wanting HTML opened add it in `.pastey.toml`.

## D03. Snippets are numbered project files

**Context:** Copy/paste text needs a home that supports highlighting and history.
**Decision:** `snippets/NNNN-meaningful-name.<ext>` inside the project, kept.
**Why:** User wants history and the snippets are useful artifacts (user's call).
**Consequences:** `snippets/` grows; projects may gitignore it if they prefer.

## D04. Re-open on edit approximated by a session record

**Context:** The editor CLI cannot report which tabs are open.
**Decision:** Open on create; on edit, open only if not yet opened this session.
**Why:** Avoids stealing focus on every edit.
**Consequences:** A tab closed mid-session stays closed until the next session.

## D05. Config lists are additive across layers

**Context:** The spec said config is "layered" without saying how lists combine.
**Decision:** `editor`/`editor_args` override; `allow` and `deny` accumulate across defaults, user and project.
**Why:** A project opting in to HTML should not have to repeat every default glob.
**Consequences:** A project cannot remove a default allow; it can only deny it.
