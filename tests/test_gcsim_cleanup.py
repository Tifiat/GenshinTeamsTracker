from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from run_workspace.gcsim.cleanup import prune_gcsim_run_dirs


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


def _make_run_dir(path: Path, *, size: int, timestamp: int) -> Path:
    path.mkdir()
    (path / "result.json").write_bytes(b"x" * size)
    os.utime(path, (timestamp, timestamp))
    return path


if __name__ == "__main__":
    unittest.main()
