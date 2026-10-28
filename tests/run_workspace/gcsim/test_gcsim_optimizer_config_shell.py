from __future__ import annotations

import hashlib
import unittest

from run_workspace.gcsim.artifact_set_catalog import (
    GcsimArtifactSetCapability,
    GcsimArtifactSetCatalog,
)
from run_workspace.gcsim.config_structure import build_gcsim_structural_view
from run_workspace.gcsim.optimizer_config_shell import (
    GCSIM_OPTIMIZER_ARTIFACT_BLOCK_MARKER,
    build_gcsim_optimizer_config_shell,
)
from run_workspace.gcsim.optimizer_engine_context import (
    GcsimOptimizerEngineContext,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimOptimizerSourceSimulationIdentity,
    GcsimOptimizerWearerIdentity,
)


_HASH = "1" * 64


class GcsimOptimizerConfigShellTests(unittest.TestCase):
    def test_removes_only_four_artifact_blocks_and_extracts_active_sets(self) -> None:
        config = _prepared_config()
        result = build_gcsim_optimizer_config_shell(
            config,
            source_simulation=_source_identity(config),
            engine_context=_engine_context(),
        )

        self.assertTrue(result.ready)
        shell = result.shell
        assert shell is not None
        self.assertEqual(
            shell.config_text.count(GCSIM_OPTIMIZER_ARTIFACT_BLOCK_MARKER),
            4,
        )
        structural_shell = build_gcsim_structural_view(shell.config_text)
        self.assertNotIn(" add set=", structural_shell)
        self.assertNotIn(" add stats ", structural_shell)
        self.assertIn(
            '# harmless text: "furina add stats hp=999999;"',
            shell.config_text,
        )
        self.assertIn("active furina;", shell.config_text)
        self.assertIn("furina skill;", shell.config_text)
        self.assertIn("options iteration=1000 swap_delay=12;", shell.config_text)
        self.assertIn(
            "target lvl=100 resist=0.1 hp=999999999;",
            shell.config_text,
        )
        self.assertNotIn("hp=4780", shell.config_text)
        suggestions = [
            (
                item.wearer.gcsim_character_key,
                item.gcsim_set_key,
                item.source_count,
                dict(item.set_parameters),
                item.mapping_status,
            )
            for item in shell.source_set_suggestions
        ]
        self.assertEqual(
            suggestions,
            [
                ("chasca", "obsidiancodex", 4, {"stacks": 4}, "ready"),
                ("ororon", "deepwoodmemories", 2, {}, "ready"),
                ("ororon", "emblemofseveredfate", 2, {}, "unmodeled"),
                ("furina", "goldentroupe", 5, {}, "ready"),
                ("bennett", "unknownset", 4, {}, "unmapped"),
            ],
        )
        self.assertNotIn(
            "gladiatorsfinale",
            [item.gcsim_set_key for item in shell.source_set_suggestions],
        )
        self.assertEqual(
            tuple(block.source_set_row_count for block in shell.artifact_blocks),
            (1, 2, 1, 2),
        )
        self.assertEqual(
            tuple(block.source_stats_row_count for block in shell.artifact_blocks),
            (1, 1, 1, 1),
        )

    def test_config_identity_mismatch_is_rejected_before_rewrite(self) -> None:
        config = _prepared_config()
        result = build_gcsim_optimizer_config_shell(
            config + "\n",
            source_simulation=_source_identity(config),
            engine_context=_engine_context(),
        )

        self.assertFalse(result.ready)
        self.assertEqual(result.issues[0].code, "source_config_identity_mismatch")

    def test_noncontiguous_artifact_block_is_rejected(self) -> None:
        config = _prepared_config().replace(
            'chasca add set="obsidiancodex" count=4 +params=[stacks=4];\n'
            "chasca add stats hp=4780 atk=311;\n",
            'chasca add set="obsidiancodex" count=4 +params=[stacks=4];\n'
            "# a non-artifact row splits the block\n"
            "chasca add stats hp=4780 atk=311;\n",
        )

        result = build_gcsim_optimizer_config_shell(
            config,
            source_simulation=_source_identity(config),
            engine_context=_engine_context(),
        )

        self.assertFalse(result.ready)
        self.assertEqual(result.issues[0].code, "source_artifact_block_noncontiguous")

    def test_orphan_equipment_row_is_rejected(self) -> None:
        config = _prepared_config().replace(
            "active furina;",
            "traveler add stats hp=1;\nactive furina;",
        )

        result = build_gcsim_optimizer_config_shell(
            config,
            source_simulation=_source_identity(config),
            engine_context=_engine_context(),
        )

        self.assertFalse(result.ready)
        self.assertEqual(result.issues[0].code, "source_equipment_orphan_character")

    def test_duplicate_stats_and_marker_collision_are_rejected(self) -> None:
        duplicate = _prepared_config().replace(
            "chasca add stats hp=4780 atk=311;",
            "chasca add stats hp=4780 atk=311;\nchasca add stats cr=0.1;",
        )
        duplicate_result = build_gcsim_optimizer_config_shell(
            duplicate,
            source_simulation=_source_identity(duplicate),
            engine_context=_engine_context(),
        )
        collision = _prepared_config() + (
            f"# {GCSIM_OPTIMIZER_ARTIFACT_BLOCK_MARKER}\n"
        )
        collision_result = build_gcsim_optimizer_config_shell(
            collision,
            source_simulation=_source_identity(collision),
            engine_context=_engine_context(),
        )

        self.assertFalse(duplicate_result.ready)
        self.assertEqual(
            duplicate_result.issues[0].code,
            "source_stats_row_count_invalid",
        )
        self.assertFalse(collision_result.ready)
        self.assertEqual(
            collision_result.issues[0].code,
            "source_config_marker_collision",
        )


