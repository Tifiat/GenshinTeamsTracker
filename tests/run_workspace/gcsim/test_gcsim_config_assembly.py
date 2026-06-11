from __future__ import annotations

import unittest

from hoyolab_export.artifact_stats import CRIT_RATE, HP_FLAT
from run_workspace.gcsim.config_assembly import (
    ASSEMBLY_BLOCK_NOT_READY,
    ASSEMBLY_READY,
    ASSEMBLY_SHELL_CONTAINS_MANUAL_CHARACTER_BLOCKS,
    CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH,
    WARNING_SHELL_TARGET_PLACEHOLDER_NOT_ENEMY_TRUTH,
    assemble_gcsim_full_config,
    audit_rotation_shell,
)
from run_workspace.gcsim.config_blocks import (
    GcsimArtifactConfigInput,
    GcsimArtifactSetConfigInput,
    GcsimCharacterConfigInput,
    GcsimWeaponConfigInput,
    build_gcsim_character_config_block,
)
from run_workspace.gcsim.config_readiness import (
    GcsimMappingRef,
    GcsimTalentInput,
)


def ready_mapping(key: str) -> GcsimMappingRef:
    return GcsimMappingRef(gcsim_key=key, source="curated_test_fixture")


def character_block(key: str) -> object:
    block = build_gcsim_character_config_block(
        GcsimCharacterConfigInput(
            project_character_id=f"id-{key}",
            display_name=key.title(),
            level=90,
            promote_level=6,
            constellation=0,
            mapping=ready_mapping(key),
            weapon=GcsimWeaponConfigInput(
                project_weapon_id=f"weapon-{key}",
                display_name="Weapon",
                level=90,
                promote_level=6,
                refinement=1,
                mapping=ready_mapping(f"{key}weapon"),
            ),
            artifacts=GcsimArtifactConfigInput(
                set_counts=(
                    GcsimArtifactSetConfigInput(
                        set_uid=f"set-{key}",
                        count=4,
                        mapping=ready_mapping(f"{key}set"),
                    ),
                ),
                stat_totals=(
                    {"property_type": HP_FLAT, "raw_value": 4780},
                    {"property_type": CRIT_RATE, "raw_value": 31.1},
                ),
            ),
            talents=GcsimTalentInput(
                normal=9,
                skill=9,
                burst=9,
                source_order_confirmed=True,
            ),
        )
    )
    assert block.ready
    return block


class GcsimConfigAssemblyTest(unittest.TestCase):
    def test_rotation_shell_fixture_contains_no_manual_blocks(self) -> None:
        shell = CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH.read_text(
            encoding="utf-8"
        )
        audit = audit_rotation_shell(shell)

        self.assertTrue(audit.ready)
        self.assertEqual(audit.status, ASSEMBLY_READY)
        self.assertEqual(audit.manual_block_lines, ())
        self.assertEqual(audit.active_character_key, "furina")
        self.assertIn("target lvl=100", audit.target_placeholder_lines[0])
        self.assertIn(
            WARNING_SHELL_TARGET_PLACEHOLDER_NOT_ENEMY_TRUTH,
            audit.warnings,
        )

    def test_assembler_emits_blocks_then_shell(self) -> None:
        shell = CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH.read_text(
            encoding="utf-8"
        )
        blocks = (
            character_block("chasca"),
            character_block("ororon"),
            character_block("furina"),
            character_block("bennett"),
        )

        result = assemble_gcsim_full_config(blocks, shell, shell_source="fixture")

        self.assertTrue(result.ready)
        self.assertEqual(result.status, ASSEMBLY_READY)
        self.assertTrue(result.config_text.startswith("chasca char lvl=90/90"))
        self.assertLess(
            result.config_text.index("bennett add stats"),
            result.config_text.index("options swap_delay=12"),
        )
        self.assertEqual(
            [summary.character_key for summary in result.block_summaries],
            ["chasca", "ororon", "furina", "bennett"],
        )
        self.assertEqual(result.active_character_key, "furina")
        self.assertIn("target lvl=100 resist=0.1", result.config_text)
        self.assertFalse(result.source_notes["target_line_is_enemy_truth"])

    def test_assembler_does_not_emit_partial_config_for_not_ready_block(self) -> None:
        bad_block = build_gcsim_character_config_block(
            GcsimCharacterConfigInput(
                display_name="Future",
            )
        )

        result = assemble_gcsim_full_config(
            (character_block("mona"), bad_block),
            "options iteration=1;\nactive mona;\n",
        )

        self.assertFalse(result.ready)
        self.assertEqual(result.status, ASSEMBLY_BLOCK_NOT_READY)
        self.assertEqual(result.config_text, "")

    def test_assembler_rejects_shell_with_manual_character_blocks(self) -> None:
        shell = """
options iteration=1;
active bennett;
bennett char lvl=90/90 cons=6 talent=9,9,9;
bennett add stats hp=4780;
"""

        result = assemble_gcsim_full_config((character_block("bennett"),), shell)

        self.assertFalse(result.ready)
        self.assertEqual(
            result.status,
            ASSEMBLY_SHELL_CONTAINS_MANUAL_CHARACTER_BLOCKS,
        )
        self.assertEqual(result.config_text, "")
        self.assertEqual(len(result.shell_audit.manual_block_lines), 2)


if __name__ == "__main__":
    unittest.main()
