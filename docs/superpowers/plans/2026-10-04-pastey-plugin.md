---
title: pastey plugin implementation plan
summary: Build the opener script, hook wiring, snippet skill and docs for the pastey plugin.
status: in-progress
spec: superpowers/specs/2026-10-04-pastey-design.md
---

# pastey plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code plugin that opens allowlisted files Claude writes, and copy/paste snippets saved as numbered project files, in the user's editor automatically.

**Architecture:** A `PostToolUse` hook on `Write|Edit|MultiEdit` runs `scripts/pastey_open.py`, which matches the written path against layered allow/deny globs, applies a per-session open-once rule, and launches the editor CLI. A skill teaches Claude to save pasteable text as `snippets/NNNN-name.<ext>` so the same hook opens it.

**Tech Stack:** Python 3.11+ (stdlib only: `tomllib`, `re`, `json`, `subprocess`, `unittest`), run via `uv`; Claude Code plugin (`hooks/hooks.json`, `skills/`).

**Spec:** `docs/superpowers/specs/2026-10-04-pastey-design.md`

## Global Constraints

- Default editor is `code` (VS Code); the editor is configurable and is invoked as `<editor> <editor_args...> <path>` with `editor_args` defaulting to `["-r"]`.
- Default allow: `docs/**/*.md`, `docs/superpowers/**`, `snippets/**`, `README.md`. Default deny: `docs/site/**`, `docs/roadmap.md`. Deny is checked first; anything not allowed is denied. **HTML is not in the default allow.**
- Config layers, later wins: plugin `config/defaults.toml` ← user (`~/.pastey.toml`, overridable by env `PASTEY_USER_CONFIG`) ← project (`<project>/.pastey.toml`). `editor`/`editor_args` override; `allow`/`deny` lists are **additive** across layers.
- Session record and log live in `%TEMP%\pastey\` (override with env `PASTEY_STATE_DIR`); record file is written atomically; log file is `pastey.log`.
- The opener always exits 0 and prints nothing to stdout; failures are logged, never raised to Claude.
- Open rule: a `Write` that reports `tool_response.type == "create"` always opens; any other write opens only if the file is not yet in this session's record.
- Snippets: `snippets/NNNN-meaningful-name.<ext>` inside the project, 4-digit zero-padded sequence, kept (never overwritten, never temp).
- Python files run with `uv run --no-project` and carry a PEP 723 header with `requires-python = ">=3.11"` (the machine's default `python` is 3.8). Tests run with `uv run --python 3.12 --no-project python -m unittest discover -s tests -v`.
- Commit messages end with the two attribution lines given in the session's system reminder. Docs for each change go in the same commit (pmdocs convention).

## Review Focus

Inputs the spec implies but its feature tests would not exercise; each has a test in the owning task.

1. Project path containing a space, and a unicode filename (`snippets/0001-café query.sql`) → still opens (Task 2).
2. A file outside the project (e.g. `~/.claude/plans/x.md`) → never opens (Task 2).
3. Windows path-case differences (`DOCS/A.md` against `docs/**/*.md`) → matches on Windows (Task 2, `skipUnless nt`).
4. A malformed `.pastey.toml` → ignored with a log line, defaults still apply (Task 1 unit, Task 2 integration).
5. Empty or non-JSON hook stdin, and a non-dict `tool_response` → exit 0, no crash (Task 2).

## File Structure

| File | Responsibility |
|---|---|
| `scripts/pastey_open.py` | The opener: glob matching, config loading, session record, editor launch, hook entry point |
| `config/defaults.toml` | Default editor, allow and deny globs |
| `hooks/hooks.json` | Registers the `PostToolUse` hook |
| `.claude-plugin/plugin.json` | Plugin manifest |
| `skills/pastey/SKILL.md` | Snippet convention for Claude |
| `tests/test_matching.py` | Glob matching and config layering (Task 1) |
| `tests/test_opener.py` | `handle` / `main` behavior (Task 2) |
| `tests/test_e2e.py`, `tests/stub_editor.py` | Piped hook payload through `uv run` with a stub editor; manifest checks (Task 3) |

---

### Task 1: Glob matching and config layering

**Files:**
- Create: `scripts/pastey_open.py`
- Create: `config/defaults.toml`
- Create: `tests/test_matching.py`
- Create: `.gitignore`
- Modify: `docs/pmdocs.toml` (doc-map and coverage)
- Modify: `docs/superpowers/specs/2026-10-04-pastey-design.md` (frontmatter `status: in-progress`)
- Modify: `docs/superpowers/plans/2026-10-04-pastey-plugin.md` (frontmatter `status: in-progress`)
- Modify: `docs/backlog.md` (B01 `Status: in-progress`)
- Modify: `docs/architecture.md`

**Interfaces:**
- Consumes: nothing.
- Produces (in `scripts/pastey_open.py`):
  - `DEFAULTS_PATH: Path` — `config/defaults.toml` next to the scripts directory.
  - `glob_to_regex(glob: str) -> re.Pattern`
  - `matches(rel: str, globs: list[str]) -> bool` — `rel` is a project-relative POSIX path.
  - `load_config(*layer_paths, on_error=None) -> dict` with keys `editor: str`, `editor_args: list[str]`, `allow: list[str]`, `deny: list[str]`. `on_error(path, exc)` is called for an unreadable/malformed layer, which is then skipped.

- [ ] **Step 1: Mark work in progress and ignore caches**

Set `status: in-progress` in the spec and this plan's frontmatter and `Status: in-progress` on B01 in `docs/backlog.md`. Create `.gitignore`:

```
__pycache__/
*.pyc
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_matching.py`:

```python
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pastey_open as po