def _prepared_config() -> str:
    return (
        "chasca char lvl=90/90 cons=0 talent=9,9,9;\n"
        'chasca add weapon="chainbreaker" refine=1 lvl=90/90;\n'
        'chasca add set="obsidiancodex" count=4 +params=[stacks=4];\n'
        "chasca add stats hp=4780 atk=311;\n"
        "\n"
        "ororon char lvl=90/90 cons=6 talent=1,9,9;\n"
        'ororon add weapon="thestringless" refine=1 lvl=90/90;\n'
        'ororon add set="deepwoodmemories" count=2;\n'
        'ororon add set="emblemofseveredfate" count=2;\n'
        "ororon add stats hp=4780 atk=311;\n"
        "\n"
        "furina char lvl=90/90 cons=0 talent=9,9,9;\n"
        'furina add weapon="favoniussword" refine=1 lvl=90/90;\n'
        'furina add set="goldentroupe" count=5;\n'
        "furina add stats hp=4780 cr=0.311;\n"
        "\n"
        "bennett char lvl=90/90 cons=6 talent=1,9,10;\n"
        'bennett add weapon="sapwoodblade" refine=1 lvl=90/90;\n'
        'bennett add set="unknownset" count=4;\n'
        'bennett add set="gladiatorsfinale" count=1;\n'
        "bennett add stats hp=4780 er=0.518;\n"
        "\n"
        '# harmless text: "furina add stats hp=999999;"\n'
        "options iteration=1000 swap_delay=12;\n"
        "target lvl=100 resist=0.1 hp=999999999;\n"
        "active furina;\n"
        "furina skill;\n"
    )


def _source_identity(config: str) -> GcsimOptimizerSourceSimulationIdentity:
    return GcsimOptimizerSourceSimulationIdentity(
        engine_id="test-engine",
        engine_version="test-version",
        optimizer_contract_version="test-contract",
        artifact_sha256="2" * 64,
        engine_tree_sha256="3" * 64,
        engine_binding_sha256="4" * 64,
        catalog_fingerprint="5" * 64,
        prepared_config_sha256=hashlib.sha256(config.encode("utf-8")).hexdigest(),
        rotation_sha256="6" * 64,
        target_sha256="7" * 64,
        simulation_options_sha256="8" * 64,
        wearers=tuple(
            GcsimOptimizerWearerIdentity(index, 1000 + index, key)
            for index, key in enumerate(
                ("chasca", "ororon", "furina", "bennett"),
                start=1,
            )
        ),
    )


def _engine_context() -> GcsimOptimizerEngineContext:
    capabilities = (
        _capability("obsidiancodex", two=True, four=True),
        _capability("deepwoodmemories", two=True, four=True),
        _capability("emblemofseveredfate", two=False, four=True),
        _capability("goldentroupe", two=True, four=True),
        _capability("gladiatorsfinale", two=True, four=True),
    )
    catalog = GcsimArtifactSetCatalog(
        source_root="test",
        source_fingerprint="5" * 64,
        sets=capabilities,
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


def _capability(
    key: str,
    *,
    two: bool,
    four: bool,
) -> GcsimArtifactSetCapability:
    return GcsimArtifactSetCapability(
        key=key,
        package_name=key,
        key_constant=key.title(),
        max_rarity=5,
        registered=True,
        has_two_piece_code=two,
        has_four_piece_code=four,
        two_piece_modeled=two,
        four_piece_modeled=four,
    )


if __name__ == "__main__":
    unittest.main()
