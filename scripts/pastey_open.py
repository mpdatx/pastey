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
