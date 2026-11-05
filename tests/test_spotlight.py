import json
import importlib.util
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


PALETTE = Path(__file__).resolve().parents[1] / "bin/spotlight"

MOCK = """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
import subprocess

root = Path(os.environ["PALETTE_TEST"])
tool = Path(sys.argv[0]).name
if tool == "fzf" and sys.argv[1:] == ["--version"]:
    with (root / "calls").open("a") as log:
        log.write(json.dumps({"tool": "fzf-version", "args": ["--version"]}) + "\\n")
    print(os.environ["PALETTE_FZF_VERSION"])
    sys.exit(0)
entry = {"tool": tool, "args": sys.argv[1:]}
if tool == "fzf":
    entry["input"] = sys.stdin.read()
with (root / "calls").open("a") as log:
    log.write(json.dumps(entry) + "\\n")
if tool == "fzf":
    step_file = root / "step"
    step = int(step_file.read_text()) if step_file.exists() else 0
    step_file.write_text(str(step + 1))
    response = json.loads((root / "responses").read_text())[step]
    if "preview" in response:
        preview = subprocess.run(["bash", os.environ["PALETTE_LAUNCHER"],
                                  "--preview", response["preview"]],
                                 text=True, capture_output=True)
        with (root / "calls").open("a") as log:
            log.write(json.dumps({"tool": "preview", "output": preview.stdout,
                                  "status": preview.returncode}) + "\\n")
    if "select_contains" in response:
        row = next(line for line in entry["input"].splitlines()
                   if response["select_contains"] in line)
        prefix = "\\n\\n" if "--print-query" in sys.argv else ""
        sys.stdout.write(prefix + row + "\\n")
    else:
        sys.stdout.write(response.get("output", ""))
    sys.stderr.write(response.get("stderr", ""))
    sys.exit(response.get("status", 0))
if os.environ.get("FAIL_PROVIDER") == sys.argv[1]:
    print("tmux provider failed", file=sys.stderr)
    sys.exit(1)
if sys.argv[1] == "display-message":
    print(os.environ["PALETTE_FILES_ROOT"])
    sys.exit(0)
if sys.argv[1] == "display-popup" and os.environ.get("RUN_POPUP_CHILD"):
    sys.exit(subprocess.run(["bash", "-c", sys.argv[-1]], env=os.environ).returncode)
rows = {
    "list-windows": "  work:1 editor\\tmodule:tmux:window:$1:@2\\n",
    "list-sessions": "  work\\tmodule:tmux:session:$1\\n",
    "list-panes": "  work:1.1 shell\\tmodule:tmux:pane:$1:@2.%3\\n",
}
sys.stdout.write(rows.get(sys.argv[1], ""))
"""