class GlobTests(unittest.TestCase):
    def test_double_star_dir_glob_matches_any_depth(self):
        self.assertTrue(po.matches("docs/a.md", ["docs/**/*.md"]))
        self.assertTrue(po.matches("docs/x/y/a.md", ["docs/**/*.md"]))

    def test_extension_must_match(self):
        self.assertFalse(po.matches("docs/a.txt", ["docs/**/*.md"]))

    def test_anchored_at_project_root(self):
        self.assertFalse(po.matches("other/docs/a.md", ["docs/**/*.md"]))
        self.assertTrue(po.matches("README.md", ["README.md"]))
        self.assertFalse(po.matches("sub/README.md", ["README.md"]))

    def test_trailing_double_star(self):
        self.assertTrue(po.matches("snippets/0001-a.sql", ["snippets/**"]))
        self.assertTrue(po.matches("snippets/sub/x.sh", ["snippets/**"]))
        self.assertFalse(po.matches("snippets", ["snippets/**"]))

    def test_single_star_does_not_cross_slash(self):
        self.assertFalse(po.matches("docs/a/b.md", ["docs/*.md"]))
        self.assertTrue(po.matches("docs/b.md", ["docs/*.md"]))

    def test_question_mark_matches_one_non_slash_char(self):
        self.assertTrue(po.matches("a1.md", ["a?.md"]))
        self.assertFalse(po.matches("a/.md", ["a?.md"]))

    def test_regex_metacharacters_are_literal(self):
        self.assertTrue(po.matches("a+b.md", ["a+b.md"]))
        self.assertFalse(po.matches("aab.md", ["a+b.md"]))


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def write(self, name, text):
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_defaults_file_policy(self):
        cfg = po.load_config(po.DEFAULTS_PATH)
        self.assertEqual(cfg["editor"], "code")
        self.assertEqual(cfg["editor_args"], ["-r"])
        self.assertIn("docs/**/*.md", cfg["allow"])
        self.assertIn("snippets/**", cfg["allow"])
        self.assertIn("docs/site/**", cfg["deny"])
        self.assertIn("docs/roadmap.md", cfg["deny"])
        self.assertFalse([g for g in cfg["allow"] if "html" in g.lower()])

    def test_later_layer_overrides_scalars_and_extends_lists(self):
        user = self.write("user.toml", 'editor = "cursor"\nallow = ["notes/**"]\n')
        proj = self.write("proj.toml", 'editor_args = ["--reuse-window"]\ndeny = ["notes/private/**"]\n')
        cfg = po.load_config(po.DEFAULTS_PATH, user, proj)
        self.assertEqual(cfg["editor"], "cursor")
        self.assertEqual(cfg["editor_args"], ["--reuse-window"])
        self.assertIn("snippets/**", cfg["allow"])
        self.assertIn("notes/**", cfg["allow"])
        self.assertIn("notes/private/**", cfg["deny"])
        self.assertIn("docs/site/**", cfg["deny"])

    def test_duplicate_globs_are_not_repeated(self):
        user = self.write("user.toml", 'allow = ["snippets/**"]\n')
        cfg = po.load_config(po.DEFAULTS_PATH, user)
        self.assertEqual(cfg["allow"].count("snippets/**"), 1)

    def test_missing_layer_is_ignored(self):
        cfg = po.load_config(po.DEFAULTS_PATH, self.dir / "nope.toml")
        self.assertEqual(cfg["editor"], "code")

    def test_malformed_layer_is_skipped_and_reported(self):
        bad = self.write("bad.toml", "editor = [\n")
        errors = []
        cfg = po.load_config(po.DEFAULTS_PATH, bad, on_error=lambda p, e: errors.append(p))
        self.assertEqual(cfg["editor"], "code")
        self.assertEqual(errors, [bad])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run --python 3.12 --no-project python -m unittest discover -s tests -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'pastey_open'`.

- [ ] **Step 4: Write the defaults and minimal implementation**

Create `config/defaults.toml`:

```toml
# pastey defaults. Override in ~/.pastey.toml or <project>/.pastey.toml.
# allow/deny lists are additive across layers; deny is checked first.
editor = "code"
editor_args = ["-r"]

