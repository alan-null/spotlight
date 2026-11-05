"""Harness logic checks, never timing thresholds. Run with unittest discover."""
import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import unittest


DIRECTORY = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('spotlight_benchmark', DIRECTORY / 'run.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)
paired_spec = importlib.util.spec_from_file_location('spotlight_paired', DIRECTORY / 'paired.py')
paired = importlib.util.module_from_spec(paired_spec)
paired_spec.loader.exec_module(paired)


class BenchmarkTests(unittest.TestCase):
    def report(self):
        return dict(fixture=dict(version=1), runs=5, warmups=1,
                    environment=dict(image='abc123def456', python='3.12', machine='x86_64',
                                     kernel='test', cpu_model='fixture', resources={'cpu.max': '100000 100000'},
                                     rss_tool='GNU time'),
                    scenarios={'example': {'median_ms': 20}})

    def test_comparison_tracks_changes_and_resource_mismatch(self):
        before = self.report()
        after = copy.deepcopy(before)
        after['scenarios']['example']['median_ms'] = 10
        after['environment']['resources']['cpu.max'] = 'max 100000'
        result = benchmark.compare(before, after)
        self.assertEqual(result['scenarios']['example']['change_percent'], -50)
        self.assertIn('Environment differs: resources', result['warnings'])

    def test_fixture_mismatch_is_rejected(self):
        after = self.report()
        after['fixture']['version'] = 2
        with self.assertRaises(ValueError):
            benchmark.compare(self.report(), after)

    def test_runtime_and_sampling_mismatches_are_visible(self):
        after = self.report()
        after['environment']['kernel'] = 'different'
        after['runs'] = 50
        after['warmups'] = 3
        warnings = benchmark.compare(self.report(), after)['warnings']
        self.assertIn('Environment differs: kernel', warnings)
        self.assertIn('Measurement differs: runs', warnings)
        self.assertIn('Measurement differs: warmups', warnings)

    def test_mutable_image_rejected_before_docker(self):
        result = subprocess.run(['bash', str(DIRECTORY / 'docker-run.sh')],
                                env=dict(os.environ, SPOTLIGHT_BENCH_IMAGE='python:latest'),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('immutable image', result.stderr)

    def test_paired_aggregation_preserves_samples_and_quantiles(self):
        reports = []
        for elapsed in (10, 30, 20):
            report = self.report()
            report.update(source_sha256='fixed', runs=1, warmups=0)
            report['scenarios']['example']['samples'] = [dict(elapsed_ms=elapsed, peak_process_rss_kib=None)]
            reports.append(report)
        combined = paired.aggregate(reports, 2)
        self.assertEqual(combined['runs'], 3)
        self.assertEqual(combined['warmups'], 2)
        scenario = combined['scenarios']['example']
        self.assertEqual(scenario['median_ms'], 20)
        self.assertEqual(scenario['p95_ms'], 30)
        self.assertIsNone(scenario['max_peak_process_rss_kib'])
        self.assertEqual(len(scenario['samples']), 3)

    def test_paired_aggregation_rejects_changed_source(self):
        before = self.report()
        before['source_sha256'] = 'first'
        after = copy.deepcopy(before)
        after['source_sha256'] = 'second'
        with self.assertRaisesRegex(ValueError, 'Source or measurement environment changed'):
            paired.aggregate([before, after], 0)


if __name__ == '__main__':
    unittest.main()
