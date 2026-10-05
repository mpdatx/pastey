import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import pastey_install as pi


class InstallBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.claude = Path(self.tmp.name) / ".claude"
        self.settings = self.claude / "settings.json"

    def write_settings(self, data):
        self.claude.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(json.dumps(data), encoding="utf-8")

    def read_settings(self):
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def pastey_hooks(self, data=None):
        data = data if data is not None else self.read_settings()
        return [
            h
            for e in data.get("hooks", {}).get("PostToolUse", [])
            for h in e.get("hooks", [])
            if "pastey_open.py" in h.get("command", "")
        ]


class InstallTests(InstallBase):
    def test_fresh_install_adds_hook_and_copies_skill(self):
        pi.install(self.claude, REPO)
        hooks = self.pastey_hooks()
        self.assertEqual(len(hooks), 1)
        self.assertIn((REPO / "scripts" / "pastey_open.py").as_posix(), hooks[0]["command"])
        self.assertTrue(hooks[0]["command"].startswith("uv run --no-project "))
        entry = self.read_settings()["hooks"]["PostToolUse"][0]
        self.assertEqual(entry["matcher"], "Write|Edit|MultiEdit")
        self.assertEqual(
            (self.claude / "skills" / "pastey" / "SKILL.md").read_bytes(),
            (REPO / "skills" / "pastey" / "SKILL.md").read_bytes(),
        )

    def test_existing_settings_and_hooks_are_preserved(self):
        other = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}
        self.write_settings({"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"PostToolUse": [other], "Stop": []}})
        pi.install(self.claude, REPO)
        data = self.read_settings()
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls)"]})
        self.assertEqual(data["hooks"]["Stop"], [])
        self.assertIn(other, data["hooks"]["PostToolUse"])
        self.assertEqual(len(self.pastey_hooks(data)), 1)

    def test_install_is_idempotent(self):
        first = pi.install(self.claude, REPO)
        before = self.settings.read_text(encoding="utf-8")
        second = pi.install(self.claude, REPO)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), before)
        self.assertEqual(len(self.pastey_hooks()), 1)
        self.assertTrue(any("unchanged" in line for line in second))
        self.assertFalse(any("unchanged" in line for line in first))

    def test_moved_repo_updates_the_hook_instead_of_duplicating(self):
        old = {"matcher": "Write|Edit|MultiEdit", "hooks": [
            {"type": "command", "command": 'uv run --no-project "D:/old/pastey/scripts/pastey_open.py"'}]}
        self.write_settings({"hooks": {"PostToolUse": [old]}})
        pi.install(self.claude, REPO)
        hooks = self.pastey_hooks()
        self.assertEqual(len(hooks), 1)
        self.assertNotIn("D:/old", hooks[0]["command"])

    def test_invalid_settings_json_is_left_untouched(self):
        self.claude.mkdir(parents=True)
        self.settings.write_text("{ not json", encoding="utf-8")
        with self.assertRaises(pi.SettingsError):
            pi.install(self.claude, REPO)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{ not json")
        self.assertFalse((self.claude / "skills" / "pastey").exists())

    def test_wrong_shaped_hooks_value_is_rejected(self):
        self.write_settings({"hooks": []})
        with self.assertRaises(pi.SettingsError):
            pi.install(self.claude, REPO)

    def test_settings_with_utf8_bom_are_read(self):
        self.claude.mkdir(parents=True)
        self.settings.write_bytes(b"\xef\xbb\xbf" + json.dumps({"model": "x"}).encode("utf-8"))
        pi.install(self.claude, REPO)
        self.assertEqual(self.read_settings()["model"], "x")

    def test_original_settings_are_backed_once(self):
        self.write_settings({"model": "x"})
        pi.install(self.claude, REPO)
        backup = self.claude / "settings.json.pastey.bak"
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), {"model": "x"})
        pi.uninstall(self.claude)
        pi.install(self.claude, REPO)  # a later change must not overwrite the first backup
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), {"model": "x"})


class UninstallAndStatusTests(InstallBase):
    def test_uninstall_removes_only_pastey(self):
        other = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}
        self.write_settings({"hooks": {"PostToolUse": [other]}})
        pi.install(self.claude, REPO)
        pi.uninstall(self.claude)
        self.assertEqual(self.read_settings(), {"hooks": {"PostToolUse": [other]}})
        self.assertFalse((self.claude / "skills" / "pastey").exists())

    def test_uninstall_cleans_up_empty_containers(self):
        pi.install(self.claude, REPO)
        pi.uninstall(self.claude)
        self.assertEqual(self.read_settings(), {})

    def test_uninstall_when_not_installed_is_a_noop(self):
        lines = pi.uninstall(self.claude)
        self.assertFalse(self.settings.exists())
        self.assertTrue(any("not installed" in line for line in lines))

    def test_uninstall_leaves_a_foreign_skill_folder_alone(self):
        foreign = self.claude / "skills" / "pastey"
        foreign.mkdir(parents=True)
        (foreign / "notes.txt").write_text("mine", encoding="utf-8")
        pi.uninstall(self.claude)
        self.assertTrue((foreign / "notes.txt").exists())

    def test_status_reports_both_halves(self):
        self.assertTrue(any("hook: not installed" in l for l in pi.status(self.claude, REPO)))
        pi.install(self.claude, REPO)
        lines = pi.status(self.claude, REPO)
        self.assertTrue(any("hook: installed" in l for l in lines))
        self.assertTrue(any("skill: installed" in l for l in lines))


@unittest.skipUnless(shutil.which("uv"), "uv not installed")
class CliTests(InstallBase):
    def run_cli(self, *args):
        return subprocess.run(
            ["uv", "run", "--no-project", str(REPO / "scripts" / "pastey_install.py"), *args],
            capture_output=True, text=True, timeout=120,
        )

    def test_install_status_uninstall_round_trip(self):
        result = self.run_cli("install", "--claude-dir", str(self.claude))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.pastey_hooks()), 1)
        status = self.run_cli("status", "--claude-dir", str(self.claude))
        self.assertIn("hook: installed", status.stdout)
        self.assertEqual(self.run_cli("uninstall", "--claude-dir", str(self.claude)).returncode, 0)
        self.assertEqual(self.pastey_hooks(), [])

    def test_bad_settings_exit_nonzero_with_message(self):
        self.claude.mkdir(parents=True)
        self.settings.write_text("{ not json", encoding="utf-8")
        result = self.run_cli("install", "--claude-dir", str(self.claude))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("settings.json", result.stderr)


if __name__ == "__main__":
    unittest.main()