# Globs are relative to the project root. HTML is deliberately not opened by default.
allow = [
  "docs/**/*.md",
  "docs/superpowers/**",
  "snippets/**",
  "README.md",
]

# Generated files that are rewritten on every build.
deny = [
  "docs/site/**",
  "docs/roadmap.md",
]
```

Create `scripts/pastey_open.py`:

```python
# /// script
# requires-python = ">=3.11"
# ///
"""pastey opener: a PostToolUse hook that opens allowlisted files in the user's editor."""
import os
import re
import tomllib
from pathlib import Path

DEFAULTS_PATH = Path(__file__).resolve().parent.parent / "config" / "defaults.toml"

_RE_FLAGS = re.IGNORECASE if os.name == "nt" else 0


def glob_to_regex(glob):
    """Translate a project-relative glob (`**`, `*`, `?`) into an anchored regex."""
    out = []
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        elif glob[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("".join(out) + r"\Z", _RE_FLAGS)


def matches(rel, globs):
    return any(glob_to_regex(g).match(rel) for g in globs)


def _read_toml(path):
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}


def load_config(*layer_paths, on_error=None):
    """Merge config layers in order. Scalars override; allow/deny lists are additive."""
    cfg = {"editor": "code", "editor_args": ["-r"], "allow": [], "deny": []}
    for path in layer_paths:
        try:
            data = _read_toml(path)
        except (tomllib.TOMLDecodeError, OSError) as exc:
            if on_error:
                on_error(path, exc)
            continue
        for key in ("editor", "editor_args"):
            if key in data:
                cfg[key] = data[key]
        for key in ("allow", "deny"):
            cfg[key] = cfg[key] + [g for g in data.get(key, []) if g not in cfg[key]]
    return cfg
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --python 3.12 --no-project python -m unittest discover -s tests -v`
Expected: PASS, 12 tests.

- [ ] **Step 6: Doc-map and architecture**

Replace the `[[map]]` and `[coverage]` sections of `docs/pmdocs.toml` with:

```toml
[[map]]
paths = ["scripts/pastey_open.py", "config/**", "hooks/**", "skills/**", ".claude-plugin/**"]
pages = ["docs/architecture.md"]

# Tracked files matching `include` (minus `exclude`) should be covered by some [[map]].
[coverage]
include = ["scripts/pastey_open.py", "config/**", "hooks/**", "skills/**", ".claude-plugin/**"]
exclude = []
```

In `docs/architecture.md`, replace the Components section body ("None built yet.") with:

```markdown
### Matching and config (`scripts/pastey_open.py`, `config/defaults.toml`)

