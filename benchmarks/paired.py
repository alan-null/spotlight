#!/usr/bin/env python3
"""Alternate revisions to reduce drift; reuse run.py fixtures and accounting."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

DIRECTORY = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('spotlight_benchmark', DIRECTORY / 'run.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def aggregate(reports, warmups):
    result = dict(reports[0])
    for report in reports[1:]:
        if report['source_sha256'] != result['source_sha256'] or benchmark.compare(result, report)['warnings']:
            raise ValueError('Source or measurement environment changed during paired runs')
    result.update(runs=len(reports), warmups=warmups,
                  sampling='alternating revisions; fixtures recreated each pass',
                  paired_driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    result['scenarios'] = {}
    for name in reports[0]['scenarios']:
        samples = [sample for report in reports for sample in report['scenarios'][name]['samples']]
        elapsed = sorted(sample['elapsed_ms'] for sample in samples)
        rss = [sample['peak_process_rss_kib'] for sample in samples if sample['peak_process_rss_kib'] is not None]
        result['scenarios'][name] = dict(samples=samples, median_ms=statistics.median(elapsed),
                                       p95_ms=elapsed[math.ceil(len(elapsed) * .95) - 1],
                                       max_peak_process_rss_kib=max(rss, default=None))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('--runs', type=int, default=20)
    parser.add_argument('--warmups', type=int, default=2)
    parser.add_argument('--docker', action='store_true')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.runs < 1 or args.warmups < 0:
        parser.error('runs must be positive and warmups nonnegative')
    sources = [args.before.resolve(), args.after.resolve()]
    reports = [[], []]
    for iteration in range(args.warmups + args.runs):
        # Reverse order on alternate passes to balance order effects.
        for side in ((0, 1) if iteration % 2 == 0 else (1, 0)):
            if args.docker:
                command = ['bash', str(DIRECTORY / 'docker-run.sh'), str(sources[side])]
            else:
                command = [sys.executable, str(DIRECTORY / 'run.py'), '--source', str(sources[side])]
            report = json.loads(subprocess.check_output(command + ['--runs', '1', '--warmups', '0'], text=True))
            if iteration >= args.warmups:
                reports[side].append(report)
        print(f'Paired pass {iteration + 1}/{args.warmups + args.runs}', file=sys.stderr, flush=True)
    before, after = (aggregate(side, args.warmups) for side in reports)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, report in (('before', before), ('after', after)):
        (args.output_dir / f'{name}.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(benchmark.compare(before, after), indent=2))


if __name__ == '__main__':
    main()
