from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from run_workspace.abyss.source_data import (
    HP_SOURCE_FANDOM_ENEMY_PAGE_FALLBACK,
    load_abyss_floor12_source_data,
    rebuild_abyss_floor_source_data_with_rows,
)
from run_workspace.gcsim.abyss_wave_scenario import (
    MISSING_ENEMY_TYPE_MAPPING_WARNING,
    AbyssEnemyTypeMapping,
    AbyssEnemyTypeMappingRecord,
    IDENTITY_KIND_FANDOM_PAGE_TITLE,
    IDENTITY_KIND_NANOKA_MONSTER_ID,
    abyss_enemy_identity_candidates,
    build_abyss_wave_scenario_payload,
    load_enemy_type_mapping_from_json,
    write_abyss_wave_scenario_payload,
)
from run_workspace.gcsim.enemy_type_registry import (
    GcsimEnemyTypeRegistry,
    MATCH_METHOD_AMBIGUOUS,
    MATCH_METHOD_COMPATIBLE_BASE_NAME,
    MATCH_METHOD_EXACT_NORMALIZED_NAME,
    MATCH_METHOD_MANUAL_MAPPING,
    MATCH_METHOD_MISSING,
    MATCH_METHOD_SNAP_TITLE_CONTAINS_TARGET,
    MATCH_METHOD_SNAP_TITLE_FALLBACK,
)
from run_workspace.gcsim.snap_monster_titles import (
    SNAP_TITLE_SOURCE_KIND,
    SnapMonsterTitleCandidate,
    SnapMonsterTitleIndex,
)
from tests.run_workspace.abyss.test_source_data import composition_report, fandom_row, nanoka_report, nanoka_row


def _enemy_type_mapping() -> AbyssEnemyTypeMapping:
    return AbyssEnemyTypeMapping(
        records=(
            AbyssEnemyTypeMappingRecord(
                source_kind=IDENTITY_KIND_NANOKA_MONSTER_ID,
                source_id="first",
                gcsim_type="battlehardenedgroundedgeoshroom",
            ),
            AbyssEnemyTypeMappingRecord(
                source_kind=IDENTITY_KIND_NANOKA_MONSTER_ID,
                source_id="second",
                gcsim_type="dummy",
            ),
        ),
        mapping_name="test_enemy_type_mapping",
    )


def _source_data(*, missing_level: bool = False, missing_hp: bool = False):
    fandom_rows = [
        fandom_row(
            "First Enemy",
            chamber=1,
            side=1,
            wave=1,
            count=2,
            level=None if missing_level else 95,
        ),
        fandom_row(
            "Second Enemy",
            chamber=1,
            side=1,
            wave=2,
            count=1,
            level=90,
        ),
    ]
    tower_report = None
    if not missing_hp:
        tower_report = nanoka_report(
            "119",
            [
                nanoka_row(
                    "First Enemy",
                    chamber=1,
                    side=1,
                    hp=100_000,
                    monster_id="first",
                    level=95,
                ),
                nanoka_row(
                    "Second Enemy",
                    chamber=1,
                    side=1,
                    hp=200_000,
                    monster_id="second",
                    level=90,
                ),
            ],
        )
    return load_abyss_floor12_source_data(
        "2026-05-16",
        "119",
        composition_report=composition_report("2026-05-16", fandom_rows),
        nanoka_report=tower_report,
    )


def _replace_enemy_row(data, index: int, **changes):
    rows = list(data.enemy_rows)
    rows[index] = replace(rows[index], **changes)
    return rebuild_abyss_floor_source_data_with_rows(data, rows)


def _fandom_mapping(*names: str) -> AbyssEnemyTypeMapping:
    return AbyssEnemyTypeMapping(
        records=tuple(
            AbyssEnemyTypeMappingRecord(
                source_kind=IDENTITY_KIND_FANDOM_PAGE_TITLE,
                source_id=name,
                gcsim_type="dummy",
            )
            for name in names
        ),
        mapping_name="fandom_title_mapping",
    )


def _registry(*target_types: str) -> GcsimEnemyTypeRegistry:
    return GcsimEnemyTypeRegistry(target_types)