`matches(rel, globs)` implements `**`, `*` and `?` globs anchored at the project root
(case-insensitive on Windows). `load_config` merges `config/defaults.toml`, the user
file (`~/.pastey.toml`, or `$PASTEY_USER_CONFIG`) and the project `.pastey.toml`:
`editor` and `editor_args` override, `allow` and `deny` lists are additive. A malformed
layer is skipped and reported through `on_error`.
```

- [ ] **Step 7: Verify docs and commit**

Run: `uv run scripts/pmdocs.py check`
Expected: no errors (warnings about unmapped files are acceptable only if none remain).

```bash
git add -A
git commit -m "feat: glob matching and layered config for the opener"
```

(Add the attribution lines to the message. The pre-commit hook rebuilds and stages the docs site.)

---

### Task 2: The opener (record, launch, handle, main)

**Files:**
- Modify: `scripts/pastey_open.py`
- Create: `tests/test_opener.py`
- Modify: `docs/architecture.md`

**Interfaces:**
- Consumes (from Task 1): `DEFAULTS_PATH`, `matches(rel, globs)`, `load_config(*layers, on_error=None)`.
- Produces:
  - `state_dir(env) -> Path` — `env["PASTEY_STATE_DIR"]` or `<tempdir>/pastey`.
  - `log(state: Path, msg: str) -> None` — appends a timestamped line to `state/pastey.log`; swallows `OSError`.
  - `relative_path(abs_path: Path, root) -> str | None` — POSIX path relative to `root`, `None` if outside.
  - `load_record(state, session_id) -> set[str]` / `save_record(state, session_id, opened: set[str]) -> None` (atomic).
  - `launch(cfg, path, popen=subprocess.Popen) -> None` — raises `FileNotFoundError` if the editor is not on PATH.
  - `handle(payload: dict, env=os.environ, popen=subprocess.Popen) -> bool` — returns whether it opened the file; may raise (e.g. missing editor).
  - `main() -> int` — reads stdin, never raises, returns 0.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_opener.py`:

