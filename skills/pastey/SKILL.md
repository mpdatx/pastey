---
name: pastey
description: Use when you produce text the user will copy, paste or run elsewhere — SQL queries, shell or PowerShell commands, JSON/YAML/config blocks, code meant to be pasted into another tool. Saves it as a numbered file in the project's snippets/ folder so it opens automatically in the user's editor.
---

# pastey — snippets that open themselves

A hook opens files you write in the user's editor. It only fires for files, so text that
exists only in chat never reaches the editor. When the user will copy or run text
somewhere else, **write it to a snippet file instead of (or as well as) printing it**.

## When to write a snippet

- SQL queries, shell/PowerShell/cmd command lines, one-off scripts
- Config, JSON, YAML or regexes the user will paste into another tool
- Anything the user would otherwise have to select out of terminal output

Do **not** write a snippet for code that belongs in the project's source, for short
inline mentions (`git status`), or for text the user did not ask to reuse.

## How

1. List `snippets/` (Glob `snippets/*`) and take the highest `NNNN` prefix plus one,
   zero-padded to 4 digits. If the folder is missing, start at `0001`; `Write` creates it.
2. Name it `snippets/NNNN-<what-it-does>.<ext>` — lowercase, hyphenated, meaningful
   (`0003-orders-by-region.sql`, not `query.sql`).
3. Use the extension for the content (`.sql`, `.ps1`, `.sh`, `.cmd`, `.json`, `.yaml`,
   `.regex`, `.txt` if nothing fits) so the editor highlights it.
4. Put only the copyable text in the file. Add a one- or two-line comment header with
   what it does only when the language has comments and the purpose is not obvious.
5. Use `Write` (not a shell redirect) so the hook sees it. Never overwrite an existing
   snippet; the numbered history is kept on purpose.
6. Tell the user in one line which file you wrote. The editor opens it automatically.

## Documents

Specs, plans and other human-readable files under the project's allowlisted locations
(`docs/**/*.md`, `README.md`, `snippets/**`) open automatically when written. You do not
need to do anything extra. The user can change what opens in `.pastey.toml` at the
project root or `~/.pastey.toml`.
