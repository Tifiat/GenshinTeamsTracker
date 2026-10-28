from __future__ import annotations

import json
import unittest

from hoyolab_export.weapon_stats_catalog import (
    WEAPON_PASSIVE_HANDLING_NOTE,
    WARNING_MALFORMED_ASCENSION_COMPONENT,
    WARNING_MISSING_ASCENSION_COMPONENT,
    build_weapon_stats_catalog,
    parse_weapon_stats_page,
)


def sample_weapon_page() -> dict:
    return {
        "name": "Favonius Warbow",
        "modules": [
            {
                "name": "Attributes",
                "components": [
                    {
                        "component_id": "baseInfo",
                        "data": json.dumps(
                            {
                                "list": [
                                    {
                                        "key": "Name",
                                        "value": ["Favonius Warbow"],
                                    },
                                    {
                                        "key": "Type",
                                        "value": ["<p>Bow</p>"],
                                    },
                                    {
                                        "key": "Secondary Attributes",
                                        "value": ["<p>Energy Recharge</p>"],
                                    },
                                    {
                                        "key": "Windfall",
                                        "value": [
                                            "<p>CRIT Hits have a <span>60%/70%</span> "
                                            "chance to generate particles.</p>"
                                        ],
                                    },
                                ]
                            }
                        ),
                    }
                ],
            },
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
                                                    "ATK before Ascension",
                                                    "ATK after Ascension",
                                                    "Energy Recharge",
                                                ],
                                            },
                                            {
                                                "key": "",
                                                "values": ["-", "41", "13.3%"],
                                            },
                                        ],
                                    },
                                    {
                                        "key": "Lv.20",
                                        "combatList": [
                                            {
                                                "key": "",
                                                "values": [
                                                    "ATK before Ascension",
                                                    "ATK after Ascension",
                                                    "Energy Recharge",
                                                ],
                                            },
                                            {
                                                "key": "",
                                                "values": ["99", "125", "23.6%"],
                                            },
                                        ],
                                    },
                                ]
                            }
                        ),
                    }
                ],
            },
        ],
    }


class WeaponStatsCatalogTest(unittest.TestCase):
    def test_parse_weapon_base_atk_and_secondary_stat(self) -> None:
        entry = parse_weapon_stats_page(
            sample_weapon_page(),
            entry_page_id="2019",
            language="en-us",
        )

        self.assertEqual(entry.entry_page_id, "2019")
        self.assertEqual(entry.name, "Favonius Warbow")
        self.assertEqual(entry.warnings, ())
        self.assertEqual(entry.reference_info.weapon_type, "Bow")
        self.assertEqual(entry.reference_info.secondary_attribute, "Energy Recharge")
        self.assertEqual(len(entry.rows), 2)

        first = entry.rows[0]
        self.assertEqual(first.level_key, "Lv.1")
        self.assertIsNone(first.base_atk.before)
        self.assertEqual(first.base_atk.after, "41")
        self.assertEqual(first.secondary_stat_type, "Energy Recharge")
        self.assertEqual(first.secondary_stat_value, "13.3%")

        second = entry.rows[1]
        self.assertEqual(second.base_atk.before, "99")
        self.assertEqual(second.base_atk.after, "125")
        self.assertEqual(second.secondary_stat_value, "23.6%")

    def test_passive_text_is_stored_only_as_reference(self) -> None:
        entry = parse_weapon_stats_page(sample_weapon_page(), entry_page_id="2019")

        self.assertEqual(len(entry.reference_info.passive_fields), 1)
        passive = entry.reference_info.passive_fields[0]
        self.assertEqual(passive.key, "Windfall")
        self.assertIn("60%/70%", passive.values[0])

        row = entry.rows[0]
        self.assertFalse(hasattr(row, "passive_stat_bonuses"))
        self.assertFalse(hasattr(entry, "modeled_passive_effects"))

    def test_missing_ascension_component_returns_warning(self) -> None:
        entry = parse_weapon_stats_page(
            {"name": "No Stats", "modules": []},
            entry_page_id="999",
        )

        self.assertEqual(entry.rows, ())
        self.assertIn(WARNING_MISSING_ASCENSION_COMPONENT, entry.warnings)

    def test_malformed_ascension_component_returns_warning(self) -> None:
        entry = parse_weapon_stats_page(
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
        entry = parse_weapon_stats_page(
            sample_weapon_page(),
            entry_page_id="2019",
            language="en-us",
        )
        catalog = build_weapon_stats_catalog(
            [entry],
            language="en-us",
            fetched_at="2026-05-17T00:00:00+00:00",
        )
        data = catalog.to_dict()

        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["source"], "hoyowiki")
        self.assertEqual(data["lang"], "en-us")
        self.assertEqual(data["passive_handling"], WEAPON_PASSIVE_HANDLING_NOTE)
        self.assertEqual(data["entries"][0]["rows"][0]["base_atk"]["after"], "41")
        self.assertEqual(
            data["entries"][0]["rows"][0]["secondary_stat_value"],
            "13.3%",
        )
        json.dumps(data)


if __name__ == "__main__":
    unittest.main()
