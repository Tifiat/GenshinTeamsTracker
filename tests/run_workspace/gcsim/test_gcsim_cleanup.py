from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from run_workspace.gcsim.cleanup import (
    cleanup_gcsim_local_state,
    prune_gcsim_run_dirs,
)


class GcsimCleanupTest(unittest.TestCase):
    def test_prune_run_dirs_keeps_newest_with_count_and_size_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs"
            root.mkdir()
            old = _make_run_dir(root / "old", size=10, timestamp=100)
            mid = _make_run_dir(root / "mid", size=10, timestamp=200)
            new = _make_run_dir(root / "new", size=10, timestamp=300)

            dry_run = prune_gcsim_run_dirs(
                run_root=root,
                keep_count=2,
                max_total_bytes=100,
                dry_run=True,
            )
            self.assertIn(str(old), dry_run.deleted_paths)
            self.assertTrue(old.exists())

            result = prune_gcsim_run_dirs(
                run_root=root,
                keep_count=2,
                max_total_bytes=100,
            )

            self.assertEqual(result.status, "pruned")
            self.assertIn(str(old), result.deleted_paths)
            self.assertFalse(old.exists())
            self.assertTrue(mid.exists())
            self.assertTrue(new.exists())

    def test_prune_run_dirs_keeps_latest_even_when_size_limit_is_tiny(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs"
            root.mkdir()
            old = _make_run_dir(root / "old", size=10, timestamp=100)
            new = _make_run_dir(root / "new", size=10, timestamp=200)

            result = prune_gcsim_run_dirs(
                run_root=root,
                keep_count=5,
                max_total_bytes=1,
            )

            self.assertFalse(old.exists())
            self.assertTrue(new.exists())
            self.assertEqual(result.kept_paths, (str(new),))

    def test_local_cleanup_covers_all_three_generated_run_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ordinary = root / "runs"
            farming = root / "farming-runs"
            optimizer = root / "optimizer-runs"
            optimizer_cache = root / "optimizer-cache"
            for run_root in (ordinary, farming, optimizer):
                run_root.mkdir()
                _make_run_dir(run_root / "old", size=10, timestamp=100)
                _make_run_dir(run_root / "new", size=10, timestamp=200)
            optimizer_cache.mkdir()
            old_cache = _make_cache_entry(
                optimizer_cache / "old.json", size=10, timestamp=100
            )
            _make_cache_entry(
                optimizer_cache / "new.json", size=10, timestamp=200
            )

            report = cleanup_gcsim_local_state(
                dry_run=True,
                store_dir=root / "engines",
                clean_go_cache=False,
                run_root=ordinary,
                farming_run_root=farming,
                optimizer_run_root=optimizer,
                keep_run_dirs=1,
                keep_farming_run_dirs=1,
                keep_optimizer_run_dirs=1,
                optimizer_cache_root=optimizer_cache,
                keep_optimizer_cache_entries=1,
            )

            self.assertEqual(len(report.run_dirs["deleted_paths"]), 1)
            self.assertEqual(len(report.farming_run_dirs["deleted_paths"]), 1)
            self.assertEqual(len(report.optimizer_run_dirs["deleted_paths"]), 1)
            self.assertEqual(len(report.optimizer_cache["deleted_paths"]), 1)
            self.assertTrue((ordinary / "old").exists())
            self.assertTrue((farming / "old").exists())
            self.assertTrue((optimizer / "old").exists())
            self.assertTrue(old_cache.exists())


def _make_run_dir(path: Path, *, size: int, timestamp: int) -> Path:
    path.mkdir()
    (path / "result.json").write_bytes(b"x" * size)
    os.utime(path, (timestamp, timestamp))
    return path


def _make_cache_entry(path: Path, *, size: int, timestamp: int) -> Path:
    path.write_bytes(b"x" * size)
    os.utime(path, (timestamp, timestamp))
    return path


if __name__ == "__main__":
    unittest.main()