```python
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pastey_open as po


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.base = base
        self.root = base / "my project"  # a space, on purpose
        self.root.mkdir()
        self.state = base / "state"
        self.user_cfg = base / "user.toml"
        self.user_cfg.write_text(f"editor = {json.dumps(sys.executable)}\n", encoding="utf-8")
        self.env = {
            "CLAUDE_PROJECT_DIR": str(self.root),
            "PASTEY_STATE_DIR": str(self.state),
            "PASTEY_USER_CONFIG": str(self.user_cfg),
        }
        self.calls = []

    def popen(self, argv, **kwargs):
        self.calls.append(argv)

    def project_config(self, text):
        (self.root / ".pastey.toml").write_text(text, encoding="utf-8")

    def payload(self, tool, rel, response=None, session="s1"):
        p = {
            "tool_name": tool,
            "session_id": session,
            "cwd": str(self.root),
            "tool_input": {"file_path": str(self.root / rel)},
        }
        if response is not None:
            p["tool_response"] = response
        return p

    def run_hook(self, tool, rel, response_type=None, session="s1"):
        response = {"type": response_type} if response_type else None
        return po.handle(self.payload(tool, rel, response, session), env=self.env, popen=self.popen)

    def log_text(self):
        f = self.state / "pastey.log"
        return f.read_text(encoding="utf-8") if f.exists() else ""


class OpenPolicyTests(Base):
    def test_new_allowed_doc_opens_in_editor(self):
        self.assertTrue(self.run_hook("Write", "docs/superpowers/specs/x-design.md", "create"))
        self.assertEqual(len(self.calls), 1)
        argv = self.calls[0]
        self.assertEqual(argv[1], "-r")
        self.assertTrue(argv[2].endswith("x-design.md"))

    def test_source_and_generated_files_never_open(self):
        for rel in ("src/app.py", "docs/site/index.html", "docs/roadmap.md", "docs/site/a.md"):
            self.assertFalse(self.run_hook("Write", rel, "create"), rel)
        self.assertEqual(self.calls, [])

    def test_html_is_not_opened_by_default(self):
        self.assertFalse(self.run_hook("Write", "reports/q3.html", "create"))

    def test_html_opens_when_project_opts_in(self):
        self.project_config('allow = ["reports/**/*.html"]\n')
        self.assertTrue(self.run_hook("Write", "reports/q3.html", "create"))

    def test_snippet_with_space_and_unicode_opens(self):
        self.assertTrue(self.run_hook("Write", "snippets/0001-café query.sql", "create"))
        self.assertTrue(self.calls[0][2].endswith("0001-café query.sql"))

    def test_path_outside_project_is_ignored(self):
        self.assertFalse(self.run_hook("Write", "../elsewhere/docs/a.md", "create"))
        self.assertEqual(self.calls, [])

    @unittest.skipUnless(os.name == "nt", "Windows path case")
    def test_windows_path_case_difference_still_matches(self):
        self.assertTrue(self.run_hook("Write", "DOCS/A.md", "create"))


class OpenOnceTests(Base):
    def test_edit_opens_once_per_session(self):
        self.assertTrue(self.run_hook("Edit", "docs/a.md"))
        self.assertFalse(self.run_hook("Edit", "docs/a.md"))
        self.assertEqual(len(self.calls), 1)

    def test_new_session_opens_again(self):
        self.assertTrue(self.run_hook("Edit", "docs/a.md", session="s1"))
        self.assertTrue(self.run_hook("Edit", "docs/a.md", session="s2"))

    def test_write_create_always_opens(self):
        self.assertTrue(self.run_hook("Write", "docs/a.md", "create"))
        self.assertTrue(self.run_hook("Write", "docs/a.md", "create"))

    def test_overwrite_of_opened_file_does_not_reopen(self):
        self.assertTrue(self.run_hook("Write", "docs/a.md", "create"))
        self.assertFalse(self.run_hook("Write", "docs/a.md", "update"))

    def test_non_dict_tool_response_does_not_crash(self):
        payload = self.payload("Write", "docs/a.md", response="ok")
        self.assertTrue(po.handle(payload, env=self.env, popen=self.popen))


class FailureTests(Base):
    def test_malformed_project_config_falls_back_and_logs(self):
        self.project_config("allow = [\n")
        self.assertTrue(self.run_hook("Write", "docs/a.md", "create"))
        self.assertIn("config", self.log_text())

    def test_missing_editor_raises_from_handle(self):
        self.project_config('editor = "no-such-editor-xyz"\n')
        with self.assertRaises(FileNotFoundError):
            self.run_hook("Write", "docs/a.md", "create")

    def run_main(self, stdin_text):
        with mock.patch.dict(os.environ, self.env), mock.patch("sys.stdin", io.StringIO(stdin_text)):
            return po.main()

    def test_main_logs_missing_editor_and_returns_zero(self):
        self.project_config('editor = "no-such-editor-xyz"\n')
        code = self.run_main(json.dumps(self.payload("Write", "docs/a.md", {"type": "create"})))
        self.assertEqual(code, 0)
        self.assertIn("error", self.log_text())

    def test_main_survives_garbage_and_empty_stdin(self):
        self.assertEqual(self.run_main("not json"), 0)
        self.assertEqual(self.run_main(""), 0)

    def test_debug_env_logs_raw_payload(self):
        self.env["PASTEY_DEBUG"] = "1"
        self.run_main(json.dumps(self.payload("Write", "src/app.py")))
        self.assertIn("payload:", self.log_text())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --python 3.12 --no-project python -m unittest tests.test_opener -v`
Expected: ERROR — `AttributeError: module 'pastey_open' has no attribute 'handle'` (and `main`).

- [ ] **Step 3: Write the implementation**

In `scripts/pastey_open.py`, replace the import block at the top with:

```python
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path
```

Then append to the end of the file:

