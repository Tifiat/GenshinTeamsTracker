from __future__ import annotations

import unittest

from hoyolab_export.artifact_stats import (
    ATK_PERCENT,
    CRIT_DAMAGE,
    CRIT_RATE,
    ELEMENTAL_MASTERY,
    ENERGY_RECHARGE,
    HP_FLAT,
    HP_PERCENT,
)
from run_workspace.gcsim.config_blocks import (
    CONFIG_BLOCK_MISSING_ARTIFACT_STATS,
    CONFIG_BLOCK_READY,
    WARNING_FORBIDDEN_ARTIFACT_STAT_SOURCE_IGNORED,
    WARNING_ARTIFACT_SET_COUNTS_MISSING,
    GcsimArtifactConfigInput,
    GcsimArtifactSetConfigInput,
    GcsimCharacterConfigInput,
    GcsimWeaponConfigInput,
    build_gcsim_character_config_block,
    render_gcsim_character_config_block,
)
from run_workspace.gcsim.config_readiness import (
    GcsimMappingRef,
    GcsimTalentInput,
    READINESS_MISSING_ARTIFACT_DATA,
    READINESS_MISSING_MAPPING,
    READINESS_MISSING_TALENT_DATA,
    READINESS_UNSUPPORTED_TRAVELER,
    WARNING_DISPLAY_NAME_ONLY_MAPPING,
)


def ready_mapping(key: str) -> GcsimMappingRef:
    return GcsimMappingRef(gcsim_key=key, source="curated_test_fixture")


def ready_artifacts(**overrides) -> GcsimArtifactConfigInput:
    data = {
        "set_counts": (
            GcsimArtifactSetConfigInput(
                set_uid="NoblesseOblige",
                display_name="Noblesse Oblige",
                count=4,
                mapping=ready_mapping("noblesseoblige"),
            ),
        ),
        "stat_totals": (
            {"property_type": HP_FLAT, "raw_value": 4780},
            {"property_type": ATK_PERCENT, "raw_value": 46.6},
            {"property_type": ELEMENTAL_MASTERY, "raw_value": 187},
            {"property_type": ENERGY_RECHARGE, "raw_value": 10.5},
            {"property_type": CRIT_RATE, "raw_value": 31.1},
            {"property_type": CRIT_DAMAGE, "raw_value": 62.2},
        ),
    }
    data.update(overrides)
    return GcsimArtifactConfigInput(**data)


def ready_character(**overrides) -> GcsimCharacterConfigInput:
    data = {
        "project_character_id": "10000021",
        "display_name": "Mona",
        "level": 80,
        "promote_level": 6,
        "constellation": 2,
        "mapping": ready_mapping("mona"),
        "weapon": GcsimWeaponConfigInput(
            project_weapon_id="14405",
            display_name="Favonius Codex",
            level=90,
            refinement=5,
            mapping=ready_mapping("favoniuscodex"),
        ),
        "artifacts": ready_artifacts(),
        "talents": GcsimTalentInput(
            normal=6,
            skill=9,
            burst=10,
            source_order_confirmed=True,
        ),
    }
    data.update(overrides)
    return GcsimCharacterConfigInput(**data)


