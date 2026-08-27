from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from run_workspace.gcsim.artifact_set_catalog import (
    GcsimArtifactSetCapability,
    GcsimArtifactSetCatalog,
)
from run_workspace.gcsim.optimizer_artifact_database import (
    evaluate_gcsim_optimizer_artifact_eligibility,
    load_gcsim_optimizer_artifact_database_input,
)
from run_workspace.gcsim.optimizer_engine_context import (
    GcsimOptimizerEngineContext,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimOptimizerFourStarEligibilityOverride,
    GcsimOptimizerWearerIdentity,
)


class GcsimOptimizerArtifactDatabaseTests(unittest.TestCase):
    def test_loads_every_row_readonly_and_keeps_row_failures_local(self) -> None:
        with _artifact_database() as path:
            journal_before = _journal_mode(path)
            real_connect = sqlite3.connect
            with patch(
                "run_workspace.gcsim.optimizer_artifact_database.sqlite3.connect",
                wraps=real_connect,
            ) as connect:
                first = load_gcsim_optimizer_artifact_database_input(
                    path,
                    engine_context=_engine_context(),
                )
            second = load_gcsim_optimizer_artifact_database_input(
                path,
                engine_context=_engine_context(),
            )

            self.assertTrue(first.ready)
            database_input = first.database_input
            assert database_input is not None
            self.assertEqual(
                tuple(item.artifact_id for item in database_input.artifacts),
                (1, 2, 3, 4, 5),
            )
            self.assertEqual(database_input.raw_substat_row_count, 2)
            self.assertEqual(
                database_input.eligible_5_star_artifact_ids,
                (1,),
            )
            self.assertEqual(
                database_input.artifact_by_id(1).substats,
                (),
            )
            self.assertTrue(database_input.artifact_by_id(3).calculation_valid)
            self.assertEqual(
                database_input.artifact_by_id(3).set_mapping_status,
                "unmapped",
            )
            self.assertFalse(database_input.artifact_by_id(4).calculation_valid)
            self.assertFalse(database_input.artifact_by_id(5).calculation_valid)
            issue_codes = {
                (issue.artifact_id, issue.code)
                for issue in database_input.issues
            }
            self.assertIn((3, "artifact_set_unmapped"), issue_codes)
            self.assertIn((4, "artifact_main_property_value_invalid"), issue_codes)
            self.assertIn((5, "artifact_substat_property_type_unmapped"), issue_codes)
            self.assertEqual(
                first.database_input.artifact_database_input_sha256,
                second.database_input.artifact_database_input_sha256,
            )
            args, kwargs = connect.call_args
            self.assertIn("mode=ro", args[0])
            self.assertTrue(kwargs["uri"])
            self.assertEqual(_journal_mode(path), journal_before)
            self.assertFalse(path.with_name(path.name + "-wal").exists())
            self.assertFalse(path.with_name(path.name + "-shm").exists())

    def test_membership_ignores_provenance_equipment_and_presets(self) -> None:
        with _artifact_database() as path:
            first = load_gcsim_optimizer_artifact_database_input(
                path,
                engine_context=_engine_context(),
            )
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    "UPDATE artifacts SET import_source = 'another-source' WHERE id = 1"
                )
                connection.execute(
                    "INSERT INTO artifact_equipment VALUES (2, 987654)"
                )
                connection.execute(
                    "INSERT INTO build_presets VALUES (42, 'ignored')"
                )
                connection.commit()
            finally:
                connection.close()
            second = load_gcsim_optimizer_artifact_database_input(
                path,
                engine_context=_engine_context(),
            )

            self.assertTrue(first.ready)
            self.assertTrue(second.ready)
            assert first.database_input is not None
            assert second.database_input is not None
            self.assertEqual(
                tuple(item.artifact_id for item in first.database_input.artifacts),
                tuple(item.artifact_id for item in second.database_input.artifacts),
            )
            self.assertNotEqual(
                first.database_input.artifact_database_input_sha256,
                second.database_input.artifact_database_input_sha256,
            )

    def test_four_star_authorization_is_scoped_to_wearer_and_package(self) -> None:
        wearer = GcsimOptimizerWearerIdentity(1, 1001, "chasca")
        other_wearer = GcsimOptimizerWearerIdentity(2, 1002, "ororon")
        with _artifact_database() as path:
            result = load_gcsim_optimizer_artifact_database_input(
                path,
                engine_context=_engine_context(),
            )
        assert result.database_input is not None
        four_star = result.database_input.artifact_by_id(2)
        assert four_star is not None
        by_set = GcsimOptimizerFourStarEligibilityOverride(
            wearer=wearer,
            allowed_set_uids=("KnownSet",),
        )
        by_id = GcsimOptimizerFourStarEligibilityOverride(
            wearer=wearer,
            allowed_artifact_ids=(2,),
        )

        self.assertFalse(
            evaluate_gcsim_optimizer_artifact_eligibility(
                four_star,
                wearer=wearer,
            ).eligible
        )
        self.assertFalse(
            evaluate_gcsim_optimizer_artifact_eligibility(
                four_star,
                wearer=other_wearer,
                four_star_override=by_id,
                package_set_uids=("KnownSet",),
            ).eligible
        )
        self.assertFalse(
            evaluate_gcsim_optimizer_artifact_eligibility(
                four_star,
                wearer=wearer,
                four_star_override=by_set,
                package_set_uids=("DifferentSet",),
            ).eligible
        )
        self.assertTrue(
            evaluate_gcsim_optimizer_artifact_eligibility(
                four_star,
                wearer=wearer,
                four_star_override=by_set,
                package_set_uids=("KnownSet",),
            ).eligible
        )
        self.assertTrue(
            evaluate_gcsim_optimizer_artifact_eligibility(
                four_star,
                wearer=wearer,
                four_star_override=by_id,
                package_set_uids=("DifferentSet",),
            ).eligible
        )

    def test_missing_database_is_not_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "missing.db"
            result = load_gcsim_optimizer_artifact_database_input(
                path,
                engine_context=_engine_context(),
            )

            self.assertFalse(result.ready)
            self.assertEqual(result.issues[0].code, "artifact_database_missing")
            self.assertFalse(path.exists())