```python
def state_dir(env):
    return Path(env.get("PASTEY_STATE_DIR") or Path(tempfile.gettempdir()) / "pastey")


def log(state, msg):
    try:
        state.mkdir(parents=True, exist_ok=True)
        with open(state / "pastey.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


def relative_path(abs_path, root):
    """POSIX path of abs_path relative to root, or None if it is outside root."""
    try:
        return Path(abs_path).relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return None


def _record_file(state, session_id):
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "nosession")
    return state / f"session-{safe}.json"


def load_record(state, session_id):
    try:
        with open(_record_file(state, session_id), encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, ValueError, TypeError):
        return set()


def save_record(state, session_id, opened):
    state.mkdir(parents=True, exist_ok=True)
    target = _record_file(state, session_id)
    tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(sorted(opened)), encoding="utf-8")
    os.replace(tmp, target)


def launch(cfg, path, popen=subprocess.Popen):
    exe = shutil.which(cfg["editor"])
    if exe is None:
        raise FileNotFoundError(f"editor not found on PATH: {cfg['editor']}")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    popen(
        [exe, *cfg["editor_args"], str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )


def _is_create(payload):
    response = payload.get("tool_response")
    return (
        payload.get("tool_name") == "Write"
        and isinstance(response, dict)
        and response.get("type") == "create"
    )


def handle(payload, env=os.environ, popen=subprocess.Popen):
    """Open the written file if policy allows. Returns True if the editor was launched."""
    file_path = (payload.get("tool_input") or {}).get("file_path")
    if not file_path:
        return False
    root = env.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    state = state_dir(env)
    user_cfg = env.get("PASTEY_USER_CONFIG") or Path.home() / ".pastey.toml"
    cfg = load_config(
        DEFAULTS_PATH,
        user_cfg,
        Path(root) / ".pastey.toml",
        on_error=lambda p, e: log(state, f"config {p} ignored: {e!r}"),
    )
    abs_path = Path(file_path).resolve()
    rel = relative_path(abs_path, root)
    if rel is None or matches(rel, cfg["deny"]) or not matches(rel, cfg["allow"]):
        return False
    session_id = payload.get("session_id", "")
    opened = load_record(state, session_id)
    key = abs_path.as_posix()
    if key in opened and not _is_create(payload):
        return False
    launch(cfg, abs_path, popen)
    opened.add(key)
    save_record(state, session_id, opened)
    return True


def main():
    state = state_dir(os.environ)
    try:
        raw = sys.stdin.read()
        if os.environ.get("PASTEY_DEBUG"):
            log(state, f"payload: {raw}")
        handle(json.loads(raw))
    except Exception as exc:  # the hook must never disturb Claude
        log(state, f"error: {exc!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `uv run --python 3.12 --no-project python -m unittest discover -s tests -v`
Expected: PASS (all Task 1 and Task 2 tests; the Windows-case test runs on this machine).

- [ ] **Step 5: Architecture doc and commit**

Append to the Components section of `docs/architecture.md`:

```markdown
### Opener (`scripts/pastey_open.py`)

`main()` reads the hook JSON on stdin and calls `handle()`, which resolves the written
path against `$CLAUDE_PROJECT_DIR` (else the payload `cwd`), applies deny-then-allow,
consults the per-session record (`%TEMP%\pastey\session-<id>.json`, atomic writes) and
launches `<editor> <editor_args> <path>` detached. A `Write` whose `tool_response.type`
is `create` always opens; other writes open once per session. `main()` always returns 0;
errors go to `%TEMP%\pastey\pastey.log`. Set `PASTEY_DEBUG=1` to log each raw payload.
`PASTEY_STATE_DIR` and `PASTEY_USER_CONFIG` relocate the state directory and user config
(used by the tests).
```

Run: `uv run scripts/pmdocs.py check` (expected: no errors), then:

```bash
git add -A
git commit -m "feat: opener with session record, editor launch and hook entry point"
```

---

### Task 3: Hook wiring, plugin manifest and end-to-end test

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `hooks/hooks.json`
- Create: `tests/stub_editor.py`
- Create: `tests/test_e2e.py`
- Modify: `docs/architecture.md`

**Interfaces:**
- Consumes (from Task 2): `scripts/pastey_open.py` run as a script; env vars `CLAUDE_PROJECT_DIR`, `PASTEY_STATE_DIR`, `PASTEY_USER_CONFIG`; project `.pastey.toml` keys `editor` and `editor_args`.
- Produces: a loadable plugin named `pastey` whose hook runs `uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/pastey_open.py"` on `Write|Edit|MultiEdit`.

