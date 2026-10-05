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


@unittest.skipUnless(os.name == "nt", "cmd.exe batch handling")
class CmdShimTests(unittest.TestCase):
    """`code` resolves to code.cmd on Windows, which CreateProcess runs through cmd.exe."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name).resolve()
        shim = self.dir / "ed.cmd"
        shim.write_text("@echo off\r\n", encoding="ascii")
        self.cfg = {"editor": str(shim), "editor_args": ["-r"]}
        self.calls = []

    def popen(self, argv, **kwargs):
        self.calls.append(argv)

    def test_cmd_metacharacters_in_path_are_refused(self):
        for name in ("a&b.sql", "a|b.sql", "a^b.sql", "a%USERNAME%.sql", 'a"b.sql'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                po.launch(self.cfg, self.dir / name, popen=self.popen)
        self.assertEqual(self.calls, [])

    def test_ordinary_path_with_spaces_and_parens_still_launches(self):
        path = self.dir / "Program Files (x86)" / "my proj" / "a.md"
        po.launch(self.cfg, path, popen=self.popen)
        self.assertEqual(len(self.calls), 1)


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
        stdin = io.TextIOWrapper(io.BytesIO(stdin_text.encode("utf-8")), encoding="utf-8")
        with mock.patch.dict(os.environ, self.env), mock.patch("sys.stdin", stdin):
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
