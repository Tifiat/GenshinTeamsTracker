"""N0 lifecycle tests: real tiny child commands, no engine or account access."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.managed_optimizer_experiment import managed_scratch, run_experiment
from run_workspace.gcsim.runtime_probe import _go_sandbox_env


class ManagedOptimizerExperimentTest(unittest.TestCase):
    def test_success_error_and_cancellation_remove_owned_output_only(self):
        for error in (None, ValueError, KeyboardInterrupt):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "managed"
                sibling = Path(tmp) / "evidence.txt"
                sibling.write_text("keep")
                try:
                    with managed_scratch(root) as job:
                        (job / "large.bin").write_bytes(b"x" * 256)
                        if error:
                            raise error()
                except (ValueError, KeyboardInterrupt):
                    pass
                self.assertFalse(job.exists())
                self.assertTrue(sibling.exists())

    def test_real_children_share_scratch_and_go_cache_even_through_build_helper(self):
        for code in (0, 3):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "managed"
                child = (
                    "import os,sys; from pathlib import Path; "
                    "from run_workspace.gcsim.runtime_probe import _go_sandbox_env; "
                    "p=Path(sys.argv[1]); assert str(p)==os.environ['GTT_SCRATCH_DIR']; "
                    "e=_go_sandbox_env(p/'modules'); "
                    "assert e['GOCACHE']==os.environ['GOCACHE']; "
                    "(p/'output').write_text('generated'); "
                    f"sys.exit({code})"
                )
                result = run_experiment([sys.executable, "-c", child, "{scratch}"], timeout=15, root=root)
                self.assertEqual(result, code)
                self.assertFalse(list(root.glob("job-*")))

    def test_timeout_stops_child_and_cleans(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "managed"
            with self.assertRaises(subprocess.TimeoutExpired):
                run_experiment([sys.executable, "-c", "import time; time.sleep(10)"], timeout=.1, root=root)
            self.assertFalse(list(root.glob("job-*")))

    def test_active_scope_cannot_be_reentered_or_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with managed_scratch(root) as job:
                with self.assertRaises(OSError):
                    with managed_scratch(root):
                        self.fail("Concurrent workspace allocated")
                self.assertTrue(job.exists())

    def test_failure_or_crash_leftovers_block_growth_not_blindly_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("tools.managed_optimizer_experiment.shutil.rmtree", side_effect=PermissionError("busy")):
                with self.assertWarns(RuntimeWarning), self.assertRaises(PermissionError):
                    with managed_scratch(root) as job:
                        pass
            self.assertTrue(job.exists())
            with self.assertRaisesRegex(RuntimeError, "Unfinished scratch"):
                with managed_scratch(root):
                    self.fail("Allocated another job despite residue")

    def test_nested_link_is_preserved_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, outside = Path(tmp) / "managed", Path(tmp) / "outside"
            outside.mkdir()
            (outside / "precious").write_text("keep")
            try:
                with self.assertWarns(RuntimeWarning), self.assertRaises(ValueError):
                    with managed_scratch(root) as job:
                        link = job / "link"
                        try:
                            link.symlink_to(outside, target_is_directory=True)
                        except OSError:
                            if sys.platform != "win32":
                                self.skipTest("Symlink creation unavailable")
                            # Windows junction creation needs no symlink privilege.
                            # No deletion or shell-to-shell path passing here.
                            env = dict(os.environ, GTT_TEST_LINK=str(link), GTT_TEST_TARGET=str(outside))
                            subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                                            "New-Item -ItemType Junction -Path $env:GTT_TEST_LINK -Target $env:GTT_TEST_TARGET | Out-Null"],
                                           env=env, check=True, capture_output=True)
                self.assertTrue((outside / "precious").exists())
            finally:
                if 'link' in locals() and link.exists():
                    if link.is_symlink():
                        link.unlink()
                    else:
                        link.rmdir()  # remove the test junction itself, not target

    def test_ordinary_go_cache_unchanged_without_managed_environment(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            root = Path(tmp)
            self.assertEqual(_go_sandbox_env(root)["GOCACHE"], str(root / "build-cache"))


if __name__ == "__main__":
    unittest.main()
