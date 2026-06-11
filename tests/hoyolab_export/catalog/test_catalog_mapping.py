from __future__ import annotations

import unittest

from hoyolab_export.catalog_mapping import (
    STATUS_AMBIGUOUS,
    STATUS_MATCHED,
    STATUS_UNMATCHED,
    WARNING_DIRECT_ID_EQUAL_UNVERIFIED,
    WARNING_DUPLICATE_ACCOUNT_VARIANT,
    WARNING_LANGUAGE_MISMATCH,
    WARNING_RARITY_MISSING,
    WARNING_WEAPON_TYPE_MISMATCH,
    map_character_catalog,
    map_weapon_catalog,
    normalize_catalog_name,
)


class CatalogMappingTest(unittest.TestCase):
    def test_normalized_character_name_match_with_cross_checks(self) -> None:
        result = map_character_catalog(
            [
                {
                    "id": 10000021,
                    "name": "Amber",
                    "element": "Pyro",
                    "rarity": 4,
                    "level": 90,
                    "constellation": 6,
                }
            ],
            [
                {
                    "entry_page_id": "14",
                    "name": "Amber",
                    "lang": "en-us",
                    "element": "Pyro",
                    "rarity": "4-Star",
                }
            ],
            account_language="en-us",
        )

        self.assertEqual(result.total, 1)
        self.assertEqual(result.matched_count, 1)
        entry = result.entries[0]
        self.assertEqual(entry.status, STATUS_MATCHED)
        self.assertEqual(entry.matches[0].source_id, "14")
        self.assertEqual(entry.warnings, ())

    def test_character_filter_values_are_used_for_cross_checks(self) -> None:
        result = map_character_catalog(
            [{"id": 10000021, "name": "Амбер", "element": "Pyro", "rarity": 4}],
            [
                {
                    "entry_page_id": "14",
                    "name": "Амбер",
                    "filter_values": {
                        "character_vision": {"values": ["Пиро"]},
                        "character_rarity": {"values": ["4★"]},
                    },
                }
            ],
            account_language="ru-ru",
        )

        self.assertEqual(result.entries[0].status, STATUS_MATCHED)
        self.assertEqual(result.entries[0].warnings, ())

    def test_character_unmatched(self) -> None:
        result = map_character_catalog(
            [{"id": 1, "name": "Missing Character", "element": "Pyro"}],
            [{"entry_page_id": "14", "name": "Amber", "element": "Pyro"}],
        )

        self.assertEqual(result.unmatched_count, 1)
        self.assertEqual(result.entries[0].status, STATUS_UNMATCHED)

    def test_character_ambiguous_match(self) -> None:
        result = map_character_catalog(
            [{"id": 1, "name": "Traveler", "element": "Anemo"}],
            [
                {"entry_page_id": "1", "name": "Traveler", "element": "Anemo"},
                {"entry_page_id": "2", "name": "Traveler", "element": "Anemo"},
            ],
        )

        self.assertEqual(result.ambiguous_count, 1)
        self.assertEqual(result.entries[0].status, STATUS_AMBIGUOUS)
        self.assertEqual(len(result.entries[0].matches), 2)

    def test_character_language_mismatch_warning(self) -> None:
        result = map_character_catalog(
            [{"id": 1, "name": "Amber", "element": "Pyro"}],
            [{"entry_page_id": "14", "name": "Amber", "lang": "en-us", "element": "Pyro"}],
            account_language="ru-ru",
        )

        self.assertEqual(result.entries[0].status, STATUS_MATCHED)
        self.assertIn(WARNING_LANGUAGE_MISMATCH, result.entries[0].warnings)

    def test_direct_id_equal_is_diagnostic_not_primary_method(self) -> None:
        result = map_character_catalog(
            [{"id": "14", "name": "Amber", "element": "Pyro"}],
            [{"entry_page_id": "14", "name": "Amber", "element": "Pyro"}],
        )

        entry = result.entries[0]
        self.assertEqual(entry.status, STATUS_MATCHED)
        self.assertEqual(entry.match_method, "normalized_name")
        self.assertIn(WARNING_DIRECT_ID_EQUAL_UNVERIFIED, entry.warnings)

    def test_weapon_name_type_rarity_match(self) -> None:
        result = map_weapon_catalog(
            [
                {
                    "id": 15403,
                    "name": "Favonius Warbow",
                    "rarity": 4,
                    "type_name": "bow",
                    "level": 90,
                    "refinement": 5,
                }
            ],
            [
                {
                    "entry_page_id": "2019",
                    "name": "Favonius Warbow",
                    "lang": "en-us",
                    "filter_values": {
                        "weapon_type": {"values": ["Bow"]},
                        "weapon_rarity": {"values": ["4-Star"]},
                    },
                }
            ],
            account_language="en-us",
        )

        self.assertEqual(result.matched_count, 1)
        entry = result.entries[0]
        self.assertEqual(entry.status, STATUS_MATCHED)
        self.assertEqual(entry.matches[0].source_id, "2019")
        self.assertEqual(entry.warnings, ())

    def test_weapon_localized_filter_values_are_used_for_cross_checks(self) -> None:
        result = map_weapon_catalog(
            [{"id": 15403, "name": "Боевой лук Фавония", "rarity": 4, "type_name": "bow"}],
            [
                {
                    "entry_page_id": "2019",
                    "name": "Боевой лук Фавония",
                    "filter_values": {
                        "weapon_type": {"values": ["Лук"]},
                        "weapon_rarity": {"values": ["4★"]},
                    },
                }
            ],
            account_language="ru-ru",
        )

        self.assertEqual(result.entries[0].status, STATUS_MATCHED)
        self.assertEqual(result.entries[0].warnings, ())

    def test_weapon_unmatched(self) -> None:
        result = map_weapon_catalog(
            [{"id": 1, "name": "Missing Sword", "type_name": "sword"}],
            [{"entry_page_id": "2019", "name": "Favonius Warbow", "type": "Bow"}],
        )

        self.assertEqual(result.unmatched_count, 1)
        self.assertEqual(result.entries[0].status, STATUS_UNMATCHED)

    def test_weapon_ambiguous_match(self) -> None:
        result = map_weapon_catalog(
            [{"id": 1, "name": "Twin Blade", "type_name": "sword", "rarity": 4}],
            [
                {"entry_page_id": "10", "name": "Twin Blade", "type": "Sword", "rarity": 4},
                {"entry_page_id": "11", "name": "Twin Blade", "type": "Sword", "rarity": 4},
            ],
        )

        self.assertEqual(result.ambiguous_count, 1)
        self.assertEqual(result.entries[0].status, STATUS_AMBIGUOUS)

    def test_weapon_cross_check_mismatch_stays_visible(self) -> None:
        result = map_weapon_catalog(
            [{"id": 1, "name": "Favonius Warbow", "type_name": "sword", "rarity": 4}],
            [{"entry_page_id": "2019", "name": "Favonius Warbow", "type": "Bow", "rarity": 4}],
        )

        self.assertEqual(result.entries[0].status, STATUS_MATCHED)
        self.assertIn(WARNING_WEAPON_TYPE_MISMATCH, result.entries[0].warnings)

    def test_duplicate_identical_weapon_variants_are_warned_not_blocked(self) -> None:
        result = map_weapon_catalog(
            [
                {
                    "id": 1,
                    "name": "Favonius Warbow",
                    "type_name": "bow",
                    "rarity": 4,
                    "level": 90,
                    "refinement": 5,
                },
                {
                    "id": 2,
                    "name": "Favonius Warbow",
                    "type_name": "bow",
                    "rarity": 4,
                    "level": 90,
                    "refinement": 5,
                },
            ],
            [{"entry_page_id": "2019", "name": "Favonius Warbow", "type": "Bow", "rarity": 4}],
        )

        self.assertEqual(result.matched_count, 2)
        self.assertIn(WARNING_DUPLICATE_ACCOUNT_VARIANT, result.entries[0].warnings)
        self.assertIn(WARNING_DUPLICATE_ACCOUNT_VARIANT, result.entries[1].warnings)

    def test_report_summary_totals(self) -> None:
        result = map_character_catalog(
            [
                {"id": 1, "name": "Amber", "element": "Pyro"},
                {"id": 2, "name": "Missing", "element": "Hydro"},
            ],
            [{"entry_page_id": "14", "name": "Amber", "element": "Pyro"}],
        )

        report = result.to_report(examples_per_status=1)

        self.assertEqual(report["total"], 2)
        self.assertEqual(report["matched"], 1)
        self.assertEqual(report["unmatched"], 1)
        self.assertEqual(report["ambiguous"], 0)
        self.assertEqual(len(report["examples"][STATUS_MATCHED]), 1)
        self.assertEqual(len(report["examples"][STATUS_UNMATCHED]), 1)
        self.assertIn(WARNING_RARITY_MISSING, report["warnings"])

    def test_normalize_catalog_name_handles_case_punctuation_and_yo(self) -> None:
        self.assertEqual(
            normalize_catalog_name("  Ё-Name!  "),
            "е name",
        )


if __name__ == "__main__":
    unittest.main()
