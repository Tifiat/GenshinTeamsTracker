from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hoyolab_export.catalog_mapping import (
    STATUS_MATCHED,
    STATUS_UNMATCHED,
    WARNING_DUPLICATE_ACCOUNT_VARIANT,
)
from hoyolab_export.catalog_mapping_report import (
    WARNING_ACCOUNT_LANGUAGE_MISSING,
    build_account_readiness_report_from_paths,
    build_mapping_report,
    build_mapping_report_from_paths,
    load_account_language,
    sanitize_account_character,
    sanitize_account_weapon,
)
from hoyolab_export.catalog_sanity import (
    STATUS_CATALOG_ENTRY_MISSING,
    STATUS_FUTURE_PENDING_STATS,
    STATUS_READY,
    STATUS_SPECIAL_DEFERRED,
)
from hoyolab_export.character_stats_catalog import (
    WARNING_NO_ASCENSION_ROWS,
    CharacterBaseStatRow,
    CharacterBaseStatsCatalog,
    CharacterBaseStatsEntry,
    StatValuePair,
)
from hoyolab_export.weapon_stats_catalog import (
    WeaponAtkValuePair,
    WeaponBaseStatRow,
    WeaponStatsCatalog,
    WeaponStatsEntry,
)


class CatalogMappingReportTest(unittest.TestCase):
    def test_account_character_sanitizer_extracts_only_allowed_fields(self) -> None:
        sanitized = sanitize_account_character(
            {
                "id": 1,
                "name": "Amber",
                "element": "Pyro",
                "rarity": 4,
                "level": 90,
                "constellation": 6,
                "weapon_type": 12,
                "weapon_type_name": "bow",
                "icon": "private-icon-url",
                "side_icon": "private-side-icon-url",
            }
        )

        self.assertEqual(
            set(sanitized),
            {
                "id",
                "name",
                "element",
                "rarity",
                "level",
                "constellation",
                "weapon_type",
                "weapon_type_name",
            },
        )
        self.assertNotIn("icon", sanitized)
        self.assertNotIn("side_icon", sanitized)

    def test_account_weapon_sanitizer_extracts_only_allowed_fields(self) -> None:
        sanitized = sanitize_account_weapon(
            {
                "id": 10,
                "name": "Favonius Warbow",
                "rarity": 4,
                "type": 12,
                "type_name": "bow",
                "level": 90,
                "refinement": 5,
                "icon": "private-icon-url",
                "equipped_by": {
                    "id": 1,
                    "name": "Amber",
                    "icon": "private-character-icon",
                },
            }
        )

        self.assertEqual(
            set(sanitized),
            {
                "id",
                "name",
                "rarity",
                "type",
                "type_name",
                "level",
                "refinement",
                "equipped_by",
            },
        )
        self.assertEqual(set(sanitized["equipped_by"]), {"id", "name"})
        self.assertNotIn("icon", sanitized)

    def test_missing_language_file_warns_and_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            language, warnings = load_account_language(Path(temp_dir) / "missing.json")

        self.assertEqual(language, "en-us")
        self.assertIn(WARNING_ACCOUNT_LANGUAGE_MISSING, warnings)

    def test_report_shape_and_no_private_fields(self) -> None:
        report = build_mapping_report(
            account_characters=[
                {
                    "id": 1,
                    "name": "Amber",
                    "element": "Pyro",
                    "rarity": 4,
                    "icon": "should-not-be-present",
                }
            ],
            account_weapons=[
                {
                    "id": 2,
                    "name": "Favonius Warbow",
                    "type_name": "bow",
                    "rarity": 4,
                    "icon": "should-not-be-present",
                }
            ],
            character_catalog=[
                {
                    "entry_page_id": "14",
                    "name": "Amber",
                    "lang": "en-us",
                    "element": "Pyro",
                    "rarity": 4,
                }
            ],
            weapon_catalog=[
                {
                    "entry_page_id": "2019",
                    "name": "Favonius Warbow",
                    "lang": "en-us",
                    "type": "Bow",
                    "rarity": 4,
                }
            ],
            language="en-us",
            examples_per_status=1,
        )

        self.assertEqual(report["characters"]["matched"], 1)
        self.assertEqual(report["weapons"]["matched"], 1)
        self.assertEqual(
            report["characters"]["examples"][STATUS_MATCHED][0]["account"]["name"],
            "Amber",
        )
        self.assertNotIn(
            "icon",
            json.dumps(report, ensure_ascii=False),
        )

    def test_duplicate_weapon_variants_are_warned_not_failed(self) -> None:
        report = build_mapping_report(
            account_characters=[],
            account_weapons=[
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
            character_catalog=[],
            weapon_catalog=[
                {
                    "entry_page_id": "2019",
                    "name": "Favonius Warbow",
                    "type": "Bow",
                    "rarity": 4,
                }
            ],
            language="en-us",
            examples_per_status=2,
        )

        self.assertEqual(report["weapons"]["matched"], 2)
        self.assertEqual(
            report["weapons"]["warnings"][WARNING_DUPLICATE_ACCOUNT_VARIANT],
            2,
        )

    def test_build_mapping_report_from_explicit_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            characters_path = root / "characters.json"
            weapons_path = root / "weapons.json"
            language_path = root / "language.json"
            character_catalog_path = root / "character_catalog.json"
            weapon_catalog_path = root / "weapon_catalog.json"

            characters_path.write_text(
                json.dumps([{"id": 1, "name": "Amber", "element": "Pyro"}]),
                encoding="utf-8",
            )
            weapons_path.write_text(
                json.dumps([{"id": 2, "name": "Favonius Warbow", "type_name": "bow"}]),
                encoding="utf-8",
            )
            language_path.write_text(
                json.dumps({"contentLanguage": "en-us"}),
                encoding="utf-8",
            )
            character_catalog_path.write_text(
                json.dumps([{"entry_page_id": "14", "name": "Amber", "element": "Pyro"}]),
                encoding="utf-8",
            )
            weapon_catalog_path.write_text(
                json.dumps(
                    [{"entry_page_id": "2019", "name": "Favonius Warbow", "type": "Bow"}]
                ),
                encoding="utf-8",
            )

            report = build_mapping_report_from_paths(
                characters_path=characters_path,
                weapons_path=weapons_path,
                language_path=language_path,
                character_catalog_path=character_catalog_path,
                weapon_catalog_path=weapon_catalog_path,
            )

        self.assertEqual(report["language"], "en-us")
        self.assertEqual(report["characters"]["matched"], 1)
        self.assertEqual(report["weapons"]["matched"], 1)
        self.assertEqual(report["source_notes"]["account_characters"], "characters.json")
        self.assertIn("character_catalog.json", report["source_notes"]["character_catalog"])
        self.assertNotIn(str(root), json.dumps(report, ensure_ascii=False))
        self.assertFalse(report["source_notes"]["network_fetch"])

    def test_build_account_readiness_report_from_explicit_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            characters_path = root / "characters.json"
            weapons_path = root / "weapons.json"
            language_path = root / "language.json"
            character_catalog_path = root / "character_catalog.json"
            weapon_catalog_path = root / "weapon_catalog.json"
            character_stats_path = root / "character_stats_catalog.json"
            weapon_stats_path = root / "weapon_stats_catalog.json"

            characters_path.write_text(
                json.dumps(
                    [
                        {"id": 1, "name": "Amber", "icon": "private"},
                        {"id": 2, "name": "Traveler"},
                        {"id": 3, "name": "Missing Hero"},
                        {"id": 4, "name": "Future Hero"},
                        {"id": 5, "name": "No Cache Hero"},
                    ]
                ),
                encoding="utf-8",
            )
            weapons_path.write_text(
                json.dumps(
                    [
                        {"id": 10, "name": "Favonius Warbow", "icon": "private"},
                        {"id": 11, "name": "No Cache Sword"},
                    ]
                ),
                encoding="utf-8",
            )
            language_path.write_text(
                json.dumps({"contentLanguage": "en-us"}),
                encoding="utf-8",
            )
            character_catalog_path.write_text(
                json.dumps(
                    [
                        {"entry_page_id": "14", "name": "Amber"},
                        {"entry_page_id": "9001", "name": "Future Hero"},
                        {"entry_page_id": "9999", "name": "No Cache Hero"},
                    ]
                ),
                encoding="utf-8",
            )
            weapon_catalog_path.write_text(
                json.dumps(
                    [
                        {"entry_page_id": "2019", "name": "Favonius Warbow"},
                        {"entry_page_id": "9998", "name": "No Cache Sword"},
                    ]
                ),
                encoding="utf-8",
            )
            character_stats_path.write_text(
                json.dumps(
                    CharacterBaseStatsCatalog(
                        entries=(
                            CharacterBaseStatsEntry(
                                entry_page_id="14",
                                name="Amber",
                                lang="en-us",
                                rows=(
                                    CharacterBaseStatRow(
                                        level_key="Lv.1",
                                        base_hp=StatValuePair(after="793"),
                                    ),
                                ),
                            ),
                            CharacterBaseStatsEntry(
                                entry_page_id="9001",
                                name="Future Hero",
                                lang="en-us",
                                rows=(),
                                warnings=(WARNING_NO_ASCENSION_ROWS,),
                            ),
                        )
                    ).to_dict()
                ),
                encoding="utf-8",
            )
            weapon_stats_path.write_text(
                json.dumps(
                    WeaponStatsCatalog(
                        entries=(
                            WeaponStatsEntry(
                                entry_page_id="2019",
                                name="Favonius Warbow",
                                lang="en-us",
                                rows=(
                                    WeaponBaseStatRow(
                                        level_key="Lv.1",
                                        base_atk=WeaponAtkValuePair(after="41"),
                                    ),
                                ),
                            ),
                        )
                    ).to_dict()
                ),
                encoding="utf-8",
            )

            report = build_account_readiness_report_from_paths(
                characters_path=characters_path,
                weapons_path=weapons_path,
                language_path=language_path,
                character_catalog_path=character_catalog_path,
                weapon_catalog_path=weapon_catalog_path,
                character_stats_catalog_path=character_stats_path,
                weapon_stats_catalog_path=weapon_stats_path,
            )

        character_statuses = report["readiness"]["account_characters"]["statuses"]
        weapon_statuses = report["readiness"]["account_weapons"]["statuses"]
        self.assertEqual(character_statuses[STATUS_READY], 1)
        self.assertEqual(character_statuses[STATUS_SPECIAL_DEFERRED], 1)
        self.assertEqual(character_statuses[STATUS_UNMATCHED], 1)
        self.assertEqual(character_statuses[STATUS_FUTURE_PENDING_STATS], 1)
        self.assertEqual(character_statuses[STATUS_CATALOG_ENTRY_MISSING], 1)
        self.assertEqual(weapon_statuses[STATUS_READY], 1)
        self.assertEqual(weapon_statuses[STATUS_CATALOG_ENTRY_MISSING], 1)
        self.assertFalse(report["source_notes"]["detail_fetch"])
        self.assertNotIn("private", json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
