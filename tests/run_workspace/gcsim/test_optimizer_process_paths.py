from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

from run_workspace.gcsim.optimizer_go_selected import (
    GcsimOptimizerGoSelectedRequest, GcsimOptimizerGoSelectedSession,
)
from run_workspace.gcsim.optimizer_process_paths import (
    optimizer_process_workdir, windows_current_directory_units,
)


class OptimizerProcessPathTests(unittest.TestCase):
    def test_utf16_boundary_counts_separator_nul_and_surrogate_pairs(self):
        self.assertEqual(windows_current_directory_units("a" * 258), 260)
        self.assertEqual(windows_current_directory_units("a" * 259), 261)
        self.assertEqual(windows_current_directory_units("é" * 258), 260)
        self.assertEqual(windows_current_directory_units("a" * 256 + "😀"), 260)
        self.assertEqual(windows_current_directory_units("C:\\"), 4)

    def test_short_directory_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            if os.name == "nt" and windows_current_directory_units(str(directory)) > 260:
                self.skipTest("Temporary base already exceeds the Windows cwd limit")
            self.assertEqual(optimizer_process_workdir(directory), str(directory))

    @unittest.skipUnless(os.name == "nt", "Windows process cwd restriction")
    def test_missing_directory_is_not_hidden_by_ancestor_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(NotADirectoryError):
                optimizer_process_workdir(Path(temporary) / "not-created")

    @unittest.skipUnless(os.name == "nt", "Windows process cwd restriction")
    def test_actual_selected_capture_launcher_handles_long_cwd(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / ("a" * 80) / ("b" * 80) / ("c" * 80)
            directory.mkdir(parents=True)
            self.assertGreater(windows_current_directory_units(str(directory)), 260)
            stdout, stderr = directory / "stdout.txt", directory / "stderr.txt"
            session = GcsimOptimizerGoSelectedSession(
                GcsimOptimizerGoSelectedRequest("unused", {}, 0, "")
            )
            # Exercise the real production Popen site, never a process/result mock.
            session._run_process(
                (sys.executable, "-c", "import os; print(os.getcwd())"),
                cwd=directory, timeout_ms=15_000,
                stdout_path=stdout, stderr_path=stderr,
            )
            actual = Path(stdout.read_text(encoding="utf-8").strip())
            self.assertEqual(actual, Path(optimizer_process_workdir(directory)))
            self.assertTrue(actual in directory.parents)
            self.assertEqual(stderr.read_text(encoding="utf-8"), "")
            self.assertTrue(stdout.is_file())


if __name__ == "__main__":
    unittest.main()