class PaletteTests(unittest.TestCase):
    def test_no_version_checks_across_launches_and_popup_handoff(self):
        for popup in (False, True):
            with self.subTest(popup=popup):
                result, calls = self.run_palette(
                    [{"status": 130}, {"status": 130}], launches=2,
                    args=("--popup",) if popup else (), run_popup_child=popup)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(any(call["tool"] == "fzf-version" for call in calls))

    def test_fzf_info_setting_controls_both_pickers(self):
        action = '[[actions]]\nid="pick"\ntitle="Pick value"\ncategory="Test"\ncommand="echo <value>"\n[actions.parameters.value]\nsource="printf chosen"\n'
        for configured, info in ((None, "inline-right"), ("inline", "inline")):
            with self.subTest(configured=configured):
                files = {} if configured is None else {"settings.json": json.dumps({"core": {"fzf_info": configured}})}
                result, calls = self.run_palette(
                    [{"select_contains": "Pick value"}, {"select_contains": "chosen"}],
                    command_rows=action, in_tmux=False, config_files=files)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "echo chosen")
                screens = [call for call in calls if call["tool"] == "fzf"]
                self.assertEqual(len(screens), 2)
                for screen in screens:
                    self.assertIn(f"--info={info}", screen["args"])
                self.assertFalse(any(call["tool"] == "fzf-version" for call in calls))

    def test_unsupported_info_error_updates_setting_for_next_launch(self):
        failure = {"status": 2, "stderr": "invalid info style (expected: default|hidden|inline)"}
        for popup in (False, True):
            with self.subTest(popup=popup):
                options = dict(args=("--popup",) if popup else (), run_popup_child=popup,
                               fzf_version="0.38.0 (debian)")
                result, calls = self.run_palette([failure], **options)
                self.assertEqual(result.returncode, 2)
                self.assertIn("Updated Result count position", result.stderr)
                self.assertIn("Reopen Spotlight", result.stderr)
                self.assertEqual(result.stdout, "")
                result, calls = self.run_palette([failure, {"status": 130}], launches=2, **options)
                self.assertEqual(result.returncode, 0, result.stderr)
                screens = [call for call in calls if call["tool"] == "fzf"]
                self.assertIn("--info=inline-right", screens[0]["args"])
                self.assertIn("--info=inline", screens[1]["args"])
                self.assertEqual(sum(call["tool"] == "fzf-version" for call in calls), 1)

    def test_unrelated_errors_and_unknown_or_new_versions_keep_setting(self):
        for message, version, checks in (("terminal failed", "0.38.0", 0),
                                         ("invalid info style", "unknown", 1),
                                         ("invalid info style", "0.67.0", 1)):
            with self.subTest(message=message, version=version):
                result, calls = self.run_palette(
                    [{"status": 2, "stderr": message}, {"status": 130}],
                    launches=2, fzf_version=version)
                self.assertEqual(result.returncode, 0, result.stderr)
                screens = [call for call in calls if call["tool"] == "fzf"]
                self.assertIn("--info=inline-right", screens[1]["args"])
                self.assertEqual(sum(call["tool"] == "fzf-version" for call in calls), checks)

    def test_info_setting_can_be_changed_in_settings(self):
        result, calls = self.run_palette(
            [{"select_contains": "Result count position"}, {"output": "inline\n"}, {"status": 130}],
            args=("--settings",), in_tmux=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        screens = [call for call in calls if call["tool"] == "fzf"]
        self.assertIn("--info=inline", screens[-1]["args"])

    def test_parameter_picker_unsupported_info_updates_setting(self):
        action = '[[actions]]\nid="pick"\ntitle="Pick value"\ncategory="Test"\ncommand="echo <value>"\n[actions.parameters.value]\nsource="printf chosen"\n'
        responses = [{"select_contains": "Pick value"}, {"status": 2, "stderr": "invalid info style"}]
        result, calls = self.run_palette(responses, in_tmux=False, command_rows=action, fzf_version="0.38.0")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Updated Result count position", result.stderr)
        self.assertEqual(result.stdout, "")
        result, calls = self.run_palette(
            responses + [{"select_contains": "Pick value"}, {"select_contains": "chosen"}],
            launches=2, in_tmux=False, command_rows=action, fzf_version="0.38.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "echo chosen")
        screens = [call for call in calls if call["tool"] == "fzf"]
        self.assertIn("--info=inline", screens[-1]["args"])
        self.assertEqual(sum(call["tool"] == "fzf-version" for call in calls), 1)
        result, calls = self.run_palette(
            [{"select_contains": "Pick value"}, {"status": 130}],
            args=("--popup",), run_popup_child=True, command_rows=action)
        self.assertEqual(result.returncode, 0, result.stderr)
        popup = next(call for call in calls if call["tool"] == "tmux" and call["args"][0] == "display-popup")
        self.assertIn("-EE", popup["args"])

    def test_old_python_reports_runtime_requirement_before_importing_tomllib(self):
        for name in ("actions.py", "spotlight_config.py"):
            with self.subTest(helper=name):
                path = PALETTE.parents[1] / "lib" / name
                result = subprocess.run(
                    [sys.executable, "-c", "import sys, runpy; sys.version_info = (3, 10); runpy.run_path(sys.argv[1])", str(path)],
                    text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 1)
                self.assertIn("requires Python 3.11 or newer", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def history_actions(self):
        return '\n'.join(f'[[actions]]\nid="{name.lower()}"\ntitle="{name}"\ncategory="Test"\ncommand="echo {name.lower()}"' for name in ('Alpha', 'Beta', 'Gamma'))

    def run_palette(self, responses, fail_provider="", args=(), command_rows=None,
                    launches=1, command_rows_after_first=None, prune_config=None,
                    home_config="", extra_files=None, git_repo=False, in_tmux=True,
                    tmux_launches=None, modules=None, config_files=None, run_popup_child=False,
                    record_python=False, action_suffix=".toml", installer_responses=None,
                    fzf_version="0.67.0"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            if record_python:
                wrapper = root / "python3"
                wrapper.write_text('#!/bin/bash\nprintf \'%s\\n\' "$*" >> "$PALETTE_TEST/python-calls"\nexec "$PALETTE_REAL_PYTHON" "$@"\n')
                wrapper.chmod(0o755)
            if installer_responses is not None:
                (root / 'installer-responses').write_text(json.dumps(installer_responses))
                wrapper = root / 'python3'
                wrapper.write_text(f'#!{sys.executable}\n' + '''import json, os, sys
from pathlib import Path
root = Path(os.environ['PALETTE_TEST'])
with (root / 'python-calls').open('a') as log:
    log.write(' '.join(sys.argv[1:]) + '\\n')
if len(sys.argv) > 2 and sys.argv[1].endswith('/actions.py') and sys.argv[2] == 'install':
    with (root / 'calls').open('a') as log:
        log.write(json.dumps({'tool': 'installer', 'args': sys.argv[3:]}) + '\\n')
    path = root / 'installer-responses'
    responses = json.loads(path.read_text())
    response = responses.pop(0)
    path.write_text(json.dumps(responses))
    print(response['message'])
    sys.exit(response.get('status', 0))
os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
''')
                wrapper.chmod(0o755)
            for name in ("fzf", "tmux"):
                executable = root / name
                executable.write_text(MOCK)
                executable.chmod(0o755)
            files_root = root / "files"
            files_root.mkdir()
            home = root / "home"
            home.mkdir()
            for module, files in (modules or {}).items():
                module_root = root / "modules" / module
                module_root.mkdir(parents=True)
                for name, content in files.items():
                    (module_root / name).write_text(content)
            for name, content in (config_files or {}).items():
                path = home / '.config' / 'spotlight' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            if home_config:
                (home / ".tmux.conf").write_text(home_config)
            (files_root / "example.txt").write_text("example\n")
            (files_root / "with space.txt").write_text("example\n")
            for name in (("node_modules", "target", ".cargo") if git_repo else
                         (".git", "node_modules", "target", ".cargo")):
                child_dir = files_root / name
                child_dir.mkdir()
                (child_dir / "hidden.txt").write_text("hidden\n")
            for name, content in (extra_files or {}).items():
                (files_root / name).write_bytes(content)
            if git_repo:
                git_init = ["git", "-C", str(files_root), "init", "-q"]
                if git_repo == "bare":
                    git_init.append("--bare")
                subprocess.run(git_init, check=True, capture_output=True)
            (root / "responses").write_text(
                json.dumps(responses)
                .replace("SPACE_PATH", str(files_root / "with space.txt"))
                .replace("PLACEHOLDER", str(files_root / "example.txt")))
            (root / "calls").touch()
            commands_file = root / f"test{action_suffix}"
            if command_rows is not None:
                commands_file.write_text(command_rows)
            env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}", HOME=str(home),
                       XDG_CONFIG_HOME=str(home / ".config"),
                       XDG_STATE_HOME=str(root / "state"),
                       XDG_CACHE_HOME=str(root / "cache"),
                       TMUX="test", TMUX_PANE="%1", PALETTE_TEST=directory,
                       PALETTE_LAUNCHER=str(PALETTE),
                       PALETTE_REAL_PYTHON=sys.executable,
                       PALETTE_FZF_VERSION=fzf_version,
                       PALETTE_FILES_ROOT=str(files_root),
                       FAIL_PROVIDER=fail_provider)
            if run_popup_child:
                env["RUN_POPUP_CHILD"] = "1"
            env.pop("SPOTLIGHT_MODULE_PATH", None)
            env.pop("SPOTLIGHT_HISTORY_FILE", None)
            env["SPOTLIGHT_EXTRA_MODULE_PATH"] = str(root / "modules")
            if command_rows is not None:
                env["SPOTLIGHT_ACTION_PATH"] = str(commands_file)
            else:
                env["SPOTLIGHT_ACTION_PATH"] = str(root / "missing")
            if prune_config is not None:
                prune_file = root / "prune.conf"
                prune_file.write_text(prune_config)
                env["SPOTLIGHT_PRUNE_FILE"] = str(prune_file)
            for launch in range(launches):
                launch_in_tmux = tmux_launches[launch] if tmux_launches else in_tmux
                if launch_in_tmux:
                    env["TMUX"] = "test"
                else:
                    env.pop("TMUX", None)
                if launch == 1 and command_rows_after_first is not None:
                    commands_file.write_text(command_rows_after_first)
                result = subprocess.run(
                    ["bash", str(PALETTE), *args], env=env, text=True,
                    capture_output=True, timeout=10, cwd=files_root if not launch_in_tmux else None,
                )
            calls = [json.loads(line) for line in
                     (root / "calls").read_text().splitlines()]
            if record_python:
                calls.extend({"tool": "python", "command": line} for line in
                             (root / "python-calls").read_text().splitlines())
            return result, calls

    def test_install_input_cancellation_returns_to_commands(self):
        result, calls = self.run_palette(
            [{"output": "install\n\n  Install\tinstall-actions\n"},
             {"status": 130}, {"status": 130}],
            in_tmux=False, record_python=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        screens = [call for call in calls if call['tool'] == 'fzf']
        prompt = screens[1]
        self.assertEqual(prompt['input'], '')
        for option in ('--disabled', '--no-preview', '--info=hidden', '--header-first', '--query=', '--bind=enter:print-query+abort'):
            self.assertIn(option, prompt['args'])
        self.assertIn('--query=install', screens[2]['args'])
        self.assertFalse(any('actions.py install' in call.get('command', '') for call in calls))
        self.assertFalse(any('actions.py cache --refresh' in call.get('command', '') for call in calls))

    def test_install_result_stays_in_palette_and_refreshes_commands(self):
        for in_tmux in (False, True):
            with self.subTest(in_tmux=in_tmux):
                result, calls = self.run_palette(
                    [{"select_contains": "Install action file"},
                     {"output": "https://example.com/gpg.cheat\n", "status": 130},
                     {"select_contains": "Back to Commands"}, {"status": 130}],
                    in_tmux=in_tmux, record_python=True,
                    installer_responses=[{"message": "Installed 2 actions: /tmp/gpg.cheat"}])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, '')
                installed = [call for call in calls if call['tool'] == 'installer']
                self.assertEqual(installed, [{'tool': 'installer', 'args': ['https://example.com/gpg.cheat']}])
                screens = [call for call in calls if call['tool'] == 'fzf']
                self.assertTrue(any('Installed 2 actions' in arg for arg in screens[2]['args']))
                self.assertTrue(any('actions.py cache --refresh' in call.get('command', '') for call in calls))
                self.assertFalse(any(call['tool'] == 'tmux' and call['args'][0] == 'send-keys' for call in calls))

    def test_install_error_can_edit_url_or_return(self):
        result, calls = self.run_palette(
            [{"select_contains": "Install action file"},
             {"output": "https://example.com/bad.cheat\n", "status": 130},
             {"select_contains": "Edit URL"},
             {"output": "https://example.com/good.cheat\n", "status": 130},
             {"status": 130}, {"status": 130}], in_tmux=False,
            installer_responses=[{"message": "Unsupported Navi syntax", "status": 1},
                                 {"message": "Installed 1 actions: /tmp/good.cheat"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        screens = [call for call in calls if call['tool'] == 'fzf']
        self.assertTrue(any('Unsupported Navi syntax' in arg for arg in screens[2]['args']))
        self.assertTrue(any('\x1b[38;2;255;123;114m' in arg for arg in screens[2]['args']))
        self.assertEqual(screens[2]['input'].splitlines(), ['Back to Commands', 'Edit URL'])
        self.assertIn('--query=https://example.com/bad.cheat', screens[3]['args'])
        self.assertEqual(len([call for call in calls if call['tool'] == 'installer']), 2)

    def test_successful_installer_is_recent_and_opens_fresh_input(self):
        result, calls = self.run_palette(
            [{"select_contains": "Install action file"},
             {"output": "https://example.com/gpg.cheat\n", "status": 130},
             {"select_contains": "Back to Commands"},
             {"select_contains": "recent:0:install-actions", "preview": "recent:0:install-actions"},
             {"status": 130}, {"status": 130}], in_tmux=False,
            installer_responses=[{"message": "Installed 2 actions: /tmp/gpg.cheat"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        screens = [call for call in calls if call['tool'] == 'fzf']
        self.assertIn('↺ Install action file', screens[3]['input'])
        self.assertEqual(screens[3]['input'].count('Install action file'), 1)
        self.assertIn('--query=', screens[4]['args'])
        self.assertEqual(len([call for call in calls if call['tool'] == 'installer']), 1)
        self.assertTrue(any('Download an HTTPS' in call.get('output', '') for call in calls if call['tool'] == 'preview'))

    def test_failed_install_is_not_recent(self):
        result, calls = self.run_palette(
            [{"select_contains": "Install action file"},
             {"output": "https://example.com/bad.cheat\n", "status": 130},
             {"select_contains": "Back to Commands"}, {"status": 130}], in_tmux=False,
            installer_responses=[{"message": "Duplicate action", "status": 1}])
        self.assertEqual(result.returncode, 0, result.stderr)
        screens = [call for call in calls if call['tool'] == 'fzf']
        self.assertNotIn('recent:', screens[3]['input'])

    def test_theme_change_stays_in_settings_and_persists_across_launches(self):
        result, calls = self.run_palette(
            [{"select_contains": "Theme"}, {"select_contains": "terminal"},
             {"status": 130}, {"status": 130}], args=("--settings",),
            in_tmux=False, launches=2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        screens = [c for c in calls if c["tool"] == "fzf"]
        self.assertIn("default", screens[0]["input"])
        for screen in screens[2:]:
            self.assertIn("terminal", screen["input"])
            self.assertTrue(any("bg:-1" in arg for arg in screen["args"]))
            self.assertTrue(any("\x1b[48;5;2m" in arg for arg in screen["args"]))

    def test_settings_cancel_preserves_theme(self):
        result, calls = self.run_palette(
            [{"select_contains": "Theme", "preview": "setting:core:theme"},
             {"status": 130}, {"status": 130}], args=("--settings",), in_tmux=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        screens = [c for c in calls if c["tool"] == "fzf"]
        self.assertIn("default", screens[-1]["input"])
        preview = next(c for c in calls if c["tool"] == "preview")
        self.assertIn("APPEARANCE", preview["output"])
        self.assertEqual(preview["status"], 0)

    def test_recent_commands_persist_in_mru_order_without_duplicates(self):
        result, calls = self.run_palette(
            [{"select_contains": "Beta"}, {"select_contains": "Alpha"}, {"status": 130}],
            launches=3, in_tmux=False, command_rows=self.history_actions())
        self.assertEqual(result.returncode, 0, result.stderr)
        screens = [c for c in calls if c["tool"] == "fzf"]
        ids = [row.split('\t')[1] for row in screens[-1]["input"].splitlines()]
        self.assertEqual(ids[:2], ['recent:0:snippet:alpha', 'recent:1:snippet:beta'])
        self.assertNotIn('snippet:alpha', ids)
        self.assertNotIn('snippet:beta', ids)
        self.assertNotIn('--no-sort', screens[-1]['args'])
        self.assertNotIn('--no-sort', screens[0]['args'])

    @unittest.skipUnless(shutil.which('fzf'), 'real fzf is unavailable')
    def test_better_fuzzy_match_precedes_recent_command(self):
        actions = '[[actions]]\nid="recent"\ntitle="Long Alpha command"\ncategory="Test"\ncommand="echo recent"\n[[actions]]\nid="exact"\ntitle="Alpha"\ncategory="Test"\ncommand="echo exact"\n'
        result, calls = self.run_palette(
            [{"select_contains": 'Long Alpha command'}, {"status": 130}],
            launches=2, in_tmux=False, command_rows=actions)
        self.assertEqual(result.returncode, 0, result.stderr)
        screen = [c for c in calls if c['tool'] == 'fzf'][-1]
        matches = subprocess.run([shutil.which('fzf'), '--ansi', '--delimiter=\t', '--nth=1',
                                  '--with-nth=1', '--filter=Alpha'],
                                 input=screen['input'], text=True, capture_output=True, check=True).stdout.splitlines()
        self.assertIn('Long Alpha command', matches[1])
        self.assertTrue(matches[0].strip().startswith('Alpha '))
        unfiltered = subprocess.run([shutil.which('fzf'), '--ansi', '--delimiter=\t', '--nth=1',
                                     '--with-nth=1', '--filter='],
                                    input=screen['input'], text=True, capture_output=True, check=True).stdout.splitlines()
        self.assertIn('Long Alpha command', unfiltered[0])

    def test_history_limit_and_disable_setting(self):
        for limit in (0, 2):
            with self.subTest(limit=limit):
                result, calls = self.run_palette(
                    [{"select_contains": name} for name in ('Alpha', 'Beta', 'Gamma')] + [{"status": 130}],
                    launches=4, in_tmux=False, command_rows=self.history_actions(),
                    config_files={'settings.json': json.dumps({'core': {'history_limit': str(limit)}})})
                self.assertEqual(result.returncode, 0, result.stderr)
                screen = [c for c in calls if c['tool'] == 'fzf'][-1]
                ids = [row.split('\t')[1] for row in screen['input'].splitlines()]
                self.assertEqual([i for i in ids if i.startswith('recent:')],
                                 ['recent:0:snippet:gamma', 'recent:1:snippet:beta'] if limit else [])
                self.assertNotIn('--no-sort', screen['args'])

    def test_history_matches_literal_ids_and_preserves_unicode_and_percent(self):
        for identifier in ('prefix', 'literal.[x]*', 'unicode.żółw'):
            with self.subTest(identifier=identifier):
                actions = f'[[actions]]\nid="{identifier}.longer"\ntitle="Other"\ncategory="Test"\ndescription="snippet:{identifier}"\ncommand="echo other"\n[[actions]]\nid="{identifier}"\ntitle="Selected Żółw"\ncategory="Test"\ncommand="echo 100%09 żółw"\n'
                result, calls = self.run_palette(
                    [{"select_contains": 'Selected Żółw'}, {"select_contains": 'Selected Żółw'}],
                    launches=2, in_tmux=False, command_rows=actions)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, 'echo 100%09 żółw')
                screen = [c for c in calls if c['tool'] == 'fzf'][-1]
                self.assertIn(f'\trecent:0:snippet:{identifier}\t', screen['input'])

    def test_recent_module_commands_dispatch_again(self):
        result, calls = self.run_palette(
            [{"select_contains": 'New window'}, {"select_contains": 'New window'}], launches=2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len([c for c in calls if c['tool'] == 'tmux' and c['args'][0] == 'new-window']), 2)
        self.assertIn('recent:0:module:tmux:new-window', [c for c in calls if c['tool'] == 'fzf'][-1]['input'])

    def test_history_preserves_raw_module_row_titles(self):
        modules = {'raw': {'module.sh': '''
spotlight_raw_commands() { printf 'Raw command\\tmodule:raw:go\\n'; }
spotlight_raw_select() { spotlight_insert 'echo raw'; }
'''}}
        result, calls = self.run_palette(
            [{"select_contains": 'Raw command'}, {"select_contains": 'Raw command'}],
            launches=2, in_tmux=False, modules=modules)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'echo raw')
        self.assertTrue([c for c in calls if c['tool'] == 'fzf'][-1]['input'].startswith('↺ Raw command\t'))

    def test_parameterized_history_reuses_values_and_keeps_template(self):
        actions = '[[actions]]\nid="parameter"\ntitle="Parameterized"\ncategory="Test"\ncommand="echo <value>"\n[actions.parameters.value]\nsource="printf chosen"\n'
        result, calls = self.run_palette(
            [{"select_contains": 'Parameterized'}, {"select_contains": 'chosen'},
             {"select_contains": 'Parameterized', 'preview': 'recent:0:snippet:parameter'}],
            launches=2, in_tmux=False, command_rows=actions)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'echo chosen')
        screens = [c for c in calls if c['tool'] == 'fzf']
        self.assertEqual(len(screens), 3)  # No second parameter picker.
        self.assertIn('recent:0:snippet:parameter', screens[-1]['input'])
        self.assertIn('\tsnippet:parameter\t', screens[-1]['input'])
        preview = next(c for c in calls if c['tool'] == 'preview')
        self.assertEqual(preview['status'], 0)

    def test_history_hides_unavailable_modules_and_tracks_success_only(self):
        result, calls = self.run_palette(
            [{"select_contains": 'New window'}, {"status": 130}], launches=2,
            tmux_launches=(True, False))
        self.assertEqual(result.returncode, 0, result.stderr)
        screen = [c for c in calls if c['tool'] == 'fzf'][-1]
        self.assertNotIn('recent:', screen['input'])
        self.assertNotIn('--no-sort', screen['args'])
        result, calls = self.run_palette(
            [{"select_contains": 'New window'}, {"status": 130}], launches=2, fail_provider='new-window')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('recent:', [c for c in calls if c['tool'] == 'fzf'][-1]['input'])

    def test_history_definition_changes_require_refresh(self):
        changed = self.history_actions().replace('echo alpha', 'echo changed')
        result, _ = self.run_palette(
            [{"select_contains": 'Alpha'}, {"select_contains": 'Alpha'}], launches=2,
            in_tmux=False, command_rows=self.history_actions(), command_rows_after_first=changed)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Action changed', result.stderr)
        result, calls = self.run_palette(
            [{"select_contains": 'Alpha'}, {"output": '\nctrl-r\n'}, {"select_contains": 'Alpha'}],
            launches=2, in_tmux=False, command_rows=self.history_actions(), command_rows_after_first=changed)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'echo changed')
        self.assertNotIn('recent:', [c for c in calls if c['tool'] == 'fzf'][-1]['input'])

    def test_history_count_can_be_changed_in_settings(self):
        result, calls = self.run_palette(
            [{"select_contains": 'Recent command count'}, {"select_contains": '10'}, {"status": 130}],
            args=('--settings',), in_tmux=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        screen = [c for c in calls if c['tool'] == 'fzf'][-1]
        row = next(r for r in screen['input'].splitlines() if 'Recent command count' in r)
        self.assertIn('10', row)

    def test_history_can_be_cleared_from_settings(self):
        result, calls = self.run_palette(
            [{"select_contains": 'Alpha'}, {"output": '\nright\n'}, {"output": '\nright\n'},
             {"select_contains": 'Clear recent commands'}, {"output": '\nleft\n'},
             {"output": '\nleft\n'}, {"status": 130}], launches=2,
            in_tmux=False, command_rows=self.history_actions())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('recent:', [c for c in calls if c['tool'] == 'fzf'][-1]['input'])

    def test_settings_picker_failure_is_reported(self):
        result, _ = self.run_palette(
            [{"select_contains": "Theme"}, {"status": 2}], args=("--settings",), in_tmux=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Settings picker failed", result.stderr)

    def test_module_settings_persist_preview_and_return_to_settings(self):
        modules = {"demo": {"module.sh": r'''
spotlight_demo_settings() {
  local value
  value=$(spotlight_setting_get demo mode off) || return
  spotlight_module_setting demo mode 'Demo mode' "$value" 'Choose demo mode'
}
spotlight_demo_setting_preview() { printf 'Demo mode preference'; }
spotlight_demo_setting_select() {
  [[ $1 == mode ]] || return 1
  spotlight_setting_set demo mode on
}
'''}}
        result, calls = self.run_palette(
            [{"select_contains": "Demo mode", "preview": "setting:demo:mode"},
             {"status": 130}, {"status": 130}], args=("--settings",),
            in_tmux=False, launches=2, modules=modules)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        screens = [c for c in calls if c["tool"] == "fzf"]
        self.assertIn("off", screens[0]["input"])
        self.assertIn("on", screens[1]["input"])
        self.assertIn("on", screens[2]["input"])
        preview = next(c for c in calls if c["tool"] == "preview")
        self.assertEqual(preview["output"], "Demo mode preference")

    def test_user_theme_styles_main_and_parameter_picker(self):
        action = '''[[actions]]
id = "test.theme"
title = "Pick value"
category = "Demo"
command = "echo <value>"
[actions.parameters.value]
source = "printf 'hello\\n'"
'''
        result, calls = self.run_palette(
            [{"select_contains": "Pick value"}, {"select_contains": "hello"}],
            in_tmux=False, command_rows=action, config_files={
                "settings.json": '{"core":{"theme":"custom"}}',
                "themes/custom.toml": '[colors]\naccent = "#123456"\nhint = "9"\n[categories]\nDemo = "10"\nDEMO = "10"\n'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "echo hello")
        screens = [c for c in calls if c["tool"] == "fzf"]
        self.assertEqual(len(screens), 2)
        for screen in screens:
            self.assertTrue(any("hl:#123456" in a for a in screen["args"]))
            self.assertTrue(any("\x1b[48;2;18;52;86m" in a for a in screen["args"]))
            self.assertIn("\x1b[38;5;9m", screen["input"])
        self.assertIn("\x1b[38;5;10m", screens[0]["input"])

    def test_invalid_theme_fails_before_launching_fzf(self):
        for theme in ('[colors]\naccent = "oops"', '[colors]\nunknown = "1"'):
            result, calls = self.run_palette([], config_files={
                "settings.json": '{"core":{"theme":"broken"}}',
                "themes/broken.toml": theme})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Spotlight configuration:", result.stderr)
            self.assertFalse(any(c["tool"] == "fzf" for c in calls))

    def test_popup_frame_uses_selected_theme(self):
        result, calls = self.run_palette([], args=("--popup", "--files"), config_files={
            "settings.json": '{"core":{"theme":"terminal"}}'})
        self.assertEqual(result.returncode, 0, result.stderr)
        popup = next(c for c in calls if c["tool"] == "tmux")
        self.assertEqual(popup["args"][0], "display-popup")
        self.assertIn("bg=default,fg=colour7", popup["args"])
        self.assertIn("fg=colour2", popup["args"])
        self.assertIn("--files", popup["args"][-1])

    def test_popup_child_reuses_theme_and_preserves_module_action_cache(self):
        for modules in (None, self.demo_module()):
            with self.subTest(module_actions=bool(modules)):
                result, calls = self.run_palette(
                    [{"status": 130}], args=("--popup",), run_popup_child=True,
                    git_repo=True, modules=modules, record_python=True,
                    config_files={"settings.json": '{"core":{"theme":"terminal"}}'})
                self.assertEqual(result.returncode, 0, result.stderr)
                popup = next(c for c in calls if c["tool"] == "tmux" and c["args"][0] == "display-popup")
                self.assertIn("--popup-child", popup["args"][-1])
                screen = next(c for c in calls if c["tool"] == "fzf")
                self.assertIn("--color=bg:-1", next(a for a in screen["args"] if a.startswith("--color=")))
                self.assertEqual("Module TOML action" in screen["input"], bool(modules))
                bootstraps = [c for c in calls if c["tool"] == "python" and 'spotlight_config.py shell' in c["command"]]
                self.assertEqual(len(bootstraps), 1)

    def test_warm_commands_launch_does_not_start_action_cache_python(self):
        result, calls = self.run_palette(
            [{"status": 130}, {"status": 130}], launches=2,
            in_tmux=False, record_python=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        cache_calls = [c for c in calls if c["tool"] == "python" and 'actions.py cache' in c["command"]]
        bootstraps = [c for c in calls if c["tool"] == "python" and 'spotlight_config.py shell' in c["command"]]
        self.assertEqual(len(cache_calls), 1)
        self.assertEqual(len(bootstraps), 2)

    def test_files_launch_defers_action_cache_metadata(self):
        result, calls = self.run_palette(
            [{"status": 130}], args=("--files",), in_tmux=False, record_python=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        python_calls = [c["command"] for c in calls if c["tool"] == "python"]
        self.assertFalse(any('actions.py cache' in c or '--action-cache' in c for c in python_calls))

    def demo_module(self):
        return {"demo": {"module.sh": '''
spotlight_demo_available() {
  printf '{"tool":"module-context"}\\n' >> "$PALETTE_TEST/calls"
  spotlight_in_git_repo
}
spotlight_demo_tabs() {
  local n
  for n in 1 2 3 4 5; do spotlight_module_tab demo "tab$n" "Extra $n"; done
}
spotlight_demo_commands() {
  spotlight_module_row demo hello 'Module command' Demo 'Insert greeting'
}
spotlight_demo_list() {
  printf '{"tool":"module-list","tab":"%s"}\\n' "$1" >> "$PALETTE_TEST/calls"
  printf '  Module item %s\\tmodule:demo:%s\\n' "$1" "$1"
}
spotlight_demo_preview() { printf 'Module preview: %s\\n' "$1"; }
spotlight_demo_select() { spotlight_insert "echo $1"; }
''', "actions.toml": '[[actions]]\nid = "demo.action"\ntitle = "Module TOML action"\ncategory = "Demo"\ncommand = "echo toml"\n'}}

    def test_module_context_controls_tabs_commands_and_toml_actions(self):
        for git_repo, in_tmux in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(git_repo=git_repo, in_tmux=in_tmux):
                result, calls = self.run_palette(
                    [{"status": 130}], in_tmux=in_tmux, git_repo=git_repo,
                    modules=self.demo_module())
                self.assertEqual(result.returncode, 0, result.stderr)
                screen = next(c for c in calls if c["tool"] == "fzf")
                self.assertEqual("Module command" in screen["input"], git_repo)
                self.assertEqual("Module TOML action" in screen["input"], git_repo)
                self.assertEqual(any("Extra 1" in a for a in screen["args"]), git_repo)
                self.assertNotIn("Module item", screen["input"])
                self.assertFalse(any(c["tool"] == "module-list" for c in calls))

    def test_module_tabs_route_preview_select_and_dynamic_state(self):
        result, calls = self.run_palette(
            [{"output": "query\nright\n"}] +
            [{"output": "\nright\n"}] * 4 +
            [{"select_contains": "Module item tab5", "preview": "module:demo:tab5"}],
            in_tmux=False, git_repo=True, modules=self.demo_module())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "echo tab5")
        preview = next(c for c in calls if c["tool"] == "preview")
        self.assertEqual(preview, {"tool": "preview", "output": "Module preview: tab5\n", "status": 0})
        self.assertEqual(len([c for c in calls if c["tool"] == "module-context"]), 2)

    def test_module_tab_rows_are_cached_and_refresh_preserves_query(self):
        result, calls = self.run_palette(
            [{"output": "\nright\n"}, {"output": "branch\nleft\n"},
             {"output": "\nright\n"}, {"output": "branch\nctrl-r\n"},
             {"status": 130}], in_tmux=False, git_repo=True,
            modules=self.demo_module())
        self.assertEqual(result.returncode, 0, result.stderr)
        listings = [c for c in calls if c["tool"] == "module-list"]
        self.assertEqual([c["tab"] for c in listings], ["tab1", "tab1"])
        screens = [c for c in calls if c["tool"] == "fzf"]
        self.assertIn("--query=branch", screens[3]["args"])
        self.assertIn("--query=branch", screens[4]["args"])

    def test_module_commands_and_actions_insert_through_core(self):
        for title, expected in (("Module command", "echo hello"),
                                ("Module TOML action", "echo toml")):
            with self.subTest(title=title):
                result, _ = self.run_palette(
                    [{"select_contains": title}], in_tmux=False, git_repo=True,
                    modules=self.demo_module())
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected)

    def test_files_shortcut_with_module_tabs(self):
        result, calls = self.run_palette(
            [{"select_contains": "with space.txt"}], args=("--files",),
            in_tmux=False, git_repo=True, modules=self.demo_module())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "with\\ space.txt")
        self.assertEqual(len([c for c in calls if c["tool"] == "fzf"]), 1)

    def test_module_rechecks_context_before_selection(self):
        modules = self.demo_module()
        modules["demo"]["module.sh"] += '''
spotlight_demo_available() {
  [[ ! -f $PALETTE_TEST/context_seen ]] || return 1
  printf '' > "$PALETTE_TEST/context_seen"
}
'''
        result, _ = self.run_palette(
            [{"select_contains": "Module command"}], in_tmux=False, modules=modules)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("Module is no longer available: demo", result.stderr)

    def test_module_listing_failure_is_reported(self):
        modules = self.demo_module()
        modules["demo"]["module.sh"] += '''
spotlight_demo_list() { printf 'listing failed\\n' >&2; return 7; }
'''
        result, _ = self.run_palette(
            [{"output": "\nright\n"}], in_tmux=False, git_repo=True, modules=modules)
        self.assertEqual(result.returncode, 1)
        self.assertIn("listing failed", result.stderr)
        self.assertIn("Failed to load Extra 1 tab", result.stderr)

    def test_module_toml_rechecks_context_before_parameter_sources(self):
        modules = self.demo_module()
        modules["demo"]["module.sh"] += '''
spotlight_demo_available() {
  [[ ! -f $PALETTE_TEST/context_seen ]] || return 1
  printf '' > "$PALETTE_TEST/context_seen"
}
'''
        modules["demo"]["actions.toml"] = '''[[actions]]
id = "demo.parameter"
title = "Contextual parameter"
category = "Demo"
command = "echo <value>"
[actions.parameters.value]
source = "printf source-must-not-run >&2; exit 1"
'''
        result, calls = self.run_palette(
            [{"select_contains": "Contextual parameter"}], in_tmux=False, modules=modules)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("Module is no longer available: demo", result.stderr)
        self.assertNotIn("source-must-not-run", result.stderr)
        self.assertEqual(len([c for c in calls if c["tool"] == "fzf"]), 1)

    def test_invalid_or_duplicate_module_registration_fails(self):
        for modules in (
            {"tmux": {"module.sh": "true"}},
            {"bad-name": {"module.sh": "true"}},
            {"core": {"module.sh": "true"}},
            {"demo": {"module.sh": 'spotlight_demo_list() { :; }; spotlight_demo_select() { :; }; spotlight_demo_tabs() { spotlight_module_tab demo x One; spotlight_module_tab demo x Two; }'}},
        ):
            with self.subTest(modules=modules):
                result, calls = self.run_palette([], modules=modules)
                self.assertEqual(result.returncode, 1)
                self.assertIn("Invalid or duplicate module", result.stderr)
                self.assertFalse(calls)

    def test_incomplete_module_contributions_fail_at_registration(self):
        cases = (
            ('spotlight_demo_tabs() { spotlight_module_tab demo x Example; }', 'list'),
            ('spotlight_demo_list() { :; }; spotlight_demo_tabs() { spotlight_module_tab demo x Example; }', 'select'),
            ('spotlight_demo_commands() { :; }', 'select'),
            ('spotlight_demo_settings() { :; }', 'setting_select'),
        )
        for source, missing in cases:
            with self.subTest(missing=missing):
                result, calls = self.run_palette([], modules={"demo": {"module.sh": source}})
                self.assertEqual(result.returncode, 1)
                self.assertIn(f'Module demo requires callback spotlight_demo_{missing}', result.stderr)
                self.assertFalse(calls)

    def test_optional_module_preview_has_a_fallback(self):
        modules = self.demo_module()
        modules["demo"]["module.sh"] = modules["demo"]["module.sh"].replace(
            'spotlight_demo_preview() { printf \'Module preview: %s\\n\' "$1"; }', '')
        result, calls = self.run_palette(
            [{"select_contains": "Module command", "preview": "module:demo:hello"}],
            in_tmux=False, git_repo=True, modules=modules)
        self.assertEqual(result.returncode, 0, result.stderr)
        preview = next(c for c in calls if c["tool"] == "preview")
        self.assertEqual(preview["status"], 0)
        self.assertEqual(preview["output"], "No preview available.\n")

    def test_commands_are_lazy_and_cancel_is_success(self):
        result, calls = self.run_palette([{"status": 130}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(call["tool"] == "tmux" for call in calls))
        screen = next(call for call in calls if call["tool"] == "fzf")
        self.assertIn("New window", screen["input"])
        header = next(arg for arg in screen["args"] if arg.startswith("--header="))
        self.assertIn("\x1b[1m Commands ", header)
        self.assertEqual(header.count("\x1b[48;2;125;211;168m"), 1)
        self.assertNotIn("\n", header)
        self.assertNotIn("Left/Right", header)

    def test_outside_tmux_shows_only_general_commands_and_files(self):
        result, calls = self.run_palette(
            [{"select_contains": "General command"}], in_tmux=False,
            command_rows='[[actions]]\nid = "general"\ntitle = "General command"\ncategory = "System"\ndescription = "Useful"\ncommand = "echo hello"\n[[actions]]\nid = "tmux"\ntitle = "Tmux command"\ncategory = "System"\ndescription = "Only inside"\ncommand = "echo tmux"\n[actions.context]\nrequires_tmux = true\n',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "echo hello")
        self.assertFalse(any(call["tool"] == "tmux" for call in calls))
        screen = next(call for call in calls if call["tool"] == "fzf")
        self.assertIn("General command", screen["input"])
        self.assertNotIn("Tmux command", screen["input"])
        self.assertNotIn("New window", screen["input"])
        self.assertIn("Install action file", screen["input"])
        header = next(arg for arg in screen["args"] if arg.startswith("--header="))
        self.assertIn("Commands", header)
        self.assertIn("Files", header)
        self.assertNotIn("Windows", header)

    def test_outside_tmux_file_inserts_quoted_relative_path(self):
        result, calls = self.run_palette(
            [{"select_contains": "with space.txt"}], args=("--files",), in_tmux=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("with\\ space.txt", result.stdout)
        self.assertFalse(any(call["tool"] == "tmux" for call in calls))

    def test_command_columns_align_with_long_titles(self):
        actions = '[[actions]]\nid = "short"\ntitle = "Short action"\ncategory = "System"\ndescription = "First description"\ncommand = "echo one"\n[[actions]]\nid = "long"\ntitle = "An action title much longer than the column width"\ncategory = "Docker Maintenance"\ndescription = "Second description"\ncommand = "echo two"\n'
        result, calls = self.run_palette([{"status": 130}], in_tmux=False,
                                         command_rows=actions)
        self.assertEqual(result.returncode, 0, result.stderr)
        listing = next(call["input"] for call in calls if call["tool"] == "fzf")
        first = re.sub(r"\x1b\[[0-9;]*m", "", next(line for line in listing.splitlines() if "Short action" in line))
        second = re.sub(r"\x1b\[[0-9;]*m", "", next(line for line in listing.splitlines() if "Second description" in line))
        self.assertEqual(first.index("System"), second.index("Docker Maintenance"))
        self.assertEqual(first.index("First description"), second.index("Second description"))

    def test_git_context_filters_actions(self):
        action_data = '[[actions]]\nid = "git.pull"\ntitle = "Pull changes"\ncategory = "Git"\ncommand = "git pull"\n[actions.context]\nrequires_git_repo = true\n'
        result, calls = self.run_palette([{"status": 130}], in_tmux=False,
                                         command_rows=action_data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Pull changes", next(call["input"] for call in calls if call["tool"] == "fzf"))
        result, calls = self.run_palette([{"select_contains": "Pull changes"}],
                                         in_tmux=False, command_rows=action_data, git_repo=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "git pull")
        result, calls = self.run_palette([{"status": 130}], in_tmux=False,
                                         command_rows=action_data, git_repo="bare",
                                         modules=self.demo_module())
        self.assertEqual(result.returncode, 0, result.stderr)
        screen = next(c for c in calls if c["tool"] == "fzf")
        self.assertNotIn("Pull changes", screen["input"])
        self.assertNotIn("Module command", screen["input"])

    def test_parameter_choices_insert_quoted_value_without_running_action(self):
        action_data = r'''[[actions]]
id = "image.remove"
title = "Remove image"
category = "Docker"
command = "docker image rm <image_id>"
[actions.parameters.image_id]
source = 'printf "img-a\tfirst:latest\nimg-b\tsecond:latest\n"'
'''
        result, calls = self.run_palette(
            [{"select_contains": "Remove image"}, {"select_contains": "second:latest"}],
            command_rows=action_data, in_tmux=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "docker image rm img-b")
        self.assertTrue(all("--no-clear" in call["args"] for call in calls if call["tool"] == "fzf"))
        picker = [call for call in calls if call["tool"] == "fzf"][-1]
        self.assertIn("first:latest", picker["input"])
        self.assertIn("second:latest", picker["input"])
        self.assertIn("\timg-a", picker["input"])
        self.assertIn("\timg-b", picker["input"])
        self.assertIn("--layout=reverse", picker["args"])
        self.assertIn("--header-first", picker["args"])
        self.assertIn("--prompt=  Search ❯ ", picker["args"])
        self.assertTrue(any("Remove image" in arg for arg in picker["args"] if arg.startswith("--header=")))
        self.assertTrue(any(arg.startswith("--preview=") for arg in picker["args"]))

        result, _ = self.run_palette(
            [{"select_contains": "Remove image"}, {"status": 130}],
            command_rows=action_data, in_tmux=False,
        )
        self.assertEqual(result.returncode, 130)
        self.assertEqual(result.stdout, "")

        result, calls = self.run_palette(
            [{"select_contains": "Remove image"}, {"select_contains": "second:latest"}],
            command_rows=action_data, in_tmux=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[-1]["args"], ["send-keys", "-t", "%1", "-l", "--", "docker image rm img-b"])

    def test_actions_from_multiple_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, command in (("one.toml", "echo one"), ("two.toml", "echo two")):
                (root / name).write_text(f'[[actions]]\nid = "{name}"\ntitle = "{name}"\ncategory = "Test"\ncommand = "{command}"\n')
            result = subprocess.run(["python3", str(PALETTE.parent.parent / "lib/actions.py")],
                                    env=dict(os.environ, SPOTLIGHT_ACTION_PATH=str(root)),
                                    text=True, capture_output=True, check=True)
            self.assertIn("echo one", result.stdout)
            self.assertIn("echo two", result.stdout)

    def test_navi_commands_insert_in_shell_and_tmux(self):
        cheat = "% gpg, security\n# Export public key\ngpg --export <key>\n$ key: printf 'hello world\\n'\n"
        for in_tmux in (False, True):
            with self.subTest(in_tmux=in_tmux):
                result, calls = self.run_palette(
                    [{"select_contains": "Export public key"}, {"select_contains": "hello world"}],
                    command_rows=cheat, action_suffix=".cheat", in_tmux=in_tmux)
                self.assertEqual(result.returncode, 0, result.stderr)
                if in_tmux:
                    insertion = next(call for call in calls if call["tool"] == "tmux" and call["args"][0] == "send-keys")
                    self.assertEqual(insertion["args"][-1], "gpg --export 'hello world'")
                else:
                    self.assertEqual(result.stdout, "gpg --export 'hello world'")

    def test_manual_parameter_is_shell_quoted_and_reused(self):
        module_path = PALETTE.parent.parent / "lib/actions.py"
        spec = importlib.util.spec_from_file_location("spotlight_actions", module_path)
        actions = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(actions)

        class Terminal:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def write(self, _):
                pass

            def flush(self):
                pass

            def readline(self):
                return "hello world\n"

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual.toml"
            path.write_text('[[actions]]\nid = "manual"\ntitle = "Manual"\ncategory = "Test"\ncommand = "echo <word> <word>"\n[actions.parameters.word]\nprompt = "Word"\n')
            with mock.patch("builtins.open", return_value=Terminal()):
                command = actions.resolve(path, "manual", "echo <word> <word>", directory)
            self.assertEqual(command, "echo 'hello world' 'hello world'")

    def test_install_downloads_valid_actions_and_rejects_duplicate_ids(self):
        module_path = PALETTE.parent.parent / "lib/actions.py"
        spec = importlib.util.spec_from_file_location("spotlight_actions", module_path)
        actions = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(actions)

        class Response(io.BytesIO):
            def geturl(self):
                return "https://example.com/extra.toml"

        with tempfile.TemporaryDirectory() as directory:
            env = {"XDG_CONFIG_HOME": directory,
                   "XDG_CACHE_HOME": directory,
                   "SPOTLIGHT_ACTION_PATH": str(PALETTE.parent.parent / "actions")}
            data = b'[[actions]]\nid = "extra.action"\ntitle = "Extra"\ncategory = "Test"\ncommand = "echo extra"\n'
            with mock.patch.dict(os.environ, env), mock.patch("urllib.request.urlopen", return_value=Response(data)):
                actions.cached_records()
                cache = actions.cache_path()
                self.assertTrue(cache.exists())
                with mock.patch.dict(os.environ, {"SPOTLIGHT_EXTRA_ACTION_PATH": str(Path(directory) / "variant.toml")}):
                    actions.cached_records()
                    variant_cache = actions.cache_path()
                    self.assertNotEqual(cache, variant_cache)
                    self.assertTrue(variant_cache.exists())
                unrelated = cache.parent / "unrelated.txt"
                unrelated.write_text("keep")
                actions.install("https://example.com/extra.toml")
                self.assertFalse(cache.exists())
                self.assertFalse(variant_cache.exists())
                self.assertTrue(unrelated.exists())
            installed = list((Path(directory) / "spotlight/actions").glob("*.toml"))
            self.assertEqual(len(installed), 1)
            self.assertEqual(installed[0].read_bytes(), data)

            duplicate = b'[[actions]]\nid = "system.update"\ntitle = "Duplicate"\ncategory = "Test"\ncommand = "echo duplicate"\n'
            with mock.patch.dict(os.environ, env), mock.patch("urllib.request.urlopen", return_value=Response(duplicate)):
                with self.assertRaisesRegex(ValueError, "duplicate action id"):
                    actions.install("https://example.com/duplicate.toml")
            self.assertEqual(len(list((Path(directory) / "spotlight/actions").glob("*.toml"))), 1)

    def test_parameter_source_timeout_is_reported(self):
        spec = importlib.util.spec_from_file_location("spotlight_actions", PALETTE.parent.parent / "lib/actions.py")
        actions = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(actions)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "timeout.toml"
            path.write_text('[[actions]]\nid="timeout"\ntitle="Timeout"\ncategory="Test"\ncommand="echo <value>"\n[actions.parameters.value]\nsource="unused"\n')
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": directory, "SPOTLIGHT_THEME_DATA": ""}), mock.patch(
                    "subprocess.run", side_effect=subprocess.TimeoutExpired("sh", 30)):
                with self.assertRaisesRegex(ValueError, "suggestions timed out after 30 seconds"):
                    actions.resolve(path, "timeout", "echo <value>", directory)

    def test_tabs_cache_queries_refresh_and_wrap(self):
        result, calls = self.run_palette([
            {"output": "split\nright\n"},
            {"output": "editor\nleft\n"},
            {"output": "split\nright\n"},
            {"output": "editor\nctrl-r\n"},
            {"output": "editor\nright\n"},
            {"output": "\nright\n"},
            {"output": "\nright\n"},
            {"output": "\nright\n"},
            {"output": "split\nright\n"},
            {"status": 130},
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        providers = [call["args"][0] for call in calls
                     if call["tool"] == "tmux"]
        self.assertEqual(providers, [
            "list-windows", "list-windows", "list-sessions", "list-panes", "display-message",
        ])
        screens = [call for call in calls if call["tool"] == "fzf"]
        self.assertIn("--query=split", screens[2]["args"])
        self.assertIn("--query=editor", screens[3]["args"])
        self.assertIn("--query=editor", screens[4]["args"])
        self.assertIn("--query=", screens[7]["args"])
        self.assertIn("--query=split", screens[9]["args"])
        headers = [next(arg for arg in screen["args"] if arg.startswith("--header="))
                   for screen in screens]
        self.assertIn("\x1b[1m Commands ", headers[9])
        self.assertEqual(len({len(re.sub(r"\x1b\[[0-9;]*m", "", header))
                              for header in headers}), 1)

    def test_selecting_targets_and_existing_commands(self):
        cases = [
            (0, "new-window", [["new-window"]]),
            (0, "switch-tree", [["choose-tree", "-Z"]]),
            (1, "window:$1:@2", [
                ["switch-client", "-t", "$1"],
                ["select-window", "-t", "$1:@2"],
            ]),
            (2, "session:$1", [["switch-client", "-t", "$1"]]),
            (3, "pane:$1:@2.%3", [
                ["switch-client", "-t", "$1"],
                ["select-window", "-t", "$1:@2.%3"],
                ["select-pane", "-t", "$1:@2.%3"],
            ]),
        ]
        for tab, target, expected in cases:
            with self.subTest(target=target):
                result, calls = self.run_palette(
                    [{"output": "\nright\n"}] * tab +
                    [{"output": f"\n\n  selected\tmodule:tmux:{target}\n"}]
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                actions = [call["args"] for call in calls
                           if call["tool"] == "tmux"
                           and not call["args"][0].startswith("list-")]
                self.assertEqual(actions, expected)

    def test_reload_config_prefers_home_file_then_xdg(self):
        for home_config in ("", "set -g mouse off\n"):
            with self.subTest(home_config=bool(home_config)):
                result, calls = self.run_palette(
                    [{"output": "\n\n  Reload configuration\tmodule:tmux:reload-config\n"}],
                    home_config=home_config,
                    config_files={"../tmux/tmux.conf": "set -g mouse on\n"},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                source = next(call for call in calls if call["tool"] == "tmux"
                              and call["args"][0] == "source-file")
                path = Path(source["args"][1])
                if home_config:
                    self.assertEqual(path.name, ".tmux.conf")
                    self.assertEqual(path.parent.name, "home")
                else:
                    self.assertEqual(path.parts[-3:], (".config", "tmux", "tmux.conf"))

    def test_reload_config_reports_missing_configuration(self):
        result, calls = self.run_palette(
            [{"output": "\n\n  Reload configuration\tmodule:tmux:reload-config\n"}],
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tmux configuration not found", result.stderr)
        self.assertFalse(any(call["tool"] == "tmux" and call["args"][0] == "source-file"
                             for call in calls))

    def test_provider_failure_is_reported(self):
        result, _ = self.run_palette(
            [{"output": "\nright\n"}], fail_provider="list-windows",
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("tmux provider failed", result.stderr)
        self.assertIn("Failed to load Windows tab", result.stderr)

    def test_fzf_failure_is_not_treated_as_cancel(self):
        result, _ = self.run_palette([{"status": 2}])
        self.assertEqual(result.returncode, 2)
        self.assertIn("fzf failed", result.stderr)

    def test_empty_tab_can_still_switch(self):
        result, calls = self.run_palette([
            {"output": "\nright\n", "status": 1},
            {"status": 130},
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(call["args"][0] == "list-windows"
                            for call in calls))

    def test_files_shortcut_inserts_path_at_current_cursor(self):
        result, calls = self.run_palette(
            [{"output": "\n\n  example.txt\tfile:PLACEHOLDER\n"}],
            args=("--files",),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        search = next(call for call in calls if call["tool"] == "fzf")
        self.assertIn("example.txt", search["input"])
        self.assertTrue(any("\x1b[1m Files " in arg for arg in search["args"]))
        self.assertEqual(calls[-1]["args"],
                         ["send-keys", "-t", "%1", "-l", "--", "example.txt"])

    def test_inserted_file_path_is_shell_quoted(self):
        result, calls = self.run_palette(
            [{"output": "\n\n  with space.txt\tfile:SPACE_PATH\n"}],
            args=("--files",),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[-1]["args"],
                         ["send-keys", "-t", "%1", "-l", "--", r"with\ space.txt"])

    def test_non_git_file_search_prunes_configured_directories(self):
        result, calls = self.run_palette([{"status": 130}], args=("--files",))
        self.assertEqual(result.returncode, 0, result.stderr)
        listing = next(call["input"] for call in calls if call["tool"] == "fzf")
        self.assertIn("example.txt", listing)
        self.assertNotIn(".git/hidden.txt", listing)
        self.assertIn("node_modules/hidden.txt", listing)

        result, calls = self.run_palette(
            [{"status": 130}], args=("--files",),
            prune_config=".git\nnode_modules\ntarget\n.cargo\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        listing = next(call["input"] for call in calls if call["tool"] == "fzf")
        self.assertIn("example.txt", listing)
        self.assertNotIn("hidden.txt", listing)

        result, calls = self.run_palette(
            [{"status": 130}], args=("--files",), prune_config="",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        listing = next(call["input"] for call in calls if call["tool"] == "fzf")
        self.assertIn(".git/hidden.txt", listing)

    def test_unusual_file_names_survive_search_and_insertion(self):
        for name in ("odd\tline\nname%.txt", "odd\n", "odd\n\n"):
            for git_repo in (False, True):
                for in_tmux in (False, True):
                    with self.subTest(name=name, git_repo=git_repo, in_tmux=in_tmux):
                        result, calls = self.run_palette(
                            [{"select_contains": "odd"}], args=("--files",),
                            extra_files={name: b"hello\n"}, git_repo=git_repo, in_tmux=in_tmux,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        listing = next(call["input"] for call in calls if call["tool"] == "fzf")
                        self.assertIn(r"\n", listing)
                        self.assertNotIn(name, listing)
                        inserted = calls[-1]["args"][-1] if in_tmux else result.stdout
                        restored = subprocess.run(
                            ["bash", "-c", "printf '%s' " + inserted],
                            text=True, capture_output=True, check=True,
                        ).stdout
                        self.assertEqual(restored, name)

    @unittest.skipUnless(shutil.which("file"), "file command is unavailable")
    def test_file_preview_handles_binary_empty_and_escaped_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "binary.dat"
            binary.write_bytes(b"text\0binary\n")
            empty = root / "empty.txt"
            empty.write_bytes(b"")
            unusual = root / "odd\tline\nname%.txt"
            unusual.write_text("hello\n")
            for path, expected in ((binary, "Binary file; preview unavailable."),
                                   (empty, "(empty file)"), (unusual, "hello")):
                encoded = str(path).replace("%", "%25").replace("\t", "%09").replace("\n", "%0A")
                result = subprocess.run(
                    ["bash", str(PALETTE), "--preview", "file:" + encoded],
                    text=True, capture_output=True, timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)
                self.assertNotIn("\0", result.stdout)

    def test_custom_snippet_is_searchable_and_inserted_without_running(self):
        result, calls = self.run_palette(
            [{"select_contains": "Docker images"}],
            command_rows='[[actions]]\nid = "docker.images"\ntitle = "Docker images"\ncategory = "Docker"\ndescription = "List images by size"\ncommand = "docker images | sort"\n',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        search = next(call for call in calls if call["tool"] == "fzf")
        self.assertIn("Docker images", search["input"])
        self.assertIn("List images by size", search["input"])
        self.assertIn("\tsnippet:docker.images\tDocker\tList images by size\tdocker images | sort", search["input"])
        self.assertTrue(any("{2} {3} {4} {5} {6}" in arg for arg in search["args"]))
        self.assertEqual(calls[-1]["args"],
                         ["send-keys", "-t", "%1", "-l", "--", "docker images | sort"])

    def test_commands_cache_survives_reopen_until_refresh(self):
        result, calls = self.run_palette(
            [{"status": 130}, {"status": 130},
             {"output": "\nctrl-r\n"}, {"status": 130}],
            command_rows='[[actions]]\nid = "original"\ntitle = "Original"\ncategory = "System"\ndescription = "Old description"\ncommand = "echo old"\n',
            command_rows_after_first='[[actions]]\nid = "updated"\ntitle = "Updated"\ncategory = "System"\ndescription = "New description"\ncommand = "echo new"\n',
            launches=3,
            tmux_launches=(True, False, True),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        screens = [call["input"] for call in calls if call["tool"] == "fzf"]
        self.assertEqual(len(screens), 4)
        self.assertTrue(all("Original" in screen and "Updated" not in screen
                            for screen in screens[:3]))
        self.assertIn("Updated", screens[3])
        self.assertNotIn("Original", screens[3])
        self.assertFalse(any(call["tool"] == "tmux" for call in calls))

    def test_snippet_preview_uses_cached_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                ["bash", str(PALETTE), "--preview", "snippet:2", "DOCKER",
                 "List images by size", "docker images | sort"],
                env=dict(os.environ, SPOTLIGHT_ACTION_PATH="/nonexistent/test.toml",
                         XDG_CONFIG_HOME=directory, XDG_CACHE_HOME=directory, SPOTLIGHT_THEME_DATA=""),
                text=True, capture_output=True, timeout=10,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("List images by size", result.stdout)
        self.assertIn("\x1b[1m\x1b[38;5;114mdocker images | sort\x1b[0m", result.stdout)


if __name__ == "__main__":
    unittest.main()
