---
title: Gates archive
summary: Answered and dropped gates, with their verdicts, oldest first.
---

# Gates archive

## G01. Do a spec write and a snippet write each open in VS Code in a real session?
Status: answered · Asked: 2026-10-04 · For: B01 · Needs: Plugin loaded with `claude --plugin-dir`

Setup: in a scratch project, start `claude --plugin-dir G:\claude\pastey`. Ask Claude to
(1) write a short spec to `docs/superpowers/specs/` and (2) give you an SQL query to
count orders by region.
Passes if: both files open in VS Code without you doing anything; the SQL appears as
`snippets/0001-<meaningful-name>.sql` with syntax highlighting; editing the spec again
does not steal focus.
Evidence: `%TEMP%\pastey\pastey.log` (set `PASTEY_DEBUG=1` to log raw hook payloads).

### Verdicts

- 2026-10-04 — "it worked when i started in manual mode" — pass. Checked: plugin loaded with `claude --plugin-dir`, session started in manual permission mode. An earlier attempt in auto mode never reached the hook: auto mode's safety classifier gave no verdict on the Write calls, so no file was written.
