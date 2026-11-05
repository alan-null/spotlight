import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "lib/history.py"
SPEC = importlib.util.spec_from_file_location("spotlight_history", SCRIPT)
history = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(history)


def row(number):
    return f"v:snippet:{number}\tv:\tv:echo %09\tv:echo {number}"


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.environment = mock.patch.dict(os.environ, {"XDG_STATE_HOME": self.temp.name})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.saved_snapshot = os.environ.pop("SPOTLIGHT_HISTORY_FILE", None)
        if self.saved_snapshot is not None:
            self.addCleanup(os.environ.__setitem__, "SPOTLIGHT_HISTORY_FILE", self.saved_snapshot)

    def test_paths_and_limits(self):
        self.assertEqual(history.history_path(), Path(self.temp.name) / "spotlight/history-v1.tsv")
        with mock.patch.dict(os.environ, {"SPOTLIGHT_HISTORY_FILE": "/snapshot/history.tsv"}):
            self.assertEqual(history.history_path(), Path("/snapshot/history.tsv"))
            self.assertEqual(history.history_path(inherited=False), Path(self.temp.name) / "spotlight/history-v1.tsv")
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": "", "HOME": self.temp.name}):
            self.assertEqual(history.history_path(), Path(self.temp.name) / ".local/state/spotlight/history-v1.tsv")
        for value in (0, "0", 100, "005"):
            self.assertEqual(history.history_limit(value), int(value))
        for value in (True, -1, "-1", "1.0", " 5", "٥", 101, None):
            with self.assertRaises(ValueError):
                history.history_limit(value)

    def test_mru_trim_and_private_files(self):
        for number in (1, 2, 3, 2):
            history.record_history(row(number), 2)
        path = history.history_path()
        self.assertEqual(path.read_text().splitlines(), [row(2), row(3)])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(path.with_suffix(".lock").stat().st_mode & 0o777, 0o600)

    def test_disabled_does_not_create_state(self):
        history.record_history(row(1), 0)
        history.clear_history()
        self.assertFalse(history.history_path().parent.exists())

    def test_invalid_input_and_existing_rows(self):
        for invalid in ("", "a\tb\tc\td", row(1) + "\n", row(1) + "\textra", "v:unknown:a\tv:\tv:\tv:"):
            with self.assertRaises(ValueError):
                history.record_history(invalid, 5)
        history.record_history(row(1), 5)
        path = history.history_path()
        path.write_bytes(("broken\n" + row(1) + "\n" + row(1) + "\n").encode() + b"v:snippet:bad\tv:\tv:\tv:\xff\n")
        history.record_history(row(2), 5)
        self.assertEqual(path.read_text().splitlines(), [row(2), row(1)])
        neighbor = path.parent / "other"
        neighbor.write_text("keep")
        history.clear_history()
        self.assertFalse(path.exists())
        self.assertEqual(neighbor.read_text(), "keep")

    def test_cli_and_concurrent_writers(self):
        processes = []
        for number in range(12):
            process = subprocess.Popen([sys.executable, str(SCRIPT), "record", "100"], stdin=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            process.stdin.write(row(number) + "\n")
            process.stdin.close()
            processes.append(process)
        for process in processes:
            self.assertEqual(process.wait(), 0, process.stderr.read())
            process.stderr.close()
        self.assertEqual(set(history.history_path().read_text().splitlines()), {row(number) for number in range(12)})
        failed = subprocess.run([sys.executable, str(SCRIPT), "record", "5"], input=row(1) + "\n\n", text=True, capture_output=True)
        self.assertEqual(failed.returncode, 1)
        self.assertIn("spotlight history:", failed.stderr)


if __name__ == "__main__":
    unittest.main()
