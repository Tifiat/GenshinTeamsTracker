from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hoyolab_export.character_stats_catalog import (
    CharacterBaseStatsCatalog,
    build_character_base_stats_catalog,
    parse_character_base_stats_page,
    read_character_base_stats_cache,
)
from hoyolab_export.hoyowiki_catalog_refresh import (
    TRAVELER_HANDLING_NOTE,
    refresh_character_base_stats_catalog,
    refresh_hoyowiki_static_stats_catalogs,
    refresh_weapon_stats_catalog,
)
from hoyolab_export.weapon_stats_catalog import (
    WEAPON_PASSIVE_HANDLING_NOTE,
    read_weapon_stats_cache,
)


def character_page(name: str = "Amber", atk_bonus: str = "0.0%") -> dict:
    return {
        "name": name,
        "modules": [
            {
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
                                            {"key": "ATK", "values": ["-", atk_bonus]},
                                        ],
                                    }
                                ]
                            }
                        ),
                    }
                ]
            }
        ],
    }


def weapon_page(name: str = "Favonius Warbow") -> dict:
    return {
        "name": name,
        "modules": [
            {
                "components": [
                    {
                        "component_id": "baseInfo",
                        "data": json.dumps(
                            {
                                "list": [
                                    {"key": "Type", "value": ["Bow"]},
                                    {
                                        "key": "Secondary Attributes",
                                        "value": ["Energy Recharge"],
                                    },
                                    {
                                        "key": "Windfall",
                                        "value": ["CRIT Hits generate particles."],
                                    },
                                ]
                            }
                        ),
                    },
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
                                                    "ATK before Ascension",
                                                    "ATK after Ascension",
                                                    "Energy Recharge",
                                                ],
                                            },
                                            {"key": "", "values": ["-", "41", "13.3%"]},
                                        ],
                                    }
                                ]
                            }
                        ),
                    },
                ]
            }
        ],
    }


