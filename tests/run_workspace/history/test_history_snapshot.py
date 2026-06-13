"""Synthetic fixtures for the History Snapshot Bundle v1 contract.

These fixtures pin the backend schema/service before the future live
RunSession/AppShell snapshot builder exists. They must stay local-only and must
not read account DBs, generated assets, profile data, caches, or network state.
"""

from __future__ import annotations

from dataclasses import replace
import tempfile
import unittest
from pathlib import Path

from run_workspace.history_snapshot import (
    HISTORY_RUN_TYPE_ABYSS,
    HISTORY_RUN_TYPE_DPS_DUMMY,
    HISTORY_SNAPSHOT_FILENAME,
    HistoryAbyssChamberSnapshot,
    HistoryAbyssScenarioSnapshot,
    HistoryAbyssSideResultSnapshot,
    HistoryAbyssTimerSnapshot,
    HistoryArtifactBuildSnapshot,
    HistoryArtifactSlotSnapshot,
    HistoryAssetRefSnapshot,
    HistoryBonusSourceSnapshot,
    HistoryCharacterSnapshot,
    HistoryDpsDummyScenarioSnapshot,
    HistoryPreviewRefSnapshot,
    HistoryResultSummarySnapshot,
    HistoryScenarioSnapshot,
    HistorySetBonusSnapshot,
    HistorySnapshotBundle,
    HistorySnapshotBundleStore,
    HistoryStatRowSnapshot,
    HistoryTeamSlotSnapshot,
    HistoryTeamSnapshot,
    HistoryWeaponSnapshot,
    MalformedHistorySnapshotBundleError,
    UnsupportedHistorySnapshotSchemaVersionError,
    history_snapshot_bundle_from_json_text,
    history_snapshot_bundle_to_json_text,
)


