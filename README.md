# pastey

A Claude Code plugin that automatically opens the things Claude produces for you to read
or reuse in your editor (VS Code by default):

- **Documents** — specs, plans and other Markdown Claude writes under `docs/`, plus
  `README.md`, open when written.
- **Snippets** — SQL, command lines and similar copy/paste text. The `pastey` skill has
  Claude save them as `snippets/NNNN-meaningful-name.<ext>` in your project, which opens
  them with syntax highlighting and keeps a numbered history.

## How it works

A `PostToolUse` hook on `Write`, `Edit` and `MultiEdit` runs `scripts/pastey_open.py`. It
checks the written path against allow/deny globs and launches your editor. A newly
created file always opens; a file edited later opens only if it has not been opened yet
this session. Source code never opens unless you allow it.

## Install (development)

Requires [uv](https://docs.astral.sh/uv/) and an editor CLI on PATH (`code` for VS Code).

```
claude --plugin-dir G:\claude\pastey
```

## Configure

Layers, later wins: plugin defaults, then `~/.pastey.toml`, then `<project>/.pastey.toml`.
`editor` and `editor_args` override; `allow` and `deny` lists add to the defaults.

```toml
editor = "code"                # any editor CLI on PATH
editor_args = ["-r"]           # reuse the current window
allow = ["reports/**/*.html"]  # HTML is not opened by default
deny = ["docs/drafts/**"]
```

Defaults: allow `docs/**/*.md`, `docs/superpowers/**`, `snippets/**`, `README.md`; deny
`docs/site/**`, `docs/roadmap.md`. Deny wins over allow.

## Limitations

- The editor CLI cannot report open tabs, so a tab you close mid-session stays closed
  until the next session (or until the file is created again).
- On Windows, a file whose path contains `& | < > ^ % "` is not opened (the `code.cmd`
  launcher runs through `cmd.exe`, so such paths are refused and logged). The skill keeps
  snippet names to `a-z`, digits and hyphens. A project folder with `&` in its name never
  opens files for the same reason.
- Only text that becomes a file is opened; the skill is how chat text gets there.

Failures are logged to `%TEMP%\pastey\pastey.log` and never interrupt Claude. Set
`PASTEY_DEBUG=1` to log each raw hook payload.
