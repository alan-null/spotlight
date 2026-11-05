#!/usr/bin/env python3
"""Optional actual fzf/tmux PTY smoke check; no mocks or user configuration.

Run: python3 tests/smoke_terminal.py [--outside-only]
Requires host fzf, tmux, Bash, and permission to create a PTY/private socket.
"""
import argparse
import errno
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import select
import shlex
import signal
import struct
import subprocess
import tempfile
import termios
import time

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = str(ROOT / 'bin/spotlight')


class Terminal:
    def __init__(self, command, env, cwd):
        self.pid, self.fd = pty.fork()
        if not self.pid:
            os.chdir(cwd)
            os.execvpe(command[0], command, env)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 150, 0, 0))
        self.output = b''
        self.status = None

    def send(self, data):
        self.output = b''
        os.write(self.fd, data)

    def pump(self):
        if select.select([self.fd], [], [], 0.05)[0]:
            try:
                self.output = (self.output + os.read(self.fd, 65536))[-131072:]
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
        if self.status is None:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid:
                self.status = os.waitstatus_to_exitcode(status)

    def wait(self, predicate, description):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            self.pump()
            if predicate():
                return
            if self.status is not None:
                break
        raise AssertionError(f'{description}; status={self.status}; terminal tail={self.output[-1500:]!r}')

    def expect(self, text):
        self.wait(lambda: text.encode() in self.output, f'waiting for {text!r}')

    def filter_one(self, query):
        self.send(query.encode())
        # Query echo precedes fzf's asynchronous filtering. Wait for the rendered
        # single-match count before Enter can select a stale row.
        self.wait(lambda: re.search(rb'(?<![0-9])1/[0-9]+',
                                   re.sub(rb'\x1b\[[0-?]*[ -/]*[@-~]', b'', self.output)),
                  f'waiting for one filtered match for {query!r}')

    def close(self):
        if self.status is None:
            try:
                os.killpg(self.pid, signal.SIGTERM)
                self.wait(lambda: self.status is not None, 'terminal cleanup')
            except (ProcessLookupError, AssertionError):
                try:
                    os.killpg(self.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.waitpid(self.pid, 0)
        os.close(self.fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outside-only', action='store_true', help='skip the private tmux server')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='spotlight-smoke-') as temporary:
        work = Path(temporary)
        action = work / 'actions.toml'
        marker = work / 'executed'
        snippet = f'touch {shlex.quote(str(marker))}'
        action.write_text(f'[[actions]]\nid="smoke"\ntitle="SmokeAction"\ncategory="Smoke"\ncommand={json.dumps(snippet)}\n')
        env = dict(PATH='/usr/bin:/bin', HOME=str(work), TERM='xterm-256color',
                   SHELL='/bin/bash', PS1='SMOKE> ', XDG_CONFIG_HOME=str(work / 'config'),
                   XDG_STATE_HOME=str(work / 'state'),
                   XDG_CACHE_HOME=str(work / 'cache'), SPOTLIGHT_ACTION_PATH=str(action),
                   SPOTLIGHT_MODULE_PATH=str(ROOT / 'modules'), TMPDIR=str(work))
        for mode in ('cancel', 'search', 'repeat'):
            result = work / 'result'
            command = f'exec {shlex.quote(LAUNCHER)} > {shlex.quote(str(result))}'
            terminal = Terminal(['bash', '--noprofile', '--norc', '-c', command], env, work)
            try:
                terminal.expect('Search')
                if mode == 'repeat':
                    terminal.expect('↺')
                else:
                    terminal.filter_one('SmokeAction')
                terminal.send(b'\x1b' if mode == 'cancel' else b'\r')
                terminal.wait(lambda: terminal.status is not None, 'outside-tmux exit')
                assert terminal.status == 0
                assert result.read_text() == ('' if mode == 'cancel' else snippet)
                assert not marker.exists()
            finally:
                terminal.close()
        print('PASS real fzf: cancellation, exact selection, and empty-query recent reuse', flush=True)
        for mode in ('cancel', 'invalid-url'):
            result = work / 'download-result'
            command = f'exec {shlex.quote(LAUNCHER)} > {shlex.quote(str(result))}'
            terminal = Terminal(['bash', '--noprofile', '--norc', '-c', command], env, work)
            try:
                terminal.expect('Search')
                terminal.filter_one('Install action file')
                terminal.send(b'\r')
                terminal.expect('Paste an HTTPS URL')
                if mode == 'invalid-url':
                    terminal.send(b'http://example.com/actions.toml\r')
                    terminal.expect('Could not install action file')
                    terminal.expect('Edit URL')
                    terminal.send(b'\x1b[B\r')
                    terminal.expect('Paste an HTTPS URL')
                    terminal.expect('http://example.com/actions.toml')
                terminal.send(b'\x1b')
                terminal.expect('Search')
                terminal.send(b'\x1b')
                terminal.wait(lambda: terminal.status is not None, 'downloader cancellation exit')
                assert terminal.status == 0
                assert result.read_text() == ''
            finally:
                terminal.close()
        print('PASS real fzf downloader: focused URL input, validation error, edit, and return to Commands', flush=True)
        if args.outside_only:
            return
        socket = str(work / 'tmux.sock')

        def tmux(*arguments):
            return subprocess.check_output(['tmux', '-S', socket, *arguments], env=env, text=True,
                                           stderr=subprocess.PIPE, timeout=5).strip()

        terminal = Terminal(['tmux', '-S', socket, '-f', '/dev/null', 'new-session', '-s', 'smoke',
                             "env PS1='SMOKE> ' bash --noprofile --norc -i"], env, work)
        try:
            terminal.expect('SMOKE>')
            pane = tmux('display-message', '-p', '#{pane_id}')

            def popup(arguments=''):
                terminal.send(f'{shlex.quote(LAUNCHER)} --popup {arguments}\r'.encode())
                terminal.expect('Search')

            popup()
            for label in ('WINDOW', 'SESSION', 'PANE'):
                terminal.send(b'\x1b[C')
                terminal.expect(label)
                terminal.send(b'\x12')
                terminal.expect(label)
            terminal.send(b'\x1b')
            terminal.expect('SMOKE>')
            popup()
            terminal.filter_one('SmokeAction')
            terminal.send(b'\r')
            terminal.expect(snippet)
            terminal.wait(lambda: tmux('display-message', '-p', '-t', pane, '#{pane_current_command}') == 'bash',
                          'waiting for popup teardown and return to the originating shell')
            captured = tmux('capture-pane', '-p', '-t', pane)
            assert snippet in captured
            assert tmux('display-message', '-p', '-t', pane, '#{pane_current_command}') == 'bash'
            assert not marker.exists(), 'command was executed instead of inserted'
            terminal.send(b'\x15')  # Clear inserted command without submitting it.
            popup('--settings')
            terminal.filter_one('Theme')
            terminal.send(b'\r')
            terminal.expect('Choose')
            terminal.filter_one('terminal')
            terminal.send(b'\r')
            terminal.expect('Search')
            settings = work / 'config/spotlight/settings.json'
            assert json.loads(settings.read_text())['core']['theme'] == 'terminal'
            terminal.send(b'\x1b')
            terminal.expect('SMOKE>')
            popup('--settings')
            terminal.expect('terminal')
            terminal.send(b'\x1b')
            terminal.expect('SMOKE>')
            print('PASS real tmux popup: module tabs, refresh, originating-pane insertion without Enter, theme change and reopen')

            # Simulate the old-version error, then use real fzf for the next launch.
            tools = work / 'legacy-tools'
            tools.mkdir()
            driver = tools / 'fzf'
            driver.write_text('''#!/bin/bash
if [[ ${1:-} == --version ]]; then printf '0.38.0\\n'; exit 0; fi
for argument in "$@"; do
  if [[ $argument == --info=inline-right ]]; then
    printf 'invalid info style (expected: default|hidden|inline)\\n' >&2
    exit 2
  fi
done
exec /usr/bin/fzf "$@"
''')
            driver.chmod(0o755)
            tmux('set-environment', '-g', 'PATH', str(tools) + ':' + env['PATH'])
            terminal.send(f'{shlex.quote(LAUNCHER)} --popup\r'.encode())
            terminal.expect('Updated Result count position')
            terminal.expect('Reopen Spotlight')
            assert json.loads(settings.read_text())['core']['fzf_info'] == 'inline'
            # Error text must be printed after leaving fzf's alternate screen.
            assert terminal.output.rfind(b'Updated Result count position') > terminal.output.rfind(b'\x1b[?1049l')
            terminal.send(b'\x1b')
            terminal.expect('SMOKE>')
            popup()
            terminal.send(b'\x1b')
            terminal.expect('SMOKE>')
            print('PASS tmux error recovery: simulated old-fzf failure, visible correction, saved inline mode, and successful reopen')
        finally:
            try:
                tmux('kill-server')
            except (subprocess.SubprocessError, FileNotFoundError):
                pass
            terminal.close()


if __name__ == '__main__':
    main()