class HistorySnapshotBundleTests(unittest.TestCase):
    def test_minimal_abyss_snapshot_bundle_roundtrip(self) -> None:
        bundle = _minimal_abyss_bundle()

        roundtripped = history_snapshot_bundle_from_json_text(
            history_snapshot_bundle_to_json_text(bundle)
        )

        self.assertEqual(roundtripped.to_dict(), bundle.to_dict())
        self.assertEqual(roundtripped.run_type, HISTORY_RUN_TYPE_ABYSS)
        self.assertEqual(len(roundtripped.teams), 2)
        self.assertEqual(roundtripped.scenario.abyss.floor, 12)

    def test_minimal_dps_dummy_snapshot_bundle_roundtrip(self) -> None:
        bundle = _minimal_dps_dummy_bundle()

        roundtripped = history_snapshot_bundle_from_json_text(
            history_snapshot_bundle_to_json_text(bundle)
        )

        self.assertEqual(roundtripped.to_dict(), bundle.to_dict())
        self.assertEqual(roundtripped.run_type, HISTORY_RUN_TYPE_DPS_DUMMY)
        self.assertEqual(len(roundtripped.teams), 1)
        self.assertEqual(roundtripped.scenario.dps_dummy.target_label, "Training dummy")

    def test_rich_team_slot_data_survives_roundtrip(self) -> None:
        bundle = _rich_abyss_bundle()

        roundtripped = history_snapshot_bundle_from_json_text(
            history_snapshot_bundle_to_json_text(bundle)
        )
        slot = roundtripped.teams[0].slots[0]

        self.assertEqual(slot.character.character_id, "10000050")
        self.assertEqual(slot.character.name, "Thoma")
        self.assertEqual(slot.weapon.weapon_fingerprint, "favonius_lance|90|5")
        self.assertEqual(slot.weapon.stat_rows[0].label, "Base ATK")
        self.assertEqual(slot.artifact_build.build_name, "Shield support")
        self.assertEqual(slot.artifact_build.artifact_slots[0].main_stat.value, "46.6%")
        self.assertEqual(
            slot.artifact_build.active_set_bonuses[0].effects,
            ("Shield Strength +30%",),
        )
        self.assertEqual(slot.stat_rows[0].label, "HP")
        self.assertEqual(slot.bonus_sources[0].source_kind, "artifact_set")

    def test_provenance_ids_survive_but_are_not_required_for_display(self) -> None:
        bundle = _minimal_dps_dummy_bundle(
            slot=HistoryTeamSlotSnapshot(
                slot_index=0,
                character=HistoryCharacterSnapshot(
                    name="Display Traveler",
                    provenance={"debug_live_character_id": "10000007"},
                ),
                weapon=HistoryWeaponSnapshot(
                    name="Display Sword",
                    provenance={"debug_live_weapon_id": "11501"},
                ),
            )
        )

        roundtripped = history_snapshot_bundle_from_json_text(
            history_snapshot_bundle_to_json_text(bundle)
        )
        slot = roundtripped.teams[0].slots[0]

        self.assertEqual(slot.character.character_id, "")
        self.assertEqual(slot.character.name, "Display Traveler")
        self.assertEqual(slot.character.provenance["debug_live_character_id"], "10000007")
        self.assertEqual(slot.weapon.weapon_id, "")
        self.assertEqual(slot.weapon.name, "Display Sword")
        self.assertEqual(slot.weapon.provenance["debug_live_weapon_id"], "11501")

    def test_bundle_relative_asset_and_preview_refs_survive_roundtrip(self) -> None:
        bundle = replace(
            _minimal_abyss_bundle(),
            asset_refs=(
                HistoryAssetRefSnapshot(
                    path="assets/characters/thoma.png",
                    role="portrait",
                    label="Thoma portrait",
                    mime_type="image/png",
                    width=128,
                    height=128,
                    sha256="abc123",
                ),
            ),
            preview_refs=(
                HistoryPreviewRefSnapshot(
                    path="preview/card.png",
                    preview_type="history_card",
                    label="Card preview",
                    mime_type="image/png",
                    width=960,
                    height=540,
                ),
            ),
        )

        roundtripped = history_snapshot_bundle_from_json_text(
            history_snapshot_bundle_to_json_text(bundle)
        )

        self.assertEqual(roundtripped.asset_refs[0].path, "assets/characters/thoma.png")
        self.assertEqual(roundtripped.asset_refs[0].role, "portrait")
        self.assertEqual(roundtripped.preview_refs[0].path, "preview/card.png")
        self.assertEqual(roundtripped.preview_refs[0].preview_type, "history_card")

    def test_unsupported_schema_version_fails_clearly(self) -> None:
        payload = _minimal_abyss_bundle().to_dict()
        payload["schema_version"] = 999

        with self.assertRaisesRegex(
            UnsupportedHistorySnapshotSchemaVersionError,
            "Unsupported history snapshot schema version",
        ):
            HistorySnapshotBundle.from_dict(payload)

    def test_malformed_run_type_fails_clearly(self) -> None:
        payload = _minimal_abyss_bundle().to_dict()
        payload["run_type"] = "domain"

        with self.assertRaisesRegex(
            MalformedHistorySnapshotBundleError,
            "Malformed history snapshot run type",
        ):
            HistorySnapshotBundle.from_dict(payload)

    def test_store_writes_and_reads_only_under_caller_provided_root(self) -> None:
        bundle = _rich_abyss_bundle(bundle_id="store-rich-abyss")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "history-root"
            store = HistorySnapshotBundleStore(root)

            snapshot_path = store.write_bundle(bundle)
            read_back = store.read_bundle(bundle.bundle_id)

            self.assertEqual(snapshot_path, root / bundle.bundle_id / HISTORY_SNAPSHOT_FILENAME)
            self.assertTrue(_is_relative_to(snapshot_path, root))
            self.assertTrue(snapshot_path.exists())
            self.assertFalse(snapshot_path.with_name("snapshot.json.tmp").exists())
            self.assertEqual(read_back.to_dict(), bundle.to_dict())
            self.assertEqual(sorted(path.name for path in root.iterdir()), [bundle.bundle_id])

    def test_store_rejects_path_traversal_bundle_id(self) -> None:
        bundle = replace(_minimal_abyss_bundle(), bundle_id="../escape")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "history-root"
            store = HistorySnapshotBundleStore(root)

            with self.assertRaisesRegex(
                MalformedHistorySnapshotBundleError,
                "expected one safe path segment",
            ):
                store.write_bundle(bundle)

            self.assertFalse((Path(tmp) / "escape").exists())