- [ ] **Step 1: Write the failing tests and stub**

Create `tests/stub_editor.py`:

```python
"""Stand-in editor: appends its arguments to the file named by $STUB_LOG."""
import os
import sys

with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as f:
    f.write(" ".join(sys.argv[1:]) + "\n")
```

Create `tests/test_e2e.py`:

```python
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "pastey_open.py"
STUB = Path(__file__).resolve().parent / "stub_editor.py"


class ManifestTests(unittest.TestCase):
    def test_plugin_manifest(self):
        data = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "pastey")
        self.assertTrue(data["description"])

    def test_hook_registration(self):
        data = json.loads((REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        entry = data["hooks"]["PostToolUse"][0]
        self.assertEqual(entry["matcher"], "Write|Edit|MultiEdit")
        command = entry["hooks"][0]["command"]
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/pastey_open.py", command)
        self.assertIn("uv run", command)


@unittest.skipUnless(shutil.which("uv"), "uv not installed")
class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.root = base / "proj"
        self.root.mkdir()
        self.stub_log = base / "stub.log"
        (self.root / ".pastey.toml").write_text(
            f"editor = {json.dumps(sys.executable)}\n"
            f"editor_args = [{json.dumps(str(STUB))}, \"-r\"]\n",
            encoding="utf-8",
        )
        self.env = dict(
            os.environ,
            CLAUDE_PROJECT_DIR=str(self.root),
            PASTEY_STATE_DIR=str(base / "state"),
            PASTEY_USER_CONFIG=str(base / "none.toml"),
            STUB_LOG=str(self.stub_log),
        )

    def pipe(self, rel):
        payload = {
            "tool_name": "Write",
            "session_id": "e2e",
            "cwd": str(self.root),
            "tool_input": {"file_path": str(self.root / rel)},
            "tool_response": {"type": "create"},
        }
        return subprocess.run(
            ["uv", "run", "--no-project", str(SCRIPT)],
            input=json.dumps(payload),
            env=self.env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def wait_for_log(self):
        for _ in range(100):
            if self.stub_log.exists() and self.stub_log.read_text(encoding="utf-8").strip():
                return self.stub_log.read_text(encoding="utf-8")
            time.sleep(0.1)
        return ""

    def test_allowed_path_launches_editor(self):
        result = self.pipe("snippets/0001-orders-by-region.sql")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        logged = self.wait_for_log()
        self.assertIn("-r", logged)
        self.assertIn("0001-orders-by-region.sql", logged)

    def test_denied_path_does_not_launch_editor(self):
        result = self.pipe("src/app.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        time.sleep(1)
        self.assertFalse(self.stub_log.exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --python 3.12 --no-project python -m unittest tests.test_e2e -v`
Expected: `ManifestTests` ERROR (`FileNotFoundError` for plugin.json / hooks.json); the end-to-end tests should already pass because the script exists, which confirms the opener works under `uv run` with PEP 723.

- [ ] **Step 3: Write the manifest and hook registration**

Create `.claude-plugin/plugin.json`:

```json
{
  "name": "pastey",
  "description": "Automatically opens generated documents and copy/paste snippets in your editor of choice (VS Code by default).",
  "version": "0.1.0",
  "license": "MIT",
  "keywords": ["editor", "vscode", "documents", "snippets"]
}
```

Create `hooks/hooks.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "uv run --no-project \"${CLAUDE_PLUGIN_ROOT}/scripts/pastey_open.py\"",
            "shell": "bash"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `uv run --python 3.12 --no-project python -m unittest discover -s tests -v`
Expected: PASS (all tests).

- [ ] **Step 5: Architecture doc and commit**

Append to the Components section of `docs/architecture.md`:

```markdown
### Plugin wiring (`.claude-plugin/plugin.json`, `hooks/hooks.json`)

