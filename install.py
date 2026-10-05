# /// script
# requires-python = ">=3.11"
# ///
"""Manual installer for pastey (the alternative to installing it as a plugin).

Copies the skill into <claude-dir>/skills/pastey and merges the PostToolUse hook into
<claude-dir>/settings.json. Safe to re-run; `uninstall` removes only what it added.

    uv run install.py install [--project DIR | --claude-dir DIR]
    uv run install.py status
    uv run install.py uninstall
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
MATCHER = "Write|Edit|MultiEdit"
MARKER = "pastey_open.py"


class SettingsError(Exception):
    """settings.json cannot be safely read or merged; nothing has been changed."""


def load_settings(path):
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        return {}
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError
        raise SettingsError(f"{path} is not valid JSON ({exc}); fix it and re-run") from exc
    if not isinstance(data, dict):
        raise SettingsError(f"{path} must contain a JSON object")
    return data


def save_settings(path, settings):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(path.name + ".pastey.bak")
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)  # the first backup is the pre-pastey original; never overwritten
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def hook_command(repo_root):
    script = (Path(repo_root) / "scripts" / MARKER).as_posix()
    return f'uv run --no-project "{script}"'


def _ours(hook):
    return isinstance(hook, dict) and MARKER in str(hook.get("command", ""))


def _post_tool_use(settings, create):
    hooks = settings.get("hooks")
    if hooks is None:
        if not create:
            return None
        hooks = settings["hooks"] = {}
    if not isinstance(hooks, dict):
        raise SettingsError('"hooks" in settings.json must be an object')
    entries = hooks.get("PostToolUse")
    if entries is None:
        if not create:
            return None
        entries = hooks["PostToolUse"] = []
    if not isinstance(entries, list):
        raise SettingsError('"hooks.PostToolUse" in settings.json must be a list')
    return entries


def add_hook(settings, command):
    """Ensure exactly one pastey hook with `command`. Returns True if settings changed."""
    entries = _post_tool_use(settings, create=True)
    for entry in entries:
        for hook in entry.get("hooks", []) if isinstance(entry, dict) else []:
            if _ours(hook):
                if hook.get("command") == command:
                    return False
                hook["command"] = command
                return True
    entries.append({"matcher": MATCHER, "hooks": [{"type": "command", "command": command}]})
    return True


def remove_hook(settings):
    """Remove pastey's hook, and any containers that become empty. Returns True if changed."""
    entries = _post_tool_use(settings, create=False)
    if entries is None:
        return False
    changed = False
    for entry in list(entries):
        hooks = entry.get("hooks", []) if isinstance(entry, dict) else []
        kept = [h for h in hooks if not _ours(h)]
        if len(kept) != len(hooks):
            changed = True
            if kept:
                entry["hooks"] = kept
            else:
                entries.remove(entry)
    if changed and not entries:
        del settings["hooks"]["PostToolUse"]
        if not settings["hooks"]:
            del settings["hooks"]
    return changed


def _skill_paths(claude_dir, repo_root):
    return Path(repo_root) / "skills" / "pastey" / "SKILL.md", Path(claude_dir) / "skills" / "pastey"


def install(claude_dir, repo_root=REPO_ROOT):
    claude_dir = Path(claude_dir)
    settings_path = claude_dir / "settings.json"
    settings = load_settings(settings_path)  # fail before touching anything
    add_hook(settings, hook_command(repo_root))  # validates shape too
    lines = []

    src, dst_dir = _skill_paths(claude_dir, repo_root)
    dst = dst_dir / "SKILL.md"
    if dst.exists() and dst.read_bytes() == src.read_bytes():
        lines.append(f"skill: unchanged ({dst})")
    else:
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        lines.append(f"skill: installed ({dst})")

    settings = load_settings(settings_path)
    if add_hook(settings, hook_command(repo_root)):
        save_settings(settings_path, settings)
        lines.append(f"hook: installed ({settings_path})")
    else:
        lines.append(f"hook: unchanged ({settings_path})")
    lines.append("Restart Claude Code for the hook and skill to load.")
    return lines


def uninstall(claude_dir):
    claude_dir = Path(claude_dir)
    settings_path = claude_dir / "settings.json"
    lines = []
    settings = load_settings(settings_path)
    if remove_hook(settings):
        save_settings(settings_path, settings)
        lines.append("hook: removed")
    else:
        lines.append("hook: not installed")
    skill_dir = claude_dir / "skills" / "pastey"
    if (skill_dir / "SKILL.md").exists():
        shutil.rmtree(skill_dir)
        lines.append("skill: removed")
    else:
        lines.append("skill: not installed")
    return lines


def status(claude_dir, repo_root=REPO_ROOT):
    claude_dir = Path(claude_dir)
    settings = load_settings(claude_dir / "settings.json")
    entries = _post_tool_use(settings, create=False) or []
    commands = [
        h["command"] for e in entries if isinstance(e, dict) for h in e.get("hooks", []) if _ours(h)
    ]
    if not commands:
        lines = ["hook: not installed"]
    elif commands == [hook_command(repo_root)]:
        lines = [f"hook: installed ({commands[0]})"]
    else:
        lines = [f"hook: installed, but points elsewhere ({commands[0]}); re-run install"]
    skill = claude_dir / "skills" / "pastey" / "SKILL.md"
    lines.append(f"skill: installed ({skill})" if skill.exists() else "skill: not installed")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install pastey without the plugin system.")
    parser.add_argument("command", choices=["install", "uninstall", "status"])
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--project", metavar="DIR", help="install for one project (DIR/.claude)")
    where.add_argument("--claude-dir", metavar="DIR", help="use this directory instead of ~/.claude")
    args = parser.parse_args(argv)
    if args.claude_dir:
        claude_dir = Path(args.claude_dir)
    elif args.project:
        claude_dir = Path(args.project) / ".claude"
    else:
        claude_dir = Path.home() / ".claude"
    try:
        for line in {"install": install, "uninstall": uninstall, "status": status}[args.command](claude_dir):
            print(line)
    except SettingsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