def _minimal_abyss_bundle(*, bundle_id: str = "abyss-minimal") -> HistorySnapshotBundle:
    return HistorySnapshotBundle(
        bundle_id=bundle_id,
        created_at="2026-06-13T12:00:00Z",
        run_type=HISTORY_RUN_TYPE_ABYSS,
        source="unit_test",
        content_language="en-us",
        teams=(
            HistoryTeamSnapshot(
                team_index=0,
                label="Team 1",
                slots=(
                    HistoryTeamSlotSnapshot(
                        slot_index=0,
                        character=HistoryCharacterSnapshot(
                            character_id="10000050",
                            name="Thoma",
                        ),
                    ),
                ),
            ),
            HistoryTeamSnapshot(
                team_index=1,
                label="Team 2",
                slots=(
                    HistoryTeamSlotSnapshot(
                        slot_index=0,
                        character=HistoryCharacterSnapshot(
                            character_id="10000089",
                            name="Furina",
                        ),
                    ),
                ),
            ),
        ),
        scenario=HistoryScenarioSnapshot(
            run_type=HISTORY_RUN_TYPE_ABYSS,
            abyss=HistoryAbyssScenarioSnapshot(
                floor=12,
                target_mode="solo",
                chambers=(
                    HistoryAbyssChamberSnapshot(
                        chamber_index=1,
                        chamber_label="12-1",
                        timer=HistoryAbyssTimerSnapshot(
                            team1_left_seconds=540,
                            team2_left_seconds=510,
                            start_seconds=600,
                            normalized_team1_left_seconds=540,
                            normalized_team2_left_seconds=510,
                            team1_elapsed_seconds=60,
                            team2_elapsed_seconds=30,
                            total_elapsed_seconds=90,
                        ),
                        side_results=(
                            HistoryAbyssSideResultSnapshot(
                                side=1,
                                team_index=0,
                                elapsed_seconds=60,
                                total_hp=6000000,
                                factual_dps=100000,
                                hp_source="unit_fixture",
                                target_mode="solo",
                            ),
                        ),
                    ),
                ),
                total_elapsed_seconds=90,
            ),
        ),
        result_summaries=(
            HistoryResultSummarySnapshot(
                result_type="factual_dps",
                label="Fact T1 DPS",
                team_index=0,
                chamber_index=1,
                side=1,
                dps=100000,
                elapsed_seconds=60,
                source="unit_fixture",
            ),
        ),
    )


def _minimal_dps_dummy_bundle(
    *,
    slot: HistoryTeamSlotSnapshot | None = None,
) -> HistorySnapshotBundle:
    return HistorySnapshotBundle(
        bundle_id="dps-dummy-minimal",
        created_at="2026-06-13T12:10:00Z",
        run_type=HISTORY_RUN_TYPE_DPS_DUMMY,
        source="unit_test",
        content_language="en-us",
        teams=(
            HistoryTeamSnapshot(
                team_index=0,
                label="Team",
                slots=(
                    slot
                    or HistoryTeamSlotSnapshot(
                        slot_index=0,
                        character=HistoryCharacterSnapshot(name="Furina"),
                    ),
                ),
            ),
        ),
        scenario=HistoryScenarioSnapshot(
            run_type=HISTORY_RUN_TYPE_DPS_DUMMY,
            dps_dummy=HistoryDpsDummyScenarioSnapshot(
                target_label="Training dummy",
                target_hp=1000000,
                duration_seconds=20.0,
                factual_damage=1000000.0,
                factual_dps=50000.0,
                result_status="measured",
            ),
        ),
        result_summaries=(
            HistoryResultSummarySnapshot(
                result_type="factual_dps",
                label="Dummy factual DPS",
                team_index=0,
                dps=50000.0,
                damage=1000000.0,
                elapsed_seconds=20.0,
                source="manual_fixture",
            ),
        ),
    )


