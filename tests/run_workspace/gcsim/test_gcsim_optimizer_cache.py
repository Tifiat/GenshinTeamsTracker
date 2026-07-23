from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from run_workspace.gcsim.optimizer_cache import (
    GcsimOptimizerCacheError,
    GcsimOptimizerCacheIdentity,
    GcsimOptimizerCacheStore,
    build_gcsim_optimizer_cache_identity,
    build_gcsim_optimizer_cache_identity_from_sha256,
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


if __name__ == "__main__":
    unittest.main()
