---
title: Waiting on you
summary: Questions only the user can answer — a look, a listen, an approval, a decision — and their verdicts.
---

# Waiting on you

A gate is a question the work can't settle by itself: an in-person check, a listening
pass, an A/B choice, an approval, a decision. Each is one record; everything else refers
to it by ID rather than restating it. Answered and dropped gates move to the
[archive](gates-archive.md), verdicts and all.

    ## G04. The question, as the user will read it
    Status: waiting · Asked: YYYY-MM-DD · For: B03 · Needs: what must be true to answer it

    Setup: exactly what to look at or run, and how.
    Passes if: what a "yes" looks like.
    Evidence: paths to the build, render, demo or log.

    ### Verdicts

    - YYYY-MM-DD — "the user's words, verbatim" — pass / fail / unclear. Checked: preconditions.

`Status` (waiting, answered, dropped) and `Asked` are required. To retract a verdict, add
a new dated line saying what is withdrawn and set the gate back to `waiting`; never edit
an old verdict.

## G01. Do a spec write and a snippet write each open in VS Code in a real session?
Status: waiting · Asked: 2026-10-04 · For: B01 · Needs: Plugin loaded with `claude --plugin-dir`

Setup: in a scratch project, start `claude --plugin-dir G:\claude\pastey`. Ask Claude to
(1) write a short spec to `docs/superpowers/specs/` and (2) give you an SQL query to
count orders by region.
Passes if: both files open in VS Code without you doing anything; the SQL appears as
`snippets/0001-<meaningful-name>.sql` with syntax highlighting; editing the spec again
does not steal focus.
Evidence: `%TEMP%\pastey\pastey.log` (set `PASTEY_DEBUG=1` to log raw hook payloads).