class HoYoWikiCatalogRefreshTest(unittest.TestCase):
    def test_missing_only_skips_existing_valid_character_entry(self) -> None:
        existing_entry = parse_character_base_stats_page(
            character_page(),
            entry_page_id="14",
            language="en-us",
        )

        calls: list[str] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "character_stats_catalog.json"
            result = refresh_character_base_stats_catalog(
                cache_path=cache_path,
                existing_catalog=build_character_base_stats_catalog(
                    [existing_entry],
                    language="en-us",
                ),
                list_fetcher=lambda _lang: [{"entry_page_id": "14", "name": "Amber"}],
                detail_fetcher=lambda entry_id, _lang: calls.append(entry_id) or character_page(),
            )

            cache = read_character_base_stats_cache(cache_path)

        self.assertEqual(calls, [])
        self.assertEqual(result.skipped_existing, 1)
        self.assertEqual(result.fetched, 0)
        self.assertIsNotNone(cache)
        self.assertEqual(cache.entries[0].entry_page_id, "14")

    def test_force_refresh_refetches_existing_character_entry(self) -> None:
        existing_entry = parse_character_base_stats_page(
            character_page(atk_bonus="0.0%"),
            entry_page_id="14",
            language="en-us",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "character_stats_catalog.json"
            result = refresh_character_base_stats_catalog(
                cache_path=cache_path,
                existing_catalog=build_character_base_stats_catalog(
                    [existing_entry],
                    language="en-us",
                ),
                force_refresh=True,
                list_fetcher=lambda _lang: [{"entry_page_id": "14", "name": "Amber"}],
                detail_fetcher=lambda _entry_id, _lang: character_page(atk_bonus="6.0%"),
            )
            cache = read_character_base_stats_cache(cache_path)

        self.assertEqual(result.skipped_existing, 0)
        self.assertEqual(result.fetched, 1)
        self.assertEqual(
            cache.entries[0].rows[0].ascension_bonus.after,
            "6.0%",
        )

    def test_stale_character_catalog_metadata_forces_refresh(self) -> None:
        existing_entry = parse_character_base_stats_page(
            character_page(atk_bonus="0.0%"),
            entry_page_id="14",
            language="en-us",
        )
        stale_catalog = CharacterBaseStatsCatalog(
            entries=(existing_entry,),
            lang="en-us",
            parser_version=0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = refresh_character_base_stats_catalog(
                cache_path=Path(temp_dir) / "character_stats_catalog.json",
                existing_catalog=stale_catalog,
                list_fetcher=lambda _lang: [{"entry_page_id": "14", "name": "Amber"}],
                detail_fetcher=lambda _entry_id, _lang: character_page(atk_bonus="6.0%"),
            )

        self.assertEqual(result.skipped_existing, 0)
        self.assertEqual(result.fetched, 1)

    def test_failed_entry_is_reported_and_existing_cache_is_preserved(self) -> None:
        existing_entry = parse_character_base_stats_page(
            character_page(),
            entry_page_id="14",
            language="en-us",
        )

        def failing_detail_fetcher(_entry_id: str, _lang: str) -> dict:
            raise RuntimeError("network unavailable")

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "character_stats_catalog.json"
            result = refresh_character_base_stats_catalog(
                cache_path=cache_path,
                existing_catalog=build_character_base_stats_catalog(
                    [existing_entry],
                    language="en-us",
                ),
                force_refresh=True,
                list_fetcher=lambda _lang: [{"entry_page_id": "14", "name": "Amber"}],
                detail_fetcher=failing_detail_fetcher,
            )
            cache = read_character_base_stats_cache(cache_path)

        self.assertEqual(result.failed, 1)
        self.assertEqual(result.preserved_existing_after_failure, 1)
        self.assertEqual(cache.entries[0].entry_page_id, "14")

    def test_traveler_variant_is_catalog_entry_not_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "character_stats_catalog.json"
            result = refresh_character_base_stats_catalog(
                cache_path=cache_path,
                list_fetcher=lambda _lang: [
                    {"entry_page_id": "7306", "name": "Pyro Traveler"}
                ],
                detail_fetcher=lambda _entry_id, _lang: character_page("Pyro Traveler"),
            )
            cache = read_character_base_stats_cache(cache_path)

        self.assertEqual(result.fetched, 1)
        self.assertEqual(cache.entries[0].entry_page_id, "7306")
        self.assertEqual(cache.entries[0].name, "Pyro Traveler")

    def test_weapon_refresh_keeps_passive_text_as_reference_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "weapon_stats_catalog.json"
            result = refresh_weapon_stats_catalog(
                cache_path=cache_path,
                list_fetcher=lambda _lang: [
                    {"entry_page_id": "2019", "name": "Favonius Warbow"}
                ],
                detail_fetcher=lambda _entry_id, _lang: weapon_page(),
            )
            cache = read_weapon_stats_cache(cache_path)

        self.assertEqual(result.fetched, 1)
        entry = cache.entries[0]
        self.assertEqual(entry.reference_info.passive_fields[0].key, "Windfall")
        self.assertFalse(hasattr(entry, "modeled_passive_effects"))
        self.assertFalse(hasattr(entry.rows[0], "passive_stat_bonuses"))

    def test_combined_summary_contains_static_lifecycle_notes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = refresh_hoyowiki_static_stats_catalogs(
                character_cache_path=Path(temp_dir) / "character_stats_catalog.json",
                weapon_cache_path=Path(temp_dir) / "weapon_stats_catalog.json",
                character_list_fetcher=lambda _lang: [
                    {"entry_page_id": "14", "name": "Amber"}
                ],
                weapon_list_fetcher=lambda _lang: [
                    {"entry_page_id": "2019", "name": "Favonius Warbow"}
                ],
                detail_fetcher=lambda entry_id, _lang: (
                    character_page() if entry_id == "14" else weapon_page()
                ),
            )

        data = summary.to_dict()
        self.assertEqual(data["language"], "en-us")
        self.assertIn(TRAVELER_HANDLING_NOTE, data["notes"])
        self.assertIn(WEAPON_PASSIVE_HANDLING_NOTE, data["notes"])
        self.assertEqual(data["character"]["fetched"], 1)
        self.assertEqual(data["weapon"]["fetched"], 1)


if __name__ == "__main__":
    unittest.main()
