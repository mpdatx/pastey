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
        # Claude Code sends UTF-8 JSON; send real bytes so a locale-decoded stdin is caught.
        return subprocess.run(
            ["uv", "run", "--no-project", str(SCRIPT)],
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            env=self.env,
            capture_output=True,
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
        self.assertEqual(result.stdout, b"")
        logged = self.wait_for_log()
        self.assertIn("-r", logged)
        self.assertIn("0001-orders-by-region.sql", logged)

    def test_unicode_filename_arrives_intact(self):
        result = self.pipe("snippets/0002-café query.sql")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0002-café query.sql", self.wait_for_log())

    def test_denied_path_does_not_launch_editor(self):
        result = self.pipe("src/app.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        time.sleep(1)
        self.assertFalse(self.stub_log.exists())


if __name__ == "__main__":
    unittest.main()
