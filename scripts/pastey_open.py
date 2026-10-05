# /// script
# requires-python = ">=3.11"
# ///
"""pastey opener: a PostToolUse hook that opens allowlisted files in the user's editor."""
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

DEFAULTS_PATH = Path(__file__).resolve().parent.parent / "config" / "defaults.toml"

_RE_FLAGS = re.IGNORECASE if os.name == "nt" else 0


def glob_to_regex(glob):
    """Translate a project-relative glob (`**`, `*`, `?`) into an anchored regex.

    Backslashes are read as `/` and a leading `./` is dropped; `[abc]` sets are not supported.
    """
    glob = glob.replace("\\", "/")
    while glob.startswith("./"):
        glob = glob[2:]
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


def _is_str_list(value):
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _read_toml(path):
    """Read one config layer. Raises ValueError for undecodable, malformed or mistyped files."""
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        return {}
    data = tomllib.loads(raw.decode("utf-8-sig"))  # utf-8-sig: PowerShell writes a BOM
    if "editor" in data and not isinstance(data["editor"], str):
        raise ValueError("editor must be a string")
    for key in ("editor_args", "allow", "deny"):
        if key in data and not _is_str_list(data[key]):
            raise ValueError(f"{key} must be a list of strings")
    return data


def load_config(*layer_paths, on_error=None):
    """Merge config layers in order. Scalars override; allow/deny lists are additive."""
    cfg = {"editor": "code", "editor_args": ["-r"], "allow": [], "deny": []}
    for path in layer_paths:
        try:
            data = _read_toml(path)
        except (ValueError, OSError) as exc:  # ValueError covers TOML and decode errors
            if on_error:
                on_error(path, exc)
            continue
        for key in ("editor", "editor_args"):
            if key in data:
                cfg[key] = data[key]
        for key in ("allow", "deny"):
            cfg[key] = cfg[key] + [g for g in data.get(key, []) if g not in cfg[key]]
    return cfg


def state_dir(env):
    return Path(env.get("PASTEY_STATE_DIR") or Path(tempfile.gettempdir()) / "pastey")


MAX_LOG_BYTES = 1_000_000
SESSION_TTL_DAYS = 7


def log(state, msg):
    try:
        state.mkdir(parents=True, exist_ok=True)
        log_file = state / "pastey.log"
        if log_file.exists() and log_file.stat().st_size > MAX_LOG_BYTES:
            os.replace(log_file, state / "pastey.log.1")  # keep one previous log
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


def relative_path(abs_path, root):
    """POSIX path of abs_path relative to root, or None if it is outside root.

    The path as written is tried first (so a symlinked folder inside the project still
    counts as inside it); the fully resolved path is the fallback.
    """
    path = Path(os.path.abspath(abs_path))
    for base in (Path(os.path.abspath(root)), Path(root).resolve()):
        try:
            return path.relative_to(base).as_posix()
        except ValueError:
            pass
    try:
        return path.resolve().relative_to(Path(root).resolve()).as_posix()
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
    _prune_old_records(state, keep=target)


def _prune_old_records(state, keep):
    cutoff = time.time() - SESSION_TTL_DAYS * 86400
    for old in state.glob("session-*.json"):
        try:
            if old != keep and old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass


_CMD_UNSAFE = set('&|<>^%"')


def launch(cfg, path, popen=subprocess.Popen):
    exe = shutil.which(cfg["editor"])
    if exe is None:
        raise FileNotFoundError(f"editor not found on PATH: {cfg['editor']}")
    # On Windows `code` is code.cmd, which runs through cmd.exe; Python does not escape
    # its metacharacters, so a crafted filename would execute commands. Refuse those.
    if exe.lower().endswith((".cmd", ".bat")) and _CMD_UNSAFE & set(str(path)):
        raise ValueError(f"refusing to pass {str(path)!r} to a batch-file editor (cmd.exe metacharacters)")
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
    abs_path = Path(file_path)
    if not abs_path.is_absolute():
        abs_path = Path(root) / abs_path
    abs_path = Path(os.path.abspath(abs_path))
    rel = relative_path(abs_path, root)
    if rel is None or matches(rel, cfg["deny"]) or not matches(rel, cfg["allow"]):
        return False
    session_id = payload.get("session_id", "")
    opened = load_record(state, session_id)
    key = os.path.normcase(str(abs_path))
    if key in opened and not _is_create(payload):
        return False
    launch(cfg, abs_path, popen)
    opened.add(key)
    save_record(state, session_id, opened)
    return True


def main():
    state = state_dir(os.environ)
    try:
        raw = sys.stdin.buffer.read().decode("utf-8")  # hook JSON is UTF-8, whatever the locale
        if os.environ.get("PASTEY_DEBUG"):
            log(state, f"payload: {raw}")
        handle(json.loads(raw))
    except Exception as exc:  # the hook must never disturb Claude
        log(state, f"error: {exc!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
