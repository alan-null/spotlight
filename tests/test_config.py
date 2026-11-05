import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    'spotlight_config', Path(__file__).resolve().parents[1] / 'lib/spotlight_config.py')
config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(config)


class FzfSettingTests(unittest.TestCase):
    def test_default_and_saved_mode_do_not_inspect_fzf(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, XDG_CONFIG_HOME=directory):
                with mock.patch('subprocess.run') as run:
                    self.assertEqual(config.fzf_info(), 'inline-right')
                    config.save('demo', 'mode', 'keep')
                    config.save('core', 'fzf_info', 'inline')
                    self.assertEqual(config.fzf_info(), 'inline')
                    self.assertEqual(config.get('demo', 'mode'), 'keep')
                    run.assert_not_called()
                with self.assertRaisesRegex(ValueError, 'core.fzf_info'):
                    config.save('core', 'fzf_info', 'invalid')

    def test_only_matching_error_and_confirmed_old_version_update_setting(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, XDG_CONFIG_HOME=directory):
                with mock.patch('subprocess.run') as run:
                    self.assertEqual(config.fzf_error('unrelated failure', 'inline-right'), 'unrelated failure')
                    self.assertEqual(config.fzf_error('invalid info style', 'inline'), 'invalid info style')
                    run.assert_not_called()
                for version in ('unknown', '0.42.0', '0.67.0', '1.0.0'):
                    with mock.patch('subprocess.run', return_value=mock.Mock(returncode=0, stdout=version)):
                        self.assertEqual(config.fzf_error('invalid info style', 'inline-right'), 'invalid info style')
                        self.assertEqual(config.fzf_info(), 'inline-right')
                with mock.patch('subprocess.run', side_effect=subprocess.TimeoutExpired('fzf', 2)):
                    self.assertEqual(config.fzf_error('invalid info style', 'inline-right'), 'invalid info style')
                with mock.patch('subprocess.run', return_value=mock.Mock(returncode=0, stdout='0.41.1')):
                    self.assertIn('Updated Result count position', config.fzf_error('invalid info style', 'inline-right'))
                    self.assertEqual(config.fzf_info(), 'inline')
