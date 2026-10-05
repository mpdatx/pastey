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

## Install

Requires [uv](https://docs.astral.sh/uv/) and an editor CLI on PATH (`code` for VS Code).
The opener needs Python 3.11+; if none is installed, uv downloads one the first time the
hook runs, so that first write can be slow.

Pick **one** of the two ways below. Using both would register the hook twice.

### Try it for one session (plugin)

```
claude --plugin-dir G:\claude\pastey
```

### Install it yourself (no marketplace)

Clone the repo somewhere stable, then run its installer. It copies the skill to
`<claude-dir>/skills/pastey` and merges the hook into `<claude-dir>/settings.json`,
keeping everything already in that file. Re-running is safe, and the first run saves your
original settings as `settings.json.pastey.bak`.

```
uv run install.py install                    # for you, in every project (~/.claude)
uv run install.py install --project C:\work\myproj   # for one project only
uv run install.py status
uv run install.py uninstall                  # removes only what it added
```

Restart Claude Code afterwards. The hook points at the cloned repo, so keep the clone
where it is; if you move it, re-run `install` to update the path. To update pastey, pull
the repo and re-run `install` (it refreshes the skill copy). If your `settings.json` is
not valid JSON the installer stops and changes nothing.

## Using pastey

**Pick a permission mode where writes can happen.** pastey reacts to files Claude writes,
so the write has to go through first. pastey was verified in manual permission mode
(you approve writes), and `accept edits` mode does the same without prompting. In an
auto-mode session a write was blocked once before reaching the hook, because auto mode's
safety classifier gave no verdict on it, so no file existed to open. That is Claude Code's
check, not pastey's. If writes are blocked, switch modes (Shift+Tab) and ask again.

**Documents open on their own.** Ask for a spec, plan or other Markdown under `docs/`, or
edit `README.md`, and it opens in your editor when written. You do nothing.

**Snippets need a nudge only if Claude forgets.** The `pastey` skill has Claude save SQL,
commands and similar text as `snippets/NNNN-name.<ext>` when you ask for something to
copy. If it just prints the text in chat, say "save that as a snippet" and it will.
Snippets are real project files: they are kept, numbered, and may be committed, so
never ask for secrets in them. Add `snippets/` to `.gitignore` if you don't want them in git.

**If nothing opens, check in this order:**
1. Is the editor CLI on PATH? Run `code --version` (or your editor's equivalent).
2. Did the write happen at all? A blocked or declined write never reaches the hook.
3. Does the path match the allow list, and not the deny list? See Configure below.
4. Read `%TEMP%\pastey\pastey.log`. Start Claude with `PASTEY_DEBUG=1` to also log each
   raw hook payload.

## Configure

Layers, later wins: plugin defaults, then `~/.pastey.toml`, then `<project>/.pastey.toml`.
`editor` and `editor_args` override; `allow` and `deny` lists add to the defaults.

```toml
editor = "code"                # any editor CLI on PATH
editor_args = ["-r"]           # reuse the current window
allow = ["reports/**/*.html"]  # HTML is not opened by default
deny = ["docs/drafts/**"]
```

Globs are relative to the project root and support `**` (any depth), `*` (within one
folder) and `?`. `\` is read as `/` and a leading `./` is ignored; `[abc]` sets are not
supported.

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
