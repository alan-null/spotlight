#!/usr/bin/env python3
"""Controlled Spotlight component benchmarks; Python stdlib and Bash only."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time


def measure(command, env, cwd):
    # Python's own fork footprint can inflate wait4 RSS for tiny Bash children.
    # GNU time forks from its small executable instead; omit RSS if unavailable.
    timer = Path('/usr/bin/time')
    with tempfile.NamedTemporaryFile() as rss, tempfile.TemporaryFile() as errors:
        measured = [str(timer), '-f', '%M', '-o', rss.name, '--', *command] if timer.exists() else command
        start = time.perf_counter_ns()
        process = subprocess.run(measured, env=env, cwd=cwd, stdout=subprocess.DEVNULL,
                                 stderr=errors)
        elapsed = (time.perf_counter_ns() - start) / 1_000_000
        if process.returncode:
            errors.seek(0)
            raise RuntimeError(f"{command}: exit {process.returncode}: {errors.read().decode()}")
        peak_rss = int(Path(rss.name).read_text()) if timer.exists() else None
    return dict(elapsed_ms=elapsed, peak_process_rss_kib=peak_rss)


def source_hash(source):
    digest = hashlib.sha256()
    for directory in ('bin', 'lib', 'modules', 'themes', 'config'):
        for path in sorted((source / directory).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                digest.update(str(path.relative_to(source)).encode() + b'\0' + path.read_bytes())
    return digest.hexdigest()


def read_optional(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def revision(source):
    try:
        return subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'],
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def compare(before, after):
    if before['fixture'] != after['fixture']:
        raise ValueError('Cannot compare different fixtures')
    warnings = []
    for key in ('schema_version', 'harness_sha256', 'runs', 'warmups'):
        if before.get(key) != after.get(key):
            warnings.append(f'Measurement differs: {key}')
    for key in ('image', 'python', 'machine', 'kernel', 'cpu_model', 'resources', 'rss_tool'):
        if before['environment'].get(key) != after['environment'].get(key):
            warnings.append(f'Environment differs: {key}')
    changes = {}
    for name in sorted(before['scenarios'].keys() & after['scenarios'].keys()):
        old = before['scenarios'][name]['median_ms']
        new = after['scenarios'][name]['median_ms']
        changes[name] = dict(before_ms=old, after_ms=new, change_percent=(new / old - 1) * 100)
    return dict(warnings=warnings, scenarios=changes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--runs', type=int, default=30)
    parser.add_argument('--warmups', type=int, default=3)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--compare', nargs=2, metavar=('BEFORE_JSON', 'AFTER_JSON'))
    args = parser.parse_args()
    if args.compare:
        print(json.dumps(compare(*(json.loads(Path(p).read_text()) for p in args.compare)), indent=2))
        return
    if args.runs < 1 or args.warmups < 0:
        parser.error('runs must be positive and warmups nonnegative')
    source = args.source.resolve()
    with tempfile.TemporaryDirectory(prefix='spotlight-bench-') as temporary:
        root = Path(temporary)
        tools = root / 'tools'
        tools.mkdir()
        # Controlled drivers measure launcher work through the first fully consumed tab.
        for name, body in {'fzf': 'cat >/dev/null\nexit 130', 'git': 'exit 1',
                           'tput': 'exit 0'}.items():
            path = tools / name
            path.write_text('#!/bin/bash\n' + body + '\n')
            path.chmod(0o755)
        files = root / 'files'
        files.mkdir()
        for number in range(1000):
            (files / f'fixture-{number:04}.txt').write_text('spotlight benchmark\n')
        actions = root / 'actions.toml'
        actions.write_text(''.join(f'[[actions]]\nid = "bench-{n}"\ntitle = "Benchmark {n}"\ncategory = "BENCH"\ncommand = "printf fixture-{n}"\n' for n in range(200)))
        home = root / 'home'
        home.mkdir()
        env = dict(os.environ)
        for key in list(env):
            if key.startswith('SPOTLIGHT_') or key in ('TMUX', 'TMUX_PANE', 'BASH_ENV', 'ENV'):
                env.pop(key)
        env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'),
                   XDG_STATE_HOME=str(root / 'state'),
                   XDG_CACHE_HOME=str(root / 'cache'), SPOTLIGHT_ACTION_PATH=str(actions),
                   SPOTLIGHT_MODULE_PATH=str(source / 'modules'),
                   SPOTLIGHT_PROVIDER_tmux=str(source / 'modules/tmux/module.sh'),
                   PATH=f'{tools}:' + os.environ['PATH'], PYTHONDONTWRITEBYTECODE='1', LC_ALL='C')
        config = [sys.executable, str(source / 'lib/spotlight_config.py'), 'shell']
        snapshot = subprocess.check_output(config, env=env, text=True)
        # Apply exactly the theme assignments preview children inherit from the launcher.
        preview_env = dict(env)
        output = subprocess.check_output(['bash', '-c', snapshot + '\n env -0'], env=env)
        for item in output.split(b'\0'):
            if b'=' in item:
                key, value = item.split(b'=', 1)
                if key.startswith(b'SPOTLIGHT_'):
                    preview_env[key.decode()] = value.decode()
        cache = [sys.executable, str(source / 'lib/actions.py'), 'cache']
        recent_state = root / 'recent-state'
        recent_history = recent_state / 'spotlight/history-v1.tsv'
        recent_history.parent.mkdir(parents=True)
        recent_history.write_text(''.join(f'v:snippet:bench-{n}\tv:{actions}\tv:printf fixture-{n}\tv:printf fixture-{n}\n' for n in range(5)))
        scenarios = {
            'theme_bootstrap': (config, env),
            'actions_warm_cache_200': (cache, env),
            'actions_cold_cache_200': (cache, env),
            'module_preview_inherited_theme': (['bash', str(source / 'bin/spotlight'), '--preview', 'module:tmux:new-window'], preview_env),
            'launcher_commands_driver_200': (['bash', str(source / 'bin/spotlight')], env),
            'launcher_commands_recent5_driver_200': (['bash', str(source / 'bin/spotlight')], dict(env, XDG_STATE_HOME=str(recent_state))),
            'launcher_files_driver_1000': (['bash', str(source / 'bin/spotlight'), '--files'], env),
        }
        results = {}
        for name, (command, scenario_env) in scenarios.items():
            subprocess.run(cache, env=env, stdout=subprocess.DEVNULL, check=True)
            samples = []
            for iteration in range(args.warmups + args.runs):
                if name == 'actions_cold_cache_200':
                    shutil.rmtree(root / 'cache', ignore_errors=True)
                sample = measure(command, scenario_env, files)
                if iteration >= args.warmups:
                    samples.append(sample)
            elapsed = sorted(s['elapsed_ms'] for s in samples)
            results[name] = dict(median_ms=statistics.median(elapsed),
                                 p95_ms=elapsed[math.ceil(len(elapsed) * .95) - 1],
                                 max_peak_process_rss_kib=max((s['peak_process_rss_kib'] for s in samples if s['peak_process_rss_kib'] is not None), default=None),
                                 samples=samples)
        cpu = read_optional('/proc/cpuinfo') or ''
        report = dict(schema_version=1, source=str(source), source_sha256=source_hash(source),
                      source_revision=revision(source), harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      fixture=dict(version=2, actions=200, files=1000, history_entries=5, context='outside tmux/git'),
                      runs=args.runs, warmups=args.warmups,
                      environment=dict(image=os.environ.get('SPOTLIGHT_BENCH_IMAGE', 'host'),
                                       rss_tool='GNU time' if Path('/usr/bin/time').exists() else None,
                                       python=sys.version, machine=platform.machine(), kernel=platform.release(),
                                       cpu_model=next((line.split(':', 1)[1].strip() for line in cpu.splitlines() if line.startswith('model name')), None),
                                       resources={name: read_optional('/sys/fs/cgroup/' + name) for name in ('cpu.max', 'memory.max', 'memory.swap.max', 'pids.max')}),
                      scenarios=results)
        rendered = json.dumps(report, indent=2) + '\n'
        if args.output:
            args.output.write_text(rendered)
        else:
            print(rendered, end='')


if __name__ == '__main__':
    main()
