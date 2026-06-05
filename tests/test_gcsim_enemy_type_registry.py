from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from run_workspace.gcsim.enemy_type_registry import (
    GcsimEnemyNameCandidate,
    GcsimEnemyTypeRegistry,
    MATCH_METHOD_AMBIGUOUS,
    MATCH_METHOD_COMPATIBLE_BASE_NAME,
    MATCH_METHOD_EXACT_NORMALIZED_NAME,
    MATCH_METHOD_MANUAL_ALIAS,
    load_gcsim_enemy_type_registry_from_go_source,
    normalize_gcsim_enemy_name,
)


class GcsimEnemyTypeRegistryTest(unittest.TestCase):
    def test_loads_target_types_from_go_shortcut_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "enemies_gen.go"
            path.write_text(
                'package shortcut\nvar MonsterNameToID = map[string]int{\n'
                '\t"groundedgeoshroom": 26120401,\n'
                '\t"battlehardenedgroundedgeoshroom": 26120501,\n'
                "}\n",
                encoding="utf-8",
            )

            registry = load_gcsim_enemy_type_registry_from_go_source(path)

        self.assertIn("groundedgeoshroom", registry.target_types)
        self.assertIn("dummy", registry.target_types)

    def test_exact_normalized_match(self) -> None:
        registry = GcsimEnemyTypeRegistry(("groundedgeoshroom",))

        match = registry.match_name_candidates(
            (GcsimEnemyNameCandidate("fandom_page_title", "Grounded Geoshroom"),)
        )

        self.assertEqual(match.method, MATCH_METHOD_EXACT_NORMALIZED_NAME)
        self.assertEqual(match.gcsim_type, "groundedgeoshroom")

    def test_compatible_base_match_strips_variant_token(self) -> None:
        registry = GcsimEnemyTypeRegistry(("groundedgeoshroom",))

        match = registry.match_name_candidates(
            (
                GcsimEnemyNameCandidate(
                    "fandom_page_title",
                    "Battle-Hardened Grounded Geoshroom",
                ),
            )
        )

        self.assertEqual(match.method, MATCH_METHOD_COMPATIBLE_BASE_NAME)
        self.assertEqual(match.gcsim_type, "groundedgeoshroom")

    def test_ambiguous_compatible_base_match_is_not_chosen(self) -> None:
        registry = GcsimEnemyTypeRegistry(
            (
                "battlehardenedgroundedgeoshroom",
                "veterangroundedgeoshroom",
            )
        )

        match = registry.match_name_candidates(
            (GcsimEnemyNameCandidate("fandom_page_title", "Grounded Geoshroom"),)
        )

        self.assertEqual(match.method, MATCH_METHOD_AMBIGUOUS)
        self.assertEqual(
            match.ambiguous_types,
            ("battlehardenedgroundedgeoshroom", "veterangroundedgeoshroom"),
        )

    def test_manual_alias_is_small_explicit_exception_layer(self) -> None:
        registry = GcsimEnemyTypeRegistry(
            ("legatusgolem",),
            manual_aliases={normalize_gcsim_enemy_name("Statue of Marble and Brass"): "legatusgolem"},
        )

        match = registry.match_name_candidates(
            (
                GcsimEnemyNameCandidate(
                    "fandom_page_title",
                    "Statue of Marble and Brass",
                ),
            )
        )

        self.assertEqual(match.method, MATCH_METHOD_MANUAL_ALIAS)
        self.assertEqual(match.gcsim_type, "legatusgolem")


if __name__ == "__main__":
    unittest.main()