class GcsimConfigBlocksTest(unittest.TestCase):
    def test_ready_character_block_renders_stable_lines(self) -> None:
        block = build_gcsim_character_config_block(ready_character())

        self.assertTrue(block.ready)
        self.assertEqual(block.status, CONFIG_BLOCK_READY)
        self.assertEqual(
            block.lines,
            (
                "mona char lvl=80/90 cons=2 talent=6,9,10;",
                'mona add weapon="favoniuscodex" refine=5 lvl=90/90;',
                'mona add set="noblesseoblige" count=4;',
                (
                    "mona add stats hp=4780 atk%=0.466 em=187 "
                    "er=0.105 cr=0.311 cd=0.622;"
                ),
            ),
        )
        self.assertEqual(render_gcsim_character_config_block(ready_character()), block.text)

    def test_two_piece_sets_and_five_piece_count_are_preserved(self) -> None:
        block = build_gcsim_character_config_block(
            ready_character(
                artifacts=ready_artifacts(
                    set_counts=(
                        GcsimArtifactSetConfigInput(
                            set_uid="NoblesseOblige",
                            count=2,
                            mapping=ready_mapping("noblesseoblige"),
                        ),
                        GcsimArtifactSetConfigInput(
                            set_uid="EmblemOfSeveredFate",
                            count=2,
                            mapping=ready_mapping("emblemofseveredfate"),
                        ),
                    ),
                )
            )
        )

        self.assertIn('mona add set="noblesseoblige" count=2;', block.lines)
        self.assertIn('mona add set="emblemofseveredfate" count=2;', block.lines)

        five_piece = build_gcsim_character_config_block(
            ready_character(
                artifacts=ready_artifacts(
                    set_counts=(
                        GcsimArtifactSetConfigInput(
                            set_uid="NoblesseOblige",
                            count=5,
                            mapping=ready_mapping("noblesseoblige"),
                        ),
                    ),
                )
            )
        )

        self.assertIn('mona add set="noblesseoblige" count=5;', five_piece.lines)

    def test_display_name_only_mapping_is_not_rendered(self) -> None:
        block = build_gcsim_character_config_block(
            ready_character(
                mapping=GcsimMappingRef(
                    gcsim_key="Mona",
                    source="localized_display_name",
                )
            )
        )

        self.assertFalse(block.ready)
        self.assertEqual(block.status, READINESS_MISSING_MAPPING)
        self.assertEqual(block.lines, ())
        self.assertIn(WARNING_DISPLAY_NAME_ONLY_MAPPING, block.warnings)

    def test_traveler_is_deferred_not_rendered(self) -> None:
        block = build_gcsim_character_config_block(
            ready_character(
                project_character_id="10000007",
                display_name="Traveler",
                mapping=ready_mapping("pyrotraveler"),
            )
        )

        self.assertFalse(block.ready)
        self.assertEqual(block.status, READINESS_UNSUPPORTED_TRAVELER)
        self.assertEqual(block.lines, ())

    def test_missing_talent_order_is_controlled_not_partial_config(self) -> None:
        block = build_gcsim_character_config_block(
            ready_character(
                talents=GcsimTalentInput(normal=6, skill=9, burst=10),
            )
        )

        self.assertFalse(block.ready)
        self.assertEqual(block.status, READINESS_MISSING_TALENT_DATA)
        self.assertEqual(block.lines, ())

    def test_artifact_add_stats_sum_duplicates_and_ignore_forbidden_sources(self) -> None:
        block = build_gcsim_character_config_block(
            ready_character(
                artifacts=ready_artifacts(
                    stat_totals=(
                        {"property_type": HP_FLAT, "raw_value": 10000, "source_kind": "character_base"},
                        {"property_type": HP_FLAT, "raw_value": 4780},
                        {"property_type": HP_PERCENT, "raw_value": 20},
                        {"property_type": HP_PERCENT, "raw_value": 26.6},
                        {"property_type": CRIT_RATE, "raw_value": 31.1},
                    ),
                )
            )
        )

        self.assertTrue(block.ready)
        self.assertEqual(block.add_stats["hp"], 4780)
        self.assertAlmostEqual(block.add_stats["hp%"], 0.466)
        self.assertIn(
            WARNING_FORBIDDEN_ARTIFACT_STAT_SOURCE_IGNORED,
            block.warnings,
        )
        self.assertIn("hp=4780 hp%=0.466 cr=0.311", block.lines[-1])

    def test_no_mappable_artifact_stats_is_not_ready(self) -> None:
        block = build_gcsim_character_config_block(
            ready_character(
                artifacts=ready_artifacts(
                    stat_totals=(
                        {"property_type": 999, "property_name": "Mystery", "raw_value": 1},
                    ),
                )
            )
        )

        self.assertFalse(block.ready)
        self.assertEqual(block.status, CONFIG_BLOCK_MISSING_ARTIFACT_STATS)
        self.assertEqual(block.lines, ())

    def test_missing_artifact_set_counts_are_not_ready(self) -> None:
        block = build_gcsim_character_config_block(
            ready_character(
                artifacts=ready_artifacts(set_counts=()),
            )
        )

        self.assertFalse(block.ready)
        self.assertEqual(block.status, READINESS_MISSING_ARTIFACT_DATA)
        self.assertEqual(block.lines, ())
        self.assertIn(WARNING_ARTIFACT_SET_COUNTS_MISSING, block.warnings)


if __name__ == "__main__":
    unittest.main()
