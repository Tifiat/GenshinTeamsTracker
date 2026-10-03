from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from run_workspace.gcsim.artifact_set_catalog import (
    GcsimArtifactSetCapability,
    GcsimArtifactSetCatalog,
)
from run_workspace.gcsim.optimizer_artifact_database import (
    GcsimOptimizerArtifactDatabaseInput,
    GcsimOptimizerArtifactRecord,
    load_gcsim_optimizer_artifact_database_input,
)
from run_workspace.gcsim.optimizer_artifact_materializer import (
    materialize_gcsim_optimizer_artifact_stat_vector,
)
from run_workspace.gcsim.optimizer_go_selected_inputs import (
    enforce_gcsim_optimizer_mvp_energy_policy,
    selected_set_requirements,
    GcsimOptimizerGoSelectedInputError,
    SelectedEquippedTeamSnapshot,
    SelectedEquippedWearer,
    SelectedBoundWearerInput,
    bind_selected_report_config_and_snapshot,
    load_selected_equipped_team_snapshot,
    selected_virtual_inventory_baseline_summaries,
    selected_team_with_equipped_snapshot_artifacts,
)
from run_workspace.gcsim.optimizer_engine_context import (
    GcsimOptimizerEngineContext,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimOptimizerWearerArtifactAssignment,
    GcsimOptimizerWearerIdentity,
)
from run_workspace.gcsim.optimizer_go_selected import _request_wearers
from run_workspace.team_builder import TeamBuilderTeamState


ROOT = Path(__file__).resolve().parents[3]


