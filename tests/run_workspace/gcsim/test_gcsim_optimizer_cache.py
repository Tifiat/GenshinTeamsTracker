from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from run_workspace.gcsim.optimizer_cache import (
    GcsimOptimizerCacheError,
    GcsimOptimizerCacheIdentity,
    GcsimOptimizerCacheStore,
    build_gcsim_optimizer_cache_identity,
    build_gcsim_optimizer_cache_identity_from_sha256,
    prune_gcsim_optimizer_cache,
)


class GcsimOptimizerCacheTest(unittest.TestCase):
    def test_identity_hashes_actual_engine_and_canonical_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = root / "gtt-gcsim.exe"
            engine.write_bytes(b"engine-v1")

            left = build_gcsim_optimizer_cache_identity(
                engine_path=engine,
                engine_version="abc",
                source_config_text="config",
                mode="substat",
                optimizer_options={"fine_tune": 1, "total": 20},
            )
            right = build_gcsim_optimizer_cache_identity(
                engine_path=engine,
                engine_version="abc",
                source_config_text="config",
                mode="substat",
                optimizer_options=(("total", 20), ("fine_tune", 1)),
            )

            self.assertEqual(left, right)
            self.assertEqual(left.cache_key, right.cache_key)
            self.assertEqual(len(left.engine_sha256), 64)
            frozen = build_gcsim_optimizer_cache_identity_from_sha256(
                engine_sha256=left.engine_sha256,
                engine_version="abc",
                source_config_text="config",
                mode="substat",
                optimizer_options={"fine_tune": 1, "total": 20},
            )
            self.assertEqual(left, frozen)

    def test_store_round_trips_only_matching_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = GcsimOptimizerCacheStore(root)
            identity = GcsimOptimizerCacheIdentity(
                engine_sha256="a" * 64,
                engine_version="v1",
                source_config_sha256="b" * 64,
                mode="farming_4p",
                candidate_key="candidate-a",
            )

            path = store.put(identity, {"status": "passed", "dps": 123.5})

            self.assertEqual(store.get(identity), {"status": "passed", "dps": 123.5})
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["identity"]["candidate_key"] = "tampered"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIsNone(store.get(identity))

    def test_changed_config_or_engine_changes_cache_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = root / "gtt-gcsim.exe"
            engine.write_bytes(b"one")
            first = build_gcsim_optimizer_cache_identity(
                engine_path=engine,
                engine_version="v1",
                source_config_text="config-a",
                mode="substat",
            )
            engine.write_bytes(b"two")
            second = build_gcsim_optimizer_cache_identity(
                engine_path=engine,
                engine_version="v1",
                source_config_text="config-a",
                mode="substat",
            )
            third = build_gcsim_optimizer_cache_identity(
                engine_path=engine,
                engine_version="v1",
                source_config_text="config-b",
                mode="substat",
            )

            self.assertNotEqual(first.cache_key, second.cache_key)
            self.assertNotEqual(second.cache_key, third.cache_key)

    def test_corrupt_identity_is_a_cache_miss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = GcsimOptimizerCacheStore(root)
            identity = GcsimOptimizerCacheIdentity(
                engine_sha256="a" * 64,
                engine_version="v1",
                source_config_sha256="b" * 64,
                mode="farming_4p",
            )
            path = store.put(identity, {"status": "passed"})
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["identity"]["schema_version"] = "invalid"
            path.write_text(json.dumps(payload), encoding="utf-8")

            self.assertIsNone(store.get(identity))

    def test_non_json_result_fails_without_leaving_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = GcsimOptimizerCacheStore(root)
            identity = GcsimOptimizerCacheIdentity(
                engine_sha256="a" * 64,
                engine_version="v1",
                source_config_sha256="b" * 64,
                mode="farming_4p",
            )

            with self.assertRaises(GcsimOptimizerCacheError):
                store.put(identity, {"bad": object()})

            self.assertEqual(tuple(root.glob("*.tmp")), ())

    def test_prune_bounds_entry_count_and_total_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = GcsimOptimizerCacheStore(root, auto_prune=False)
            paths = []
            for index in range(3):
                path = store.put(
                    _identity(f"candidate-{index}"),
                    {"status": "passed", "padding": "x" * (index + 1)},
                )
                os.utime(path, (100 + index, 100 + index))
                paths.append(path)

            dry_run = prune_gcsim_optimizer_cache(
                cache_root=root,
                max_entries=2,
                max_total_bytes=1024 * 1024,
                dry_run=True,
            )
            self.assertEqual(dry_run.kept_count, 2)
            self.assertEqual(dry_run.deleted_paths, (str(paths[0]),))
            self.assertTrue(paths[0].exists())

            newest_size = paths[2].stat().st_size
            result = prune_gcsim_optimizer_cache(
                cache_root=root,
                max_entries=3,
                max_total_bytes=newest_size,
            )
            self.assertEqual(result.kept_count, 1)
            self.assertTrue(paths[2].exists())
            self.assertFalse(paths[0].exists())
            self.assertFalse(paths[1].exists())

    def test_put_auto_prunes_but_throttles_full_scans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = GcsimOptimizerCacheStore(
                root,
                max_entries=1,
                max_bytes=1024 * 1024,
                prune_interval_seconds=60,
            )
            target = "run_workspace.gcsim.optimizer_cache.prune_gcsim_optimizer_cache"
            with patch(target, wraps=prune_gcsim_optimizer_cache) as prune:
                first = store.put(_identity("first"), {"status": "passed"})
                second = store.put(_identity("second"), {"status": "passed"})

            self.assertEqual(prune.call_count, 1)
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())

    def test_put_auto_prune_enforces_configured_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = GcsimOptimizerCacheStore(
                root,
                max_entries=1,
                max_bytes=1024 * 1024,
                prune_interval_seconds=0,
            )
            first = store.put(_identity("first"), {"status": "passed"})
            os.utime(first, (100, 100))

            second = store.put(_identity("second"), {"status": "passed"})

            self.assertFalse(first.exists())
            self.assertTrue(second.exists())

    def test_prune_removes_only_stale_orphan_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stale = root / ".stale.json.token.tmp"
            live = root / ".live.json.token.tmp"
            stale.write_bytes(b"stale")
            live.write_bytes(b"live")
            os.utime(stale, (100, 100))

            result = prune_gcsim_optimizer_cache(
                cache_root=root,
                stale_temp_seconds=60,
            )

            self.assertIn(str(stale), result.deleted_paths)
            self.assertFalse(stale.exists())
            self.assertTrue(live.exists())


def _identity(candidate_key: str) -> GcsimOptimizerCacheIdentity:
    return GcsimOptimizerCacheIdentity(
        engine_sha256="a" * 64,
        engine_version="v1",
        source_config_sha256="b" * 64,
        mode="farming_4p",
        candidate_key=candidate_key,
    )


if __name__ == "__main__":
    unittest.main()
