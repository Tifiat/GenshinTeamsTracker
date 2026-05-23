from __future__ import annotations

import json
import unittest

from hoyolab_export.character_stats_catalog import (
    WARNING_MALFORMED_ASCENSION_COMPONENT,
    WARNING_MISSING_ASCENSION_COMPONENT,
    build_character_base_stats_catalog,
    parse_character_base_stats_page,
)
from hoyolab_export.hoyowiki_client import (
    find_first_hoyowiki_component,
    parse_hoyowiki_component_data,
)


def sample_character_page() -> dict:
    return {
        "name": "Amber",
        "modules": [
            {
                "name": "Ascend",
                "components": [
                    {
                        "component_id": "ascension",
                        "data": json.dumps(
                            {
                                "list": [
                                    {
                                        "key": "Lv.1",
                                        "combatList": [
                                            {
                                                "key": "",
                                                "values": [
                                                    "Before Ascension",
                                                    "After Ascension",
                                                ],
                                            },
                                            {"key": "Base HP", "values": ["-", "793"]},
                                            {"key": "Base ATK", "values": ["-", "19"]},
                                            {"key": "Base DEF", "values": ["-", "50"]},
                                            {"key": "ATK", "values": ["-", "0.0%"]},
                                        ],
                                    },
                                    {
                                        "key": "Lv.40",
                                        "combatList": [
                                            {
                                                "key": "",
                                                "values": [
                                                    "Before Ascension",
                                                    "After Ascension",
                                                ],
                                            },
                                            {"key": "Base HP", "values": ["3940", "4361"]},
                                            {"key": "Base ATK", "values": ["93", "103"]},
                                            {"key": "Base DEF", "values": ["250", "277"]},
                                            {"key": "ATK", "values": ["0.0%", "6.0%"]},
                                        ],
                                    },
                                ]
                            }
                        ),
                    }
                ],
            }
        ],
    }


class HoYoWikiClientHelpersTest(unittest.TestCase):
    def test_find_component_and_parse_json_string_data(self) -> None:
        page = sample_character_page()
        component = find_first_hoyowiki_component(page, "ascension")

        self.assertIsNotNone(component)
        parsed = parse_hoyowiki_component_data(component["data"])

        self.assertIsInstance(parsed, dict)
        self.assertEqual(len(parsed["list"]), 2)


class CharacterStatsCatalogTest(unittest.TestCase):
    def test_parse_character_base_stats_and_ascension_bonus_separately(self) -> None:
        entry = parse_character_base_stats_page(
            sample_character_page(),
            entry_page_id="14",
            language="en-us",
        )

        self.assertEqual(entry.entry_page_id, "14")
        self.assertEqual(entry.name, "Amber")
        self.assertEqual(entry.warnings, ())
        self.assertEqual(len(entry.rows), 2)

        first = entry.rows[0]
        self.assertEqual(first.level_key, "Lv.1")
        self.assertIsNone(first.base_hp.before)
        self.assertEqual(first.base_hp.after, "793")
        self.assertEqual(first.base_atk.after, "19")
        self.assertEqual(first.base_def.after, "50")
        self.assertEqual(first.ascension_bonus_stat_type, "ATK")
        self.assertEqual(first.ascension_bonus.after, "0.0%")

        second = entry.rows[1]
        self.assertEqual(second.base_atk.before, "93")
        self.assertEqual(second.base_atk.after, "103")
        self.assertEqual(second.ascension_bonus_stat_type, "ATK")
        self.assertEqual(second.ascension_bonus.before, "0.0%")
        self.assertEqual(second.ascension_bonus.after, "6.0%")

    def test_missing_ascension_component_returns_warning(self) -> None:
        entry = parse_character_base_stats_page(
            {"name": "No Stats", "modules": []},
            entry_page_id="999",
        )

        self.assertEqual(entry.rows, ())
        self.assertIn(WARNING_MISSING_ASCENSION_COMPONENT, entry.warnings)

    def test_malformed_ascension_component_returns_warning(self) -> None:
        entry = parse_character_base_stats_page(
            {
                "name": "Broken",
                "modules": [
                    {
                        "components": [
                            {
                                "component_id": "ascension",
                                "data": "{not json",
                            }
                        ]
                    }
                ],
            },
            entry_page_id="1000",
        )

        self.assertEqual(entry.rows, ())
        self.assertIn(WARNING_MALFORMED_ASCENSION_COMPONENT, entry.warnings)

    def test_catalog_cache_shape_is_serializable(self) -> None:
        entry = parse_character_base_stats_page(
            sample_character_page(),
            entry_page_id="14",
            language="en-us",
        )
        catalog = build_character_base_stats_catalog(
            [entry],
            language="en-us",
            fetched_at="2026-05-17T00:00:00+00:00",
        )
        data = catalog.to_dict()

        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["source"], "hoyowiki")
        self.assertEqual(data["lang"], "en-us")
        self.assertEqual(data["entries"][0]["rows"][0]["base_hp"]["after"], "793")
        self.assertEqual(
            data["entries"][0]["rows"][0]["ascension_bonus"]["after"],
            "0.0%",
        )
        json.dumps(data)


if __name__ == "__main__":
    unittest.main()