def _selected_snapshot_engine_context() -> GcsimOptimizerEngineContext:
    capabilities = tuple(
        GcsimArtifactSetCapability(
            key=set_uid,
            package_name=set_uid,
            key_constant=set_uid,
            max_rarity=5,
            registered=True,
            has_two_piece_code=True,
            has_four_piece_code=True,
            two_piece_modeled=True,
            four_piece_modeled=True,
        )
        for set_uid in ("set_a", "set_b", "set_c", "set_d")
    )
    catalog = GcsimArtifactSetCatalog(
        source_root="selected-snapshot-test",
        source_fingerprint="5" * 64,
        sets=capabilities,
    )
    return GcsimOptimizerEngineContext(
        engine_id="selected-snapshot-test",
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


def _create_selected_snapshot_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE artifacts (
                id INTEGER PRIMARY KEY,
                set_uid TEXT NOT NULL,
                pos INTEGER NOT NULL,
                rarity INTEGER NOT NULL,
                level INTEGER NOT NULL,
                main_property_type INTEGER NOT NULL,
                main_property_name TEXT NOT NULL,
                main_property_value TEXT NOT NULL
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
            CREATE TABLE account_characters (
                character_id INTEGER PRIMARY KEY,
                gcsim_character_key TEXT NOT NULL
            );
            CREATE TABLE account_character_equipped_artifacts (
                character_id INTEGER NOT NULL,
                slot_key TEXT NOT NULL,
                artifact_id INTEGER NOT NULL
            );
            """
        )
        main_stats = {
            1: (2, "HP", "4780"),
            2: (5, "ATK", "311"),
            3: (6, "ATK%", "46.6%"),
            4: (40, "Pyro DMG", "46.6%"),
            5: (20, "CRIT Rate", "31.1%"),
        }
        artifact_rows = []
        equipment_rows = []
        slots = GCSIM_OPTIMIZER_ARTIFACT_SLOTS
        for team_slot in range(1, 5):
            character_id = 100 + team_slot
            character_key = f"actor{team_slot}"
            connection.execute(
                "INSERT INTO account_characters VALUES (?, ?)",
                (character_id, character_key),
            )
            for position, slot_key in enumerate(slots, start=1):
                artifact_id = (team_slot - 1) * 5 + position
                if team_slot == 1:
                    set_uid = (
                        "set_a" if position <= 2 else
                        "set_b" if position <= 4 else
                        "set_c"
                    )
                else:
                    set_uid = f"set_{'abcd'[team_slot - 1]}"
                property_type, property_name, property_value = main_stats[position]
                artifact_rows.append(
                    (
                        artifact_id,
                        set_uid,
                        position,
                        5,
                        20,
                        property_type,
                        property_name,
                        property_value,
                    )
                )
                equipment_rows.append((character_id, slot_key, artifact_id))
        connection.executemany(
            "INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            artifact_rows,
        )
        connection.executemany(
            "INSERT INTO account_character_equipped_artifacts VALUES (?, ?, ?)",
            equipment_rows,
        )
        connection.commit()
    finally:
        connection.close()


class GoSelectedInputBoundaryTests(unittest.TestCase):
    @staticmethod
    def _snapshot_fixture():
        main_stats = (
            (2, "HP", "4780", 4780.0),
            (5, "ATK", "311", 311.0),
            (6, "ATK%", "46.6%", 46.6),
            (40, "Pyro DMG", "46.6%", 46.6),
            (20, "CRIT Rate", "31.1%", 31.1),
        )
        artifacts = []
        for team_slot in range(1, 5):
            for position, slot in enumerate(GCSIM_OPTIMIZER_ARTIFACT_SLOTS, start=1):
                artifact_id = (team_slot - 1) * 5 + position
                if team_slot == 1:
                    set_uid = "set_a" if position <= 2 else "set_b" if position <= 4 else "set_c"
                else:
                    set_uid = f"set_{team_slot}"
                stat_type, stat_name, raw_value, numeric_value = main_stats[position - 1]
                artifacts.append(
                    GcsimOptimizerArtifactRecord(
                        artifact_id=artifact_id,
                        set_uid=set_uid,
                        gcsim_set_key=set_uid,
                        set_mapping_status="ready",
                        position=position,
                        position_key=slot,
                        rarity=5,
                        level=20,
                        main_property_type=stat_type,
                        main_property_name=stat_name,
                        main_property_value=raw_value,
                        main_numeric_value=numeric_value,
                        substats=(),
                        calculation_valid=True,
                        default_eligible=True,
                        issues=(),
                        raw_columns=(("set_name", set_uid),),
                    )
                )
        database = GcsimOptimizerArtifactDatabaseInput(
            database_path="memory",
            artifact_database_input_sha256="a" * 64,
            engine_binding_sha256="b" * 64,
            catalog_fingerprint="c" * 64,
            artifact_columns=(),
            substat_columns=(),
            artifacts=tuple(artifacts),
            raw_substat_row_count=0,
            issues=(),
        )
        wearers = []
        for team_slot in range(1, 5):
            actor = f"actor{team_slot}"
            account_character_id = 99 + team_slot if team_slot < 4 else None
            wearer = GcsimOptimizerWearerIdentity(
                team_slot=team_slot,
                account_character_id=account_character_id,
                gcsim_character_key=actor,
            )
            ids_by_slot = {
                slot: (team_slot - 1) * 5 + position
                for position, slot in enumerate(GCSIM_OPTIMIZER_ARTIFACT_SLOTS, start=1)
            }
            assignment = GcsimOptimizerWearerArtifactAssignment(
                wearer=wearer,
                artifact_ids_by_slot=ids_by_slot,
            )
            counts = {}
            for artifact_id in assignment.artifact_ids:
                artifact = database.artifact_by_id(artifact_id)
                counts[artifact.set_uid] = counts.get(artifact.set_uid, 0) + 1
            set_counts = tuple(sorted(counts.items()))
            wearers.append(
                SelectedEquippedWearer(
                    wearer=wearer,
                    assignment=assignment,
                    target_sets=selected_set_requirements(set_counts),
                    set_counts=set_counts,
                )
            )
        snapshot = SelectedEquippedTeamSnapshot(
            artifact_database_input_sha256=database.artifact_database_input_sha256,
            equipment_rows_sha256="d" * 64,
            character_keys=tuple(f"actor{index}" for index in range(1, 5)),
            wearers=tuple(wearers),
        )
        return database, snapshot

    def test_stale_ui_artifact_ids_are_rejected_before_materializing(self) -> None:
        # Diagnostic for the 2026-09-26 Chasca startup failure. The guard is
        # correct; callers must supply one consistent equipment snapshot.
        slots = ("flower", "plume", "sands", "goblet", "circlet")
        snapshot = SimpleNamespace(wearers=(SimpleNamespace(
            wearer=SimpleNamespace(gcsim_character_key="chasca"),
            assignment=SimpleNamespace(artifact_ids_by_slot=dict(zip(slots, range(1, 6)))),
        ),))
        payload = {"characters": [{"mapping": {"gcsim_key": "chasca"}, "artifact_build": {
            "artifact_ids_by_pos": {str(i): (6 if i == 1 else i) for i in range(1, 6)},
        }}]}
        with patch("run_workspace.gcsim.optimizer_go_selected_inputs.materialize_gcsim_optimizer_artifact_stat_vector") as materialize:
            with self.assertRaisesRegex(GcsimOptimizerGoSelectedInputError, "prepared config artifact IDs differ for chasca") as caught:
                bind_selected_report_config_and_snapshot(payload, config_text="", artifact_database=None, snapshot=snapshot)
            materialize.assert_not_called()
            self.assertIn("prepared=(6, 2, 3, 4, 5)", str(caught.exception))
            self.assertIn("snapshot=(1, 2, 3, 4, 5)", str(caught.exception))

    def test_snapshot_rejects_in_place_stat_or_set_edits_after_inventory_load(self) -> None:
        for column, value in (
            ("main_property_value", "4790"),
            ("set_uid", "set_d"),
        ):
            with self.subTest(column=column), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "artifacts.db"
                _create_selected_snapshot_database(path)
                loaded = load_gcsim_optimizer_artifact_database_input(
                    path,
                    engine_context=_selected_snapshot_engine_context(),
                )
                self.assertTrue(loaded.ready)
                database = loaded.database_input
                assert database is not None
                artifact_ids_before = tuple(
                    row.artifact_id for row in database.artifacts
                )

                writer = sqlite3.connect(path)
                try:
                    writer.execute(
                        f"UPDATE artifacts SET {column} = ? WHERE id = 1",
                        (value,),
                    )
                    writer.commit()
                finally:
                    writer.close()

                self.assertEqual(
                    tuple(row.artifact_id for row in database.artifacts),
                    artifact_ids_before,
                )
                with self.assertRaisesRegex(
                    GcsimOptimizerGoSelectedInputError,
                    "artifact inventory changed between optimizer input loading",
                ):
                    load_selected_equipped_team_snapshot(
                        path,
                        artifact_database=database,
                        character_keys=("actor1", "actor2", "actor3", "actor4"),
                    )

    def test_unchanged_snapshot_and_virtual_baseline_use_frozen_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifacts.db"
            _create_selected_snapshot_database(path)
            loaded = load_gcsim_optimizer_artifact_database_input(
                path,
                engine_context=_selected_snapshot_engine_context(),
            )
            self.assertTrue(loaded.ready)
            database = loaded.database_input
            assert database is not None

            snapshot = load_selected_equipped_team_snapshot(
                path,
                artifact_database=database,
                character_keys=("actor1", "actor2", "actor3", "actor4"),
                virtual_character_keys=("actor4",),
            )
            self.assertEqual(
                snapshot.artifact_database_input_sha256,
                database.artifact_database_input_sha256,
            )
            self.assertEqual(
                snapshot.wearers[0].set_counts,
                (("set_a", 2), ("set_b", 2), ("set_c", 1)),
            )

            writer = sqlite3.connect(path)
            try:
                writer.execute(
                    "UPDATE artifacts SET main_property_value = '9999', "
                    "set_uid = 'set_a' WHERE id = 16"
                )
                writer.commit()
            finally:
                writer.close()

            summaries = selected_virtual_inventory_baseline_summaries(
                database,
                snapshot=snapshot,
            )
            self.assertEqual(tuple(summaries), ("actor4",))
            self.assertEqual(
                summaries["actor4"]["artifact_ids_by_pos"],
                {str(index): 15 + index for index in range(1, 6)},
            )
            self.assertEqual(
                {row["set_uid"]: row["count"] for row in summaries["actor4"]["set_counts"]},
                {"set_d": 5},
            )
            self.assertEqual(
                next(
                    row["raw_value"]
                    for row in summaries["actor4"]["total_stats"]
                    if row["property_type"] == 2
                ),
                4780.0,
            )

    def test_preparation_prefers_ui_snapshot_over_fresh_database_equipment(self) -> None:
        # Records the second input source, not a claim that the user's old UI
        # contents survived in the failed log. No real database is opened.
        from run_workspace.gcsim.selected_team_config import _selected_artifact_payload

        summary = {"artifact_ids_by_pos": {"1": 6}}
        slot = {"slot_index": 0, "character_details_data": {
            "stat_snapshot": {"artifact": {"summary": summary}},
        }}
        with patch("run_workspace.gcsim.selected_team_config._artifact_payload_from_snapshot", return_value=(None, {}, (), ())) as from_ui, patch(
            "run_workspace.gcsim.selected_team_config._current_artifact_payload_from_account_rows"
        ) as from_db:
            _selected_artifact_payload(None, slot, character_id="10000104", artifact_set_resolver=None)
            self.assertEqual(from_ui.call_args.args[0], summary)
            from_db.assert_not_called()

    def test_frozen_equipment_replaces_only_physical_ui_artifacts_and_binds_2_plus_2(self) -> None:
        database, snapshot = self._snapshot_fixture()
        stale_summary = {
            "artifact_ids_by_pos": {str(index): 900 + index for index in range(1, 6)},
            "total_stats": [{"property_type": 20, "property_name": "CRIT Rate", "raw_value": 999}],
        }
        virtual_profile = {
            "character": {"gcsim_key": "actor_4"},
            "artifact_build_id": 42,
            "artifact_build": {"explicit_profile": True},
        }
        selected_team = {
            "slots": [
                {
                    "slot_index": 0,
                    "character": {"id": "100"},
                    "gcsim_virtual_override": {},
                    "character_details_data": {
                        "account_character": {
                            "character_id": "100",
                            "id": "101",
                            "project_character_id": "102",
                        },
                        "stat_snapshot": {
                            "artifact": {"summary": stale_summary, "capture_note": "retain"},
                            "weapon": {"level": 90},
                        },
                        "artifact_build_snapshot": {"older_summary": True},
                        "unrelated_details": {"keep": True},
                    },
                },
                {"slot_index": 1, "character": {"id": "101"}},
                {"slot_index": 2, "character": {"id": "102"}},
                {"slot_index": 3, "gcsim_virtual_override": virtual_profile},
            ]
        }

        prepared_team = selected_team_with_equipped_snapshot_artifacts(
            selected_team,
            artifact_database=database,
            snapshot=snapshot,
        )
        prepared_slot = prepared_team["slots"][0]
        summary = prepared_slot["character_details_data"]["stat_snapshot"]["artifact"]["summary"]
        self.assertEqual(
            summary["artifact_ids_by_pos"],
            {str(index): index for index in range(1, 6)},
        )
        self.assertEqual(
            {row["set_uid"]: row["count"] for row in summary["set_counts"]},
            {"set_a": 2, "set_b": 2, "set_c": 1},
        )
        self.assertEqual(
            prepared_slot["character_details_data"]["stat_snapshot"]["artifact"]["capture_note"],
            "retain",
        )
        self.assertEqual(
            prepared_slot["character_details_data"]["stat_snapshot"]["weapon"],
            {"level": 90},
        )
        self.assertEqual(
            prepared_slot["character_details_data"]["artifact_build_snapshot"],
            {"older_summary": True},
        )
        self.assertEqual(
            prepared_slot["character_details_data"]["unrelated_details"],
            {"keep": True},
        )
        self.assertEqual(selected_team["slots"][0]["character_details_data"]["stat_snapshot"]["artifact"]["summary"], stale_summary)
        self.assertEqual(prepared_team["slots"][3]["gcsim_virtual_override"], virtual_profile)

        wearer = snapshot.wearers[0]
        config_totals = {}
        for artifact_id in wearer.assignment.artifact_ids:
            artifact = database.artifact_by_id(artifact_id)
            vector = materialize_gcsim_optimizer_artifact_stat_vector(
                artifact,
                wearer=wearer.wearer,
            )
            self.assertTrue(vector.ready)
            for stat_key, value in vector.stat_vector.normalized_stats:
                config_totals[stat_key] = config_totals.get(stat_key, 0.0) + float(value)
        config_lines = [
                "actor1 add stats "
            + " ".join(f"{key}={value:g}" for key, value in sorted(config_totals.items()))
            + ";"
        ]
        config_lines.extend(
            f'actor1 add set="{row["set_uid"]}" count={row["count"]};'
            for row in summary["set_counts"]
            if row["count"] >= 2
        )
        prepared_character = {
            "mapping": {"gcsim_key": "actor1"},
            "artifact_build": {
                "artifact_ids_by_pos": summary["artifact_ids_by_pos"],
                "set_counts": [
                    {"mapping": {"gcsim_key": row["set_uid"]}, "count": row["count"]}
                    for row in summary["set_counts"]
                ],
            },
        }
        bound = bind_selected_report_config_and_snapshot(
            {"characters": [prepared_character]},
            config_text="\n".join(config_lines),
            artifact_database=database,
            snapshot=SimpleNamespace(wearers=(wearer,)),
        )
        self.assertEqual(bound[0].artifact_ids, wearer.assignment.artifact_ids)
        self.assertEqual(bound[0].active_sets, (("set_a", 2), ("set_b", 2)))

    def test_team_builder_state_copy_keeps_slot_index_and_uses_current_ids(self) -> None:
        database, snapshot = self._snapshot_fixture()
        team = TeamBuilderTeamState.empty().set_character(
            0, {"id": "100", "name": "account character"}
        )
        team = team.attach_character_details_data(
            0,
            {
                "account_character": {"character_id": "100"},
                "stat_snapshot": {
                    "artifact": {
                        "summary": {
                            "artifact_ids_by_pos": {
                                str(index): 800 + index for index in range(1, 6)
                            }
                        }
                    }
                },
            },
        )
        copied = selected_team_with_equipped_snapshot_artifacts(
            team,
            artifact_database=database,
            snapshot=snapshot,
        )
        self.assertEqual(copied["slots"][0]["slot_index"], 0)
        self.assertEqual(
            copied["slots"][0]["character_details_data"]["stat_snapshot"]
            ["artifact"]["summary"]["artifact_ids_by_pos"],
            {str(index): index for index in range(1, 6)},
        )

    def test_equipped_snapshot_overlay_rejects_removed_inventory_ids(self) -> None:
        database, snapshot = self._snapshot_fixture()
        wearer = snapshot.wearers[0]
        changed_ids = dict(wearer.assignment.artifact_ids_by_slot)
        changed_ids["flower"] = 999
        removed_wearer = SelectedEquippedWearer(
            wearer=wearer.wearer,
            assignment=GcsimOptimizerWearerArtifactAssignment(
                wearer=wearer.wearer,
                artifact_ids_by_slot=changed_ids,
            ),
            target_sets=wearer.target_sets,
            set_counts=wearer.set_counts,
        )
        removed_snapshot = SelectedEquippedTeamSnapshot(
            artifact_database_input_sha256=snapshot.artifact_database_input_sha256,
            equipment_rows_sha256=snapshot.equipment_rows_sha256,
            character_keys=snapshot.character_keys,
            wearers=(removed_wearer, *snapshot.wearers[1:]),
        )
        with self.assertRaisesRegex(GcsimOptimizerGoSelectedInputError, "missing or in the wrong slot"):
            selected_team_with_equipped_snapshot_artifacts(
                {"slots": [{"character": {"id": "100"}}]},
                artifact_database=database,
                snapshot=removed_snapshot,
            )

    def test_equipped_snapshot_rejects_duplicate_physical_artifact_ids(self) -> None:
        _database, snapshot = self._snapshot_fixture()
        wearer = snapshot.wearers[1]
        changed_ids = dict(wearer.assignment.artifact_ids_by_slot)
        changed_ids["flower"] = snapshot.wearers[0].assignment.artifact_ids[0]
        duplicate_wearer = SelectedEquippedWearer(
            wearer=wearer.wearer,
            assignment=GcsimOptimizerWearerArtifactAssignment(
                wearer=wearer.wearer,
                artifact_ids_by_slot=changed_ids,
            ),
            target_sets=wearer.target_sets,
            set_counts=wearer.set_counts,
        )
        with self.assertRaisesRegex(GcsimOptimizerGoSelectedInputError, "twenty globally distinct artifacts"):
            SelectedEquippedTeamSnapshot(
                artifact_database_input_sha256=snapshot.artifact_database_input_sha256,
                equipment_rows_sha256=snapshot.equipment_rows_sha256,
                character_keys=snapshot.character_keys,
                wearers=(snapshot.wearers[0], duplicate_wearer, *snapshot.wearers[2:]),
            )

    def test_selected_packages_keep_tiers_not_extra_piece(self) -> None:
        for source, expected in (
            ((("a", 4), ("x", 1)), (("a", 4),)),
            ((("a", 5),), (("a", 4),)),
            ((("a", 2), ("b", 2), ("x", 1)), (("a", 2), ("b", 2))),
            ((("b", 3), ("a", 2)), (("a", 2), ("b", 2))),
        ):
            self.assertEqual(selected_set_requirements(source), expected)
        for bad in ((("a", 3), ("b", 1), ("c", 1)), (("a", 2),),
                    (("a", 2), ("a", 2)), (("a", 4), ("b", 2))):
            with self.assertRaises(GcsimOptimizerGoSelectedInputError):
                selected_set_requirements(bad)

    def test_mixed_packages_transport_both_sets_and_preserve_four_piece_wire(self) -> None:
        wearers = (
            SelectedBoundWearerInput("actor_b", (), (), (("z", 3), ("a", 2))),
            SelectedBoundWearerInput("actor_a", (), (), (("four", 5),)),
        )
        rows = _request_wearers('actor_b add weapon="weapon_b";\nactor_a add weapon="weapon_a";', wearers)
        self.assertEqual(rows[0]["selected_set_uid"], "four")
        self.assertNotIn("selected_sets", rows[0])
        self.assertNotIn("selected_set_uid", rows[1])
        self.assertEqual(rows[1]["selected_sets"], [{"set_uid": "a", "count": 2}, {"set_uid": "z", "count": 2}])

    def test_energy_policy_is_idempotent(self) -> None:
        source = "options iteration=1 ignore_burst_energy=false;\ntarget lvl=100;\n"
        once = enforce_gcsim_optimizer_mvp_energy_policy(source)
        self.assertIn("ignore_burst_energy=true", once)
        self.assertEqual(enforce_gcsim_optimizer_mvp_energy_policy(once), once)

    def test_energy_policy_can_enable_real_burst_requirements(self) -> None:
        source = "options iteration=1 ignore_burst_energy=true;\ntarget lvl=100;\n"
        once = enforce_gcsim_optimizer_mvp_energy_policy(
            source,
            ignore_burst_energy=False,
        )
        self.assertIn("ignore_burst_energy=false", once)
        self.assertEqual(
            enforce_gcsim_optimizer_mvp_energy_policy(
                once,
                ignore_burst_energy=False,
            ),
            once,
        )

    def test_clean_selected_import_does_not_load_historical_trace_search(self) -> None:
        code = (
            "import json,sys; "
            "import run_workspace.gcsim.optimizer_go_selected; "
            "print(json.dumps(sorted(m for m in sys.modules "
            "if m.startswith('run_workspace.gcsim.trace_equation') "
            "or m.endswith('optimizer_main_response') "
            "or m.endswith('optimizer_stat_response'))))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(completed.stdout), [])


if __name__ == "__main__":
    unittest.main()