class _artifact_database:
    def __enter__(self) -> Path:
        self._temp = tempfile.TemporaryDirectory()
        self.path = Path(self._temp.name) / "artifacts.db"
        connection = sqlite3.connect(self.path)
        try:
            connection.executescript(
                """
                PRAGMA journal_mode = DELETE;
                CREATE TABLE artifacts (
                    id INTEGER PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    content_fingerprint TEXT,
                    name TEXT NOT NULL,
                    set_uid TEXT,
                    pos INTEGER,
                    rarity INTEGER,
                    level INTEGER,
                    main_property_type INTEGER,
                    main_property_name TEXT,
                    main_property_value TEXT,
                    import_source TEXT,
                    import_format TEXT,
                    import_batch_id INTEGER,
                    json_imported INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE artifact_substats (
                    artifact_id INTEGER NOT NULL,
                    slot_index INTEGER NOT NULL,
                    property_type INTEGER,
                    property_name TEXT,
                    value TEXT,
                    times INTEGER,
                    PRIMARY KEY (artifact_id, slot_index)
                );
                CREATE TABLE artifact_equipment (
                    artifact_id INTEGER NOT NULL,
                    character_id INTEGER NOT NULL
                );
                CREATE TABLE build_presets (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
                );
                """
            )
            rows = (
                (1, "fp1", "cfp1", "Flower", "KnownSet", 1, 5, 20, 2, "HP", "4780", "artiscan", "json", 10, 1),
                (2, "fp2", "cfp2", "Plume", "KnownSet", 2, 4, 16, 5, "ATK", "232", "account", "api", 11, 0),
                (3, "fp3", "cfp3", "Old Flower", "UnknownSet", 1, 2, 4, 2, "HP", "430", "manual", "db", 12, 0),
                (4, "fp4", "cfp4", "Broken Main", "KnownSet", 3, 5, 20, 6, "ATK%", None, "account", "api", 13, 0),
                (5, "fp5", "cfp5", "Broken Sub", "KnownSet", 4, 5, 20, 44, "Anemo", "46.6%", "account", "api", 14, 0),
            )
            connection.executemany(
                """
                INSERT INTO artifacts (
                    id, fingerprint, content_fingerprint, name, set_uid, pos,
                    rarity, level, main_property_type, main_property_name,
                    main_property_value, import_source, import_format,
                    import_batch_id, json_imported
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            connection.executemany(
                """
                INSERT INTO artifact_substats (
                    artifact_id, slot_index, property_type, property_name,
                    value, times
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (2, 0, 20, "CRIT Rate", "3.1%", 1),
                    (5, 0, 999, "Unknown", "5.0", 1),
                ),
            )
            connection.execute(
                "INSERT INTO artifact_equipment VALUES (1, 123456)"
            )
            connection.execute(
                "INSERT INTO build_presets VALUES (1, 'ignored')"
            )
            connection.commit()
        finally:
            connection.close()
        return self.path

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._temp.cleanup()


def _journal_mode(path: Path) -> str:
    connection = sqlite3.connect(path)
    try:
        return str(connection.execute("PRAGMA journal_mode").fetchone()[0])
    finally:
        connection.close()


def _engine_context() -> GcsimOptimizerEngineContext:
    capability = GcsimArtifactSetCapability(
        key="knownset",
        package_name="knownset",
        key_constant="KnownSet",
        max_rarity=5,
        registered=True,
        has_two_piece_code=True,
        has_four_piece_code=True,
        two_piece_modeled=True,
        four_piece_modeled=True,
    )
    catalog = GcsimArtifactSetCatalog(
        source_root="test",
        source_fingerprint="5" * 64,
        sets=(capability,),
    )
    return GcsimOptimizerEngineContext(
        engine_id="test-engine",
        engine_root="test",
        engine_version="test-version",
        optimizer_contract_version="test-contract",
        artifact_path="gcsim",
        artifact_sha256="2" * 64,
        engine_tree_sha256="3" * 64,
        catalog=catalog,
        manifest_artifact_sha256="2" * 64,
        manifest_engine_tree_sha256="3" * 64,
        binding_sha256="4" * 64,
        trusted=True,
    )


if __name__ == "__main__":
    unittest.main()
