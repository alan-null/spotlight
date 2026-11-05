"""Run with python3 -m unittest discover -s tests -p test_navi.py."""

import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("actions", Path(__file__).resolve().parents[1] / "lib/actions.py")
actions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(actions)

CHEAT = "% gpg, security\n; local example\n# Version\ngpg --version\n\n# Export\ngpg --export <key> <key>\n$ key: printf 'hello world\\n'\n"


class NaviTests(unittest.TestCase):
    def test_mapping_scopes_and_stable_ids(self):
        parsed = actions.parse_cheat(CHEAT, "gpg.cheat")
        self.assertEqual(parsed[1]["keywords"], ["gpg", "security"])
        self.assertEqual(parsed[1]["parameters"], {"key": {"source": "printf 'hello world\\n'"}})
        self.assertEqual(len(list(actions.records(parsed, "gpg.cheat", set()))), 2)
        changed = actions.parse_cheat("; added comment\n" + CHEAT, "gpg.cheat")
        self.assertEqual(parsed, changed)
        scoped = actions.parse_cheat(CHEAT + "% other\n# Manual\necho <key>\n", "gpg.cheat")
        self.assertEqual(scoped[-1]["parameters"], {"key": {}})
        self.assertNotEqual(parsed[0]["id"], actions.parse_cheat(CHEAT, "other.cheat")[0]["id"])

    def test_discovery_cache_resolution_and_changed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "nested/gpg.cheat"
            path.parent.mkdir()
            path.write_text(CHEAT)
            env = {"SPOTLIGHT_ACTION_PATH": str(root), "SPOTLIGHT_EXTRA_ACTION_PATH": "",
                   "XDG_CACHE_HOME": directory, "XDG_CONFIG_HOME": directory,
                   "SPOTLIGHT_THEME_DATA": ""}
            with mock.patch.dict(os.environ, env):
                cached = actions.cached_records()
                self.assertIn("gpg --export <key> <key>", cached)
                action = actions.load_actions(path)[1]
                choice = mock.Mock(returncode=0, stdout="hello world\n")
                source = mock.Mock(returncode=0, stdout="hello world\n")
                with mock.patch("subprocess.run", side_effect=[source, choice]) as run:
                    result = actions.resolve(path, action["id"], action["command"], directory)
                self.assertEqual(result, "gpg --export 'hello world' 'hello world'")
                self.assertEqual(run.call_count, 2)
                path.write_text(CHEAT.replace("gpg --export", "gpg --import"))
                self.assertEqual(actions.cached_records(), cached)
                with self.assertRaisesRegex(ValueError, "refresh Commands"):
                    actions.resolve(path, action["id"], action["command"], directory, result)
                self.assertIn("gpg --import", actions.cached_records(refresh=True))

    def test_installer_keeps_original_and_normalizes_github_url(self):
        raw_url = "https://raw.githubusercontent.com/denisidoro/cheats/master/security/gpg.cheat"

        class Response(io.BytesIO):
            def geturl(self):
                return raw_url

        with tempfile.TemporaryDirectory() as directory:
            env = {"XDG_CONFIG_HOME": directory, "XDG_CACHE_HOME": directory,
                   "SPOTLIGHT_ACTION_PATH": str(Path(directory) / "spotlight/actions"),
                   "SPOTLIGHT_EXTRA_ACTION_PATH": ""}
            with mock.patch.dict(os.environ, env):
                cache = actions.cache_path()
                actions.cached_records()
                with mock.patch("urllib.request.urlopen", return_value=Response(CHEAT.encode())) as download:
                    actions.install("https://github.com/denisidoro/cheats/blob/master/security/gpg.cheat")
                download.assert_called_once_with(raw_url, timeout=15)
                self.assertFalse(cache.exists())
                installed = list(actions.config_actions_dir().glob("*.cheat"))
                self.assertEqual(len(installed), 1)
                self.assertEqual(installed[0].read_text(), CHEAT)
                self.assertEqual(len(list(actions.main())), 2)
                with mock.patch("urllib.request.urlopen", return_value=Response(CHEAT.encode())):
                    with self.assertRaisesRegex(ValueError, "duplicate action id"):
                        actions.install(raw_url)
                with mock.patch("urllib.request.urlopen", return_value=Response(b"% x\n# Bad\necho one\necho two")):
                    with self.assertRaisesRegex(ValueError, "multiline"):
                        actions.install("https://example.com/bad.cheat")
                self.assertEqual(len(list(actions.config_actions_dir().glob("*.cheat"))), 1)

    def test_unsupported_syntax_reports_file_and_line(self):
        examples = ["@ common", "```sh", "# Missing", "# Multi\necho one\necho two",
                    "# Invalid name\necho <1value>",
                    '# Quoted\necho "<word>"', "# Escaped\necho \\<word>",
                    "# Options\necho <x>\n$ x: printf x --- --multi",
                    "# Dependency\necho <x>\n$ x: echo <y>",
                    "# Dependency\necho <y>\n$ x: printf x\n$ y: echo $x"]
        for example in examples:
            with self.subTest(example=example), self.assertRaisesRegex(ValueError, r"example.cheat:\d+:"):
                actions.parse_cheat("% test\n" + example, "example.cheat")


if __name__ == "__main__":
    unittest.main()