def _snap_titles(*pairs: tuple[str, str]) -> SnapMonsterTitleIndex:
    grouped: dict[str, list[SnapMonsterTitleCandidate]] = {}
    for name, title in pairs:
        candidate = SnapMonsterTitleCandidate(source_name=name, title=title)
        grouped.setdefault(candidate.normalized_source_name, []).append(candidate)
    return SnapMonsterTitleIndex(
        {key: tuple(value) for key, value in grouped.items()}
    )


def _rename_enemy(data, index: int, name: str):
    return _replace_enemy_row(
        data,
        index,
        primary_display_name=name,
        fandom_enemy_page_url=f"https://genshin-impact.fandom.com/wiki/{name.replace(' ', '_')}",
        matched_nanoka_display_name=name,
    )


class GcsimAbyssWaveScenarioTest(unittest.TestCase):
    def test_rows_grouped_by_wave_and_enemy_count_expands_targets(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(),
            chamber=1,
            side=1,
            enemy_type_mapping=_enemy_type_mapping(),
        )

        self.assertTrue(result.ready)
        self.assertIsNotNone(result.payload)
        assert result.payload is not None
        self.assertEqual(result.audit.wave_count, 2)
        self.assertEqual(result.audit.source_enemy_row_count, 2)
        self.assertEqual(result.audit.generated_target_count, 3)
        self.assertEqual([len(wave["targets"]) for wave in result.payload["waves"]], [2, 1])
        self.assertEqual(result.payload["waves"][0]["targets"][0]["hp"], 100_000.0)
        self.assertEqual(result.payload["waves"][0]["targets"][1]["hp"], 100_000.0)
        self.assertEqual(result.payload["waves"][1]["targets"][0]["level"], 90)
        self.assertEqual(
            result.payload["waves"][0]["targets"][0]["type"],
            "battlehardenedgroundedgeoshroom",
        )
        self.assertNotIn("radius", result.payload["waves"][0]["targets"][0])
        self.assertNotIn("pos", result.payload["waves"][0]["targets"][0])
        self.assertNotIn("resist", result.payload["waves"][0]["targets"][0])

    def test_missing_hp_reports_not_ready_without_payload(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(missing_hp=True),
            chamber=1,
            side=1,
            enemy_type_mapping=_enemy_type_mapping(),
        )

        self.assertFalse(result.ready)
        self.assertIsNone(result.payload)
        self.assertGreater(len(result.audit.missing_hp_rows), 0)
        self.assertIn("First Enemy", result.audit.missing_hp_rows[0])

    def test_missing_level_reports_not_ready_without_payload(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(missing_level=True),
            chamber=1,
            side=1,
            enemy_type_mapping=_enemy_type_mapping(),
        )

        self.assertFalse(result.ready)
        self.assertIsNone(result.payload)
        self.assertGreater(len(result.audit.missing_level_rows), 0)
        self.assertIn("First Enemy", result.audit.missing_level_rows[0])

    def test_missing_enemy_type_mapping_prevents_payload_generation(self) -> None:
        result = build_abyss_wave_scenario_payload(_source_data(), chamber=1, side=1)

        self.assertFalse(result.ready)
        self.assertIsNone(result.payload)
        self.assertGreater(len(result.audit.missing_type_mapping_rows), 0)
        self.assertIn(MISSING_ENEMY_TYPE_MAPPING_WARNING, result.audit.warnings)

    def test_partial_enemy_type_mapping_reports_missing_row(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(),
            chamber=1,
            side=1,
            enemy_type_mapping=AbyssEnemyTypeMapping(
                types_by_nanoka_monster_id={"first": "battlehardenedgroundedgeoshroom"}
            ),
        )

        self.assertFalse(result.ready)
        self.assertIsNone(result.payload)
        self.assertEqual(len(result.audit.missing_type_mapping_rows), 1)
        self.assertIn("Second Enemy", result.audit.missing_type_mapping_rows[0])

    def test_enemy_type_mapping_produces_schema_v1_payload(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(),
            chamber=1,
            side=1,
            enemy_type_mapping=_enemy_type_mapping(),
        )

        self.assertTrue(result.ready)
        self.assertIsNotNone(result.payload)
        assert result.payload is not None
        self.assertEqual(result.payload["schema_version"], 1)
        self.assertEqual(result.payload["spawn_policy"], "group_clear")
        self.assertEqual(result.audit.enemy_type_mapping_name, "test_enemy_type_mapping")
        self.assertEqual(result.audit.type_mapping_details[0]["status"], "resolved")
        self.assertEqual(result.audit.type_mapping_details[0]["method"], MATCH_METHOD_MANUAL_MAPPING)
        self.assertEqual(
            result.audit.type_mapping_details[0]["selected_identity"]["source_kind"],
            IDENTITY_KIND_NANOKA_MONSTER_ID,
        )
        self.assertEqual(
            result.payload["waves"][1]["targets"][0],
            {"hp": 200_000.0, "level": 90, "type": "dummy"},
        )

    def test_manual_mapping_wins_over_registry_match(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(),
            chamber=1,
            side=1,
            enemy_type_mapping=AbyssEnemyTypeMapping(
                records=(
                    AbyssEnemyTypeMappingRecord(
                        source_kind=IDENTITY_KIND_NANOKA_MONSTER_ID,
                        source_id="first",
                        gcsim_type="dummy",
                    ),
                    AbyssEnemyTypeMappingRecord(
                        source_kind=IDENTITY_KIND_NANOKA_MONSTER_ID,
                        source_id="second",
                        gcsim_type="secondenemy",
                    ),
                )
            ),
            enemy_type_registry=_registry("firstenemy", "secondenemy", "dummy"),
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.payload["waves"][0]["targets"][0]["type"], "dummy")
        self.assertEqual(result.audit.type_mapping_details[0]["method"], MATCH_METHOD_MANUAL_MAPPING)

    def test_identity_candidates_include_nanoka_and_fandom_sources(self) -> None:
        row = _source_data().enemy_rows[0]
        candidates = abyss_enemy_identity_candidates(row)

        self.assertEqual(candidates[0].source_kind, IDENTITY_KIND_NANOKA_MONSTER_ID)
        self.assertEqual(candidates[0].source_id, "first")
        self.assertEqual(candidates[1].source_id, "First Enemy")
        self.assertIn(
            (IDENTITY_KIND_FANDOM_PAGE_TITLE, "First Enemy"),
            [candidate.key() for candidate in candidates],
        )

    def test_registry_resolves_grounded_geoshroom_to_known_gcsim_type(self) -> None:
        data = _rename_enemy(_source_data(), 0, "Grounded Geoshroom")

        result = build_abyss_wave_scenario_payload(
            data,
            chamber=1,
            side=1,
            enemy_type_registry=_registry("groundedgeoshroom", "secondenemy"),
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.payload["waves"][0]["targets"][0]["type"], "groundedgeoshroom")
        self.assertEqual(
            result.audit.type_mapping_details[0]["method"],
            MATCH_METHOD_EXACT_NORMALIZED_NAME,
        )

    def test_registry_exact_normalized_match_works(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(),
            chamber=1,
            side=1,
            enemy_type_registry=_registry("firstenemy", "secondenemy"),
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.payload["waves"][1]["targets"][0]["type"], "secondenemy")
        self.assertEqual(
            result.audit.type_mapping_details[1]["method"],
            MATCH_METHOD_EXACT_NORMALIZED_NAME,
        )

    def test_registry_compatible_base_match_works_when_exact_variant_absent(self) -> None:
        data = _rename_enemy(_source_data(), 0, "Battle-Hardened Grounded Geoshroom")

        result = build_abyss_wave_scenario_payload(
            data,
            chamber=1,
            side=1,
            enemy_type_registry=_registry("groundedgeoshroom", "secondenemy"),
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.payload["waves"][0]["targets"][0]["type"], "groundedgeoshroom")
        self.assertEqual(
            result.audit.type_mapping_details[0]["method"],
            MATCH_METHOD_COMPATIBLE_BASE_NAME,
        )

    def test_registry_ambiguous_compatible_match_is_reported(self) -> None:
        data = _rename_enemy(_source_data(), 0, "Grounded Geoshroom")

        result = build_abyss_wave_scenario_payload(
            data,
            chamber=1,
            side=1,
            enemy_type_registry=_registry(
                "battlehardenedgroundedgeoshroom",
                "veterangroundedgeoshroom",
                "secondenemy",
            ),
        )

        self.assertFalse(result.ready)
        self.assertEqual(len(result.audit.ambiguous_type_mapping_rows), 1)
        self.assertEqual(result.audit.type_mapping_details[0]["method"], MATCH_METHOD_AMBIGUOUS)
        self.assertEqual(
            result.audit.type_mapping_details[0]["ambiguous_types"],
            ["battlehardenedgroundedgeoshroom", "veterangroundedgeoshroom"],
        )

    def test_registry_missing_match_is_reported(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(),
            chamber=1,
            side=1,
            enemy_type_registry=_registry("secondenemy"),
        )

        self.assertFalse(result.ready)
        self.assertEqual(len(result.audit.missing_type_mapping_rows), 1)
        self.assertEqual(result.audit.type_mapping_details[0]["method"], MATCH_METHOD_MISSING)

    def test_snap_title_fallback_resolves_mek_arkhe_suffix(self) -> None:
        data = _rename_enemy(_source_data(), 0, "Assault Specialist Mek - Pneuma")

        result = build_abyss_wave_scenario_payload(
            data,
            chamber=1,
            side=1,
            enemy_type_registry=_registry("assaultspecialistmek", "secondenemy"),
            snap_title_index=_snap_titles(
                ("Assault Specialist Mek - Pneuma", "Assault Specialist Mek")
            ),
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.payload["waves"][0]["targets"][0]["type"], "assaultspecialistmek")
        self.assertEqual(
            result.audit.type_mapping_details[0]["method"],
            MATCH_METHOD_SNAP_TITLE_FALLBACK,
        )
        self.assertEqual(
            result.audit.type_mapping_details[0]["selected_identity"]["source_kind"],
            SNAP_TITLE_SOURCE_KIND,
        )

    def test_snap_title_fallback_resolves_tenebrous_mimesis_form(self) -> None:
        data = _rename_enemy(
            _source_data(),
            0,
            "Tenebrous Mimesis - Anemo Hilichurl Rogue",
        )

        result = build_abyss_wave_scenario_payload(
            data,
            chamber=1,
            side=1,
            enemy_type_registry=_registry("tenebrousmimiflora", "secondenemy"),
            snap_title_index=_snap_titles(
                (
                    "Tenebrous Mimesis - Anemo Hilichurl Rogue",
                    "Tenebrous Mimiflora",
                )
            ),
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.payload["waves"][0]["targets"][0]["type"], "tenebrousmimiflora")
        self.assertEqual(
            result.audit.type_mapping_details[0]["method"],
            MATCH_METHOD_SNAP_TITLE_FALLBACK,
        )

    def test_registry_exact_match_wins_before_snap_title_fallback(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(),
            chamber=1,
            side=1,
            enemy_type_registry=_registry("firstenemy", "secondenemy", "wrongenemy"),
            snap_title_index=_snap_titles(("First Enemy", "Wrong Enemy")),
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.payload["waves"][0]["targets"][0]["type"], "firstenemy")
        self.assertEqual(
            result.audit.type_mapping_details[0]["method"],
            MATCH_METHOD_EXACT_NORMALIZED_NAME,
        )

    def test_manual_mapping_wins_before_snap_title_fallback(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(),
            chamber=1,
            side=1,
            enemy_type_mapping=_enemy_type_mapping(),
            enemy_type_registry=_registry("firstenemy", "secondenemy", "wrongenemy"),
            snap_title_index=_snap_titles(("First Enemy", "Wrong Enemy")),
        )

        self.assertTrue(result.ready)
        self.assertEqual(
            result.audit.type_mapping_details[0]["method"],
            MATCH_METHOD_MANUAL_MAPPING,
        )

    def test_without_snap_title_index_missing_behavior_is_unchanged(self) -> None:
        data = _rename_enemy(_source_data(), 0, "Assault Specialist Mek - Pneuma")

        result = build_abyss_wave_scenario_payload(
            data,
            chamber=1,
            side=1,
            enemy_type_registry=_registry("secondenemy"),
        )

        self.assertFalse(result.ready)
        self.assertEqual(result.audit.type_mapping_details[0]["method"], MATCH_METHOD_MISSING)

    def test_duplicate_snap_name_with_different_titles_is_ambiguous(self) -> None:
        data = _rename_enemy(_source_data(), 0, "Assault Specialist Mek - Pneuma")

        result = build_abyss_wave_scenario_payload(
            data,
            chamber=1,
            side=1,
            enemy_type_registry=_registry("assaultspecialistmek", "clockworkmek"),
            snap_title_index=_snap_titles(
                ("Assault Specialist Mek - Pneuma", "Assault Specialist Mek"),
                ("Assault Specialist Mek - Pneuma", "Clockwork Mek"),
            ),
        )

        self.assertFalse(result.ready)
        self.assertEqual(len(result.audit.ambiguous_type_mapping_rows), 1)
        self.assertEqual(
            result.audit.type_mapping_details[0]["method"],
            MATCH_METHOD_SNAP_TITLE_FALLBACK,
        )
        self.assertIn(
            "snap_title_ambiguous_for_name:assaultspecialistmekpneuma",
            result.audit.type_mapping_details[0]["warnings"],
        )

    def test_snap_title_missing_from_registry_reports_missing(self) -> None:
        data = _rename_enemy(_source_data(), 0, "Assault Specialist Mek - Pneuma")

        result = build_abyss_wave_scenario_payload(
            data,
            chamber=1,
            side=1,
            enemy_type_registry=_registry("secondenemy"),
            snap_title_index=_snap_titles(
                ("Assault Specialist Mek - Pneuma", "Assault Specialist Mek")
            ),
        )

        self.assertFalse(result.ready)
        self.assertEqual(
            result.audit.type_mapping_details[0]["method"],
            MATCH_METHOD_SNAP_TITLE_FALLBACK,
        )
        self.assertIn(
            "snap_title_registry_match_missing:assaultspecialistmek",
            result.audit.type_mapping_details[0]["warnings"],
        )

    def test_snap_title_contains_target_resolves_unique_registry_extension(self) -> None:
        data = _rename_enemy(_source_data(), 0, "Tenebrous Papilla: Type II")

        result = build_abyss_wave_scenario_payload(
            data,
            chamber=1,
            side=1,
            enemy_type_registry=_registry("tenebrouspapillatypei", "secondenemy"),
            snap_title_index=_snap_titles(
                ("Tenebrous Papilla: Type II", "Tenebrous Papilla")
            ),
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.payload["waves"][0]["targets"][0]["type"], "tenebrouspapillatypei")
        self.assertEqual(
            result.audit.type_mapping_details[0]["method"],
            MATCH_METHOD_SNAP_TITLE_CONTAINS_TARGET,
        )
        self.assertEqual(
            result.audit.type_mapping_details[0]["selected_identity"]["source_id"],
            "Tenebrous Papilla",
        )
        self.assertIn(
            "snap_title_contains_target:tenebrouspapilla->tenebrouspapillatypei",
            result.audit.type_mapping_details[0]["warnings"],
        )

    def test_snap_title_contains_target_reports_ambiguous_matches(self) -> None:
        data = _rename_enemy(_source_data(), 0, "Tenebrous Papilla: Type II")

        result = build_abyss_wave_scenario_payload(
            data,
            chamber=1,
            side=1,
            enemy_type_registry=_registry(
                "shadowtenebrouspapilla",
                "tenebrouspapillatypei",
                "secondenemy",
            ),
            snap_title_index=_snap_titles(
                ("Tenebrous Papilla: Type II", "Tenebrous Papilla")
            ),
        )

        self.assertFalse(result.ready)
        self.assertEqual(len(result.audit.ambiguous_type_mapping_rows), 1)
        self.assertEqual(
            result.audit.type_mapping_details[0]["method"],
            MATCH_METHOD_SNAP_TITLE_CONTAINS_TARGET,
        )
        self.assertEqual(
            result.audit.type_mapping_details[0]["ambiguous_types"],
            ["shadowtenebrouspapilla", "tenebrouspapillatypei"],
        )

    def test_falls_back_to_fandom_identity_when_nanoka_id_missing(self) -> None:
        data = _replace_enemy_row(
            _source_data(),
            0,
            nanoka_monster_id=None,
            matched_nanoka_display_name=None,
        )

        result = build_abyss_wave_scenario_payload(
            data,
            chamber=1,
            side=1,
            enemy_type_mapping=AbyssEnemyTypeMapping(
                records=(
                    *_fandom_mapping("First Enemy").records,
                    *_fandom_mapping("Second Enemy").records,
                )
            ),
        )

        self.assertTrue(result.ready)
        self.assertEqual(
            result.audit.type_mapping_details[0]["selected_identity"]["source_kind"],
            IDENTITY_KIND_FANDOM_PAGE_TITLE,
        )

    def test_falls_back_to_fandom_identity_when_nanoka_id_is_unmapped(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(),
            chamber=1,
            side=1,
            enemy_type_mapping=AbyssEnemyTypeMapping(
                records=(
                    *_fandom_mapping("First Enemy").records,
                    AbyssEnemyTypeMappingRecord(
                        source_kind=IDENTITY_KIND_NANOKA_MONSTER_ID,
                        source_id="second",
                        gcsim_type="dummy",
                    ),
                )
            ),
        )

        self.assertTrue(result.ready)
        self.assertEqual(
            result.audit.type_mapping_details[0]["selected_identity"]["source_kind"],
            IDENTITY_KIND_FANDOM_PAGE_TITLE,
        )

    def test_hp_source_does_not_control_fandom_type_fallback(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(),
            chamber=1,
            side=1,
            enemy_type_mapping=AbyssEnemyTypeMapping(
                records=(
                    *_fandom_mapping("First Enemy").records,
                    *_fandom_mapping("Second Enemy").records,
                )
            ),
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.payload["waves"][0]["targets"][0]["type"], "dummy")

    def test_nanoka_hp_accepts_fandom_name_registry_resolution(self) -> None:
        data = _replace_enemy_row(
            _source_data(),
            0,
            matched_nanoka_display_name=None,
        )

        result = build_abyss_wave_scenario_payload(
            data,
            chamber=1,
            side=1,
            enemy_type_registry=_registry("firstenemy", "secondenemy"),
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.payload["waves"][0]["targets"][0]["hp"], 100_000.0)
        self.assertEqual(result.payload["waves"][0]["targets"][0]["type"], "firstenemy")
        self.assertEqual(
            result.audit.type_mapping_details[0]["selected_identity"]["source_kind"],
            IDENTITY_KIND_FANDOM_PAGE_TITLE,
        )

    def test_fandom_fallback_hp_can_resolve_type_by_nanoka_id(self) -> None:
        data = _replace_enemy_row(
            _source_data(),
            0,
            hp_source=HP_SOURCE_FANDOM_ENEMY_PAGE_FALLBACK,
        )

        result = build_abyss_wave_scenario_payload(
            data,
            chamber=1,
            side=1,
            enemy_type_mapping=_enemy_type_mapping(),
        )

        self.assertTrue(result.ready)
        self.assertEqual(
            result.audit.type_mapping_details[0]["selected_identity"]["source_kind"],
            IDENTITY_KIND_NANOKA_MONSTER_ID,
        )

    def test_fandom_fallback_hp_accepts_nanoka_name_registry_resolution(self) -> None:
        data = _replace_enemy_row(
            _source_data(),
            0,
            hp_source=HP_SOURCE_FANDOM_ENEMY_PAGE_FALLBACK,
        )

        result = build_abyss_wave_scenario_payload(
            data,
            chamber=1,
            side=1,
            enemy_type_registry=_registry("firstenemy", "secondenemy"),
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.payload["waves"][0]["targets"][0]["hp"], 100_000.0)
        self.assertEqual(
            result.audit.type_mapping_details[0]["selected_identity"]["source_kind"],
            "nanoka_display_name",
        )

    def test_missing_all_accepted_mappings_reports_available_identities(self) -> None:
        data = _replace_enemy_row(
            _source_data(),
            0,
            nanoka_monster_id=None,
            fandom_enemy_page_url=None,
            matched_nanoka_display_name=None,
        )

        result = build_abyss_wave_scenario_payload(
            data,
            chamber=1,
            side=1,
            enemy_type_mapping=AbyssEnemyTypeMapping(
                records=(
                    AbyssEnemyTypeMappingRecord(
                        source_kind=IDENTITY_KIND_NANOKA_MONSTER_ID,
                        source_id="second",
                        gcsim_type="dummy",
                    ),
                )
            ),
        )

        self.assertFalse(result.ready)
        self.assertEqual(len(result.audit.missing_type_mapping_rows), 1)
        missing_detail = next(
            detail
            for detail in result.audit.type_mapping_details
            if detail["status"] == "missing_mapping"
        )
        self.assertGreater(len(missing_detail["available_identities"]), 0)

    def test_duplicate_mapping_is_ambiguous_not_silently_chosen(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(),
            chamber=1,
            side=1,
            enemy_type_mapping=AbyssEnemyTypeMapping(
                records=(
                    AbyssEnemyTypeMappingRecord(
                        source_kind=IDENTITY_KIND_NANOKA_MONSTER_ID,
                        source_id="first",
                        gcsim_type="dummy",
                    ),
                    AbyssEnemyTypeMappingRecord(
                        source_kind=IDENTITY_KIND_NANOKA_MONSTER_ID,
                        source_id="first",
                        gcsim_type="battlehardenedgroundedgeoshroom",
                    ),
                    AbyssEnemyTypeMappingRecord(
                        source_kind=IDENTITY_KIND_NANOKA_MONSTER_ID,
                        source_id="second",
                        gcsim_type="dummy",
                    ),
                )
            ),
        )

        self.assertFalse(result.ready)
        self.assertEqual(len(result.audit.ambiguous_type_mapping_rows), 1)
        self.assertEqual(
            result.audit.type_mapping_details[0]["status"],
            "ambiguous_mapping",
        )

    def test_load_enemy_type_mapping_from_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "enemy_types.json"
            path.write_text(
                (
                    '{"mapping_name":"tmp_mapping","records":['
                    '{"source_kind":"fandom_page_title","source_id":"First Enemy",'
                    '"gcsim_type":"dummy","source_name":"First Enemy"}]}'
                ),
                encoding="utf-8",
            )
            mapping = load_enemy_type_mapping_from_json(path)

        self.assertEqual(mapping.mapping_name, "tmp_mapping")
        self.assertEqual(mapping.records[0].source_kind, IDENTITY_KIND_FANDOM_PAGE_TITLE)
        self.assertEqual(mapping.records[0].source_id, "First Enemy")

    def test_old_nanoka_mapping_json_still_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "enemy_types.json"
            path.write_text(
                '{"mapping_name":"tmp_mapping","enemy_types_by_nanoka_monster_id":{"first":"dummy"}}',
                encoding="utf-8",
            )
            mapping = load_enemy_type_mapping_from_json(path)

        self.assertEqual(mapping.types_by_nanoka_monster_id["first"], "dummy")

    def test_write_payload_helper_writes_json_only_when_caller_has_payload(self) -> None:
        result = build_abyss_wave_scenario_payload(
            _source_data(),
            chamber=1,
            side=1,
            enemy_type_mapping=_enemy_type_mapping(),
        )
        assert result.payload is not None

        with tempfile.TemporaryDirectory() as tmp:
            path = write_abyss_wave_scenario_payload(
                result.payload,
                Path(tmp) / "scenario.json",
            )
            text = path.read_text(encoding="utf-8")

        self.assertIn('"spawn_policy": "group_clear"', text)


if __name__ == "__main__":
    unittest.main()
