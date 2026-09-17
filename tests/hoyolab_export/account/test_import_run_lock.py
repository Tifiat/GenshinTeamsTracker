"""Real OS locking in temporary files; no login or account access."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hoyolab_export.run_import import HoYoLABImportError, import_run_lock


class ImportRunLockTest(unittest.TestCase):
    def test_concurrent_process_is_rejected_and_release_allows_next_run(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "import.lock"
            code = (
                "from pathlib import Path; import sys\n"
                "from hoyolab_export.run_import import import_run_lock, HoYoLABImportError\n"
                "try:\n"
                " with import_run_lock(Path(sys.argv[1])): pass\n"
                "except HoYoLABImportError: sys.exit(2)\n"
            )
            def run():
                return subprocess.run([sys.executable, "-c", code, str(path)],
                                      capture_output=True, timeout=20).returncode
            with import_run_lock(path):
                self.assertEqual(run(), 2)
            self.assertEqual(run(), 0)

    def test_exception_releases_lock_without_deleting_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "import.lock"
            with self.assertRaisesRegex(RuntimeError, "fixture"):
                with import_run_lock(path):
                    raise RuntimeError("fixture")
            self.assertTrue(path.exists())
            with import_run_lock(path):
                pass