The plugin is named `pastey`. `hooks.json` registers one `PostToolUse` hook on
`Write|Edit|MultiEdit` that runs `uv run --no-project ${CLAUDE_PLUGIN_ROOT}/scripts/pastey_open.py`
under bash. The script's PEP 723 header requires Python 3.11+, which `uv` provides.
```

Run: `uv run scripts/pmdocs.py check` (expected: no errors), then:

```bash
git add -A
git commit -m "feat: register the PostToolUse hook and plugin manifest"
```

---

### Task 4: Snippet skill, docs and the real-session gate

**Files:**
- Create: `skills/pastey/SKILL.md`
- Modify: `docs/architecture.md`, `docs/product.md`, `docs/decisions.md`, `docs/gates.md`, `docs/index.md`, `README.md` (create)

**Interfaces:**
- Consumes: the hook (Task 3) opens any file written under `snippets/` — the skill's only job is to make Claude write snippets there with the right name.
- Produces: the user-facing skill `pastey` and gate `G01`.

- [ ] **Step 1: Write the skill**

Create `skills/pastey/SKILL.md`:

````markdown
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
````

- [ ] **Step 2: Update the docs**

`README.md` (create): what pastey is, install for development (`claude --plugin-dir G:\claude\pastey`), the default allow/deny, `.pastey.toml` example:

```toml
editor = "code"              # any editor CLI on PATH
editor_args = ["-r"]         # reuse the current window
allow = ["reports/**/*.html"]  # additive to the defaults
deny = ["docs/drafts/**"]
```

and the limitation that a tab closed mid-session stays closed until the next session.

`docs/product.md`: replace the Capabilities body with the built behavior (documents and snippets open automatically; configurable editor; layered config) and the Non-goals body with the spec's three non-goals.

`docs/architecture.md`: replace the Overview body with the data flow (Write/Edit → hook → opener → editor; skill → snippet file → same hook), append a "Skill (`skills/pastey/SKILL.md`)" component subsection, and replace the code-pointers table with rows for `scripts/pastey_open.py`, `config/defaults.toml`, `hooks/hooks.json`, `.claude-plugin/plugin.json`, `skills/pastey/SKILL.md` and `tests/`.

`docs/index.md`: update the "current state" sentence to say the plugin is implemented and awaiting real-session verification (G01).

`docs/decisions.md`: append

```markdown
## D05. Config lists are additive across layers

**Context:** The spec said config is "layered" without saying how lists combine.
**Decision:** `editor`/`editor_args` override; `allow` and `deny` accumulate across defaults, user and project.
**Why:** A project opting in to HTML should not have to repeat every default glob.
**Consequences:** A project cannot remove a default allow; it can only deny it.
```

- [ ] **Step 3: Open the gate for the real-session check**

Append to `docs/gates.md` (follow the template's format):

```markdown
## G01. Do a spec write and a snippet write each open in VS Code in a real session?
Status: waiting · Asked: 2026-10-04 · For: B01 · Needs: Plugin loaded with `claude --plugin-dir`

Setup: in a scratch project, start `claude --plugin-dir G:\claude\pastey`. Ask Claude to
(1) write a short spec to `docs/superpowers/specs/` and (2) give you an SQL query to
count orders by region.
Passes if: both files open in VS Code without you doing anything; the SQL appears as
`snippets/0001-<meaningful-name>.sql` with syntax highlighting; editing the spec again
does not steal focus.
Evidence: `%TEMP%\pastey\pastey.log` (set `PASTEY_DEBUG=1` to log raw hook payloads).
```

Set B01 to `Status: blocked · Gate: G01` in `docs/backlog.md`.

- [ ] **Step 4: Verify**

Run: `uv run --python 3.12 --no-project python -m unittest discover -s tests -v` (expected: PASS)
Run: `uv run scripts/pmdocs.py check` (expected: no errors, no warnings)

- [ ] **Step 5: Commit and hand over the gate**

```bash
git add -A
git commit -m "feat: snippet skill, README and docs; open gate G01"
```

Then tell the user G01 is waiting, with the setup line above. The plan is complete when the user records a verdict in G01; if `tool_response.type` turns out to differ in a real payload (visible with `PASTEY_DEBUG=1`), fix `_is_create` in `scripts/pastey_open.py` with a failing test first.