def _rich_abyss_bundle(*, bundle_id: str = "abyss-rich") -> HistorySnapshotBundle:
    return replace(
        _minimal_abyss_bundle(bundle_id=bundle_id),
        teams=(
            HistoryTeamSnapshot(
                team_index=0,
                label="Team 1",
                slots=(
                    HistoryTeamSlotSnapshot(
                        slot_index=0,
                        character=HistoryCharacterSnapshot(
                            character_id="10000050",
                            name="Thoma",
                            level=90,
                            element="Pyro",
                            rarity=4,
                            constellation=6,
                            portrait_ref="assets/characters/thoma.png",
                            provenance={"source_table": "account_characters"},
                        ),
                        weapon=HistoryWeaponSnapshot(
                            weapon_id="13501",
                            name="Favonius Lance",
                            level=90,
                            promote_level=6,
                            rarity=4,
                            refinement=5,
                            weapon_type="Polearm",
                            weapon_fingerprint="favonius_lance|90|5",
                            icon_ref="assets/weapons/favonius_lance.png",
                            passive_name="Windfall",
                            passive_effects=("Generates particles on CRIT.",),
                            stat_rows=(
                                HistoryStatRowSnapshot(
                                    label="Base ATK",
                                    value="565",
                                    key="base_atk",
                                ),
                            ),
                            provenance={"observed_stack_key": "favonius_lance|90|5"},
                        ),
                        artifact_build=HistoryArtifactBuildSnapshot(
                            source="current_equipment",
                            build_id="preset-42",
                            build_name="Shield support",
                            artifact_slots=(
                                HistoryArtifactSlotSnapshot(
                                    position=3,
                                    artifact_id="artifact-100",
                                    set_uid="retracing_bolide",
                                    set_name="Retracing Bolide",
                                    piece_name="Sands of Eon",
                                    rarity=5,
                                    level=20,
                                    main_stat=HistoryStatRowSnapshot(
                                        label="HP",
                                        value="46.6%",
                                        key="HP_PERCENT",
                                    ),
                                    substats=(
                                        HistoryStatRowSnapshot(
                                            label="Energy Recharge",
                                            value="11.0%",
                                            key="ENERGY_RECHARGE",
                                        ),
                                    ),
                                    icon_ref="assets/artifacts/sands.png",
                                    provenance={"artifact_db_id": 100},
                                ),
                            ),
                            active_set_bonuses=(
                                HistorySetBonusSnapshot(
                                    set_uid="retracing_bolide",
                                    set_name="Retracing Bolide",
                                    piece_count=2,
                                    icon_ref="assets/sets/retracing_bolide.png",
                                    effects=("Shield Strength +30%",),
                                ),
                            ),
                            stat_rows=(
                                HistoryStatRowSnapshot(
                                    label="HP",
                                    value="34,250",
                                    key="HP",
                                ),
                            ),
                            crit_value=42.4,
                            proc_count=9,
                            missing_positions=(1, 2, 4, 5),
                            warnings=("artifact_build_incomplete",),
                            provenance={"selected_build_id": 42},
                        ),
                        stat_rows=(
                            HistoryStatRowSnapshot(label="HP", value="34,250", key="HP"),
                            HistoryStatRowSnapshot(label="ER", value="221%", key="ENERGY_RECHARGE"),
                        ),
                        bonus_sources=(
                            HistoryBonusSourceSnapshot(
                                source_kind="artifact_set",
                                source_id="retracing_bolide",
                                label="Retracing Bolide 2p",
                                effects=("Shield Strength +30%",),
                            ),
                        ),
                        asset_refs=(
                            HistoryAssetRefSnapshot(
                                path="assets/characters/thoma.png",
                                role="portrait",
                                label="Thoma portrait",
                            ),
                        ),
                        warnings=("set_bonus_formulas_not_included",),
                    ),
                ),
            ),
            HistoryTeamSnapshot(
                team_index=1,
                label="Team 2",
                slots=(
                    HistoryTeamSlotSnapshot(
                        slot_index=0,
                        character=HistoryCharacterSnapshot(name="Furina"),
                    ),
                ),
            ),
        ),
        asset_refs=(
            HistoryAssetRefSnapshot(
                path="assets/characters/thoma.png",
                role="portrait",
                label="Thoma portrait",
            ),
        ),
        preview_refs=(
            HistoryPreviewRefSnapshot(
                path="preview/abyss-rich.png",
                preview_type="history_card",
            ),
        ),
        provenance={"fixture": "rich_abyss_bundle"},
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


if __name__ == "__main__":
    unittest.main()
