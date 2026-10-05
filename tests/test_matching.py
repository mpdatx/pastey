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
