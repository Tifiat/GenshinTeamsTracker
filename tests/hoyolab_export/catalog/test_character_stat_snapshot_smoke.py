from __future__ import annotations

import unittest

from hoyolab_export.character_stat_snapshot import (
    WARNING_CHARACTER_ASCENSION_PHASE_ASSUMED,
    WARNING_WEAPON_STATS_UNAVAILABLE,
)
from hoyolab_export.character_stat_snapshot_smoke import (
    WARNING_WEAPON_WIKI_MAPPING_MISSING,
    build_character_stat_snapshot_smoke_report,
    inspect_account_promote_phase_fields,
)
from hoyolab_export.character_stats_catalog import (
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


def character_catalog() -> CharacterBaseStatsCatalog:
    return CharacterBaseStatsCatalog(
        lang="en-us",
        fetched_at="2026-01-01T00:00:00+00:00",
        entries=(
            CharacterBaseStatsEntry(
                entry_page_id="14",
                name="Amber",
                lang="en-us",
                rows=(
                    CharacterBaseStatRow(
                        level_key="Lv.20",
                        base_hp=StatValuePair(before="2038", after="2630"),
                        base_atk=StatValuePair(before="48", after="62"),
                        base_def=StatValuePair(before="129", after="167"),
                        ascension_bonus_stat_type="ATK",
                        ascension_bonus=StatValuePair(before="0.0%", after="6.0%"),
                    ),
                ),
            ),
        ),
    )


def weapon_catalog() -> WeaponStatsCatalog:
    return WeaponStatsCatalog(
        lang="en-us",
        fetched_at="2026-01-01T00:00:00+00:00",
        entries=(
            WeaponStatsEntry(
                entry_page_id="2019",
                name="Favonius Warbow",
                lang="en-us",
                rows=(
                    WeaponBaseStatRow(
                        level_key="Lv.20",
                        base_atk=WeaponAtkValuePair(before="99", after="125"),
                        secondary_stat_type="Energy Recharge",
                        secondary_stat_value="23.6%",
                    ),
                ),
            ),
        ),
    )


def account_details(*, include_weapon_wiki: bool = True) -> dict:
    weapon_wiki = {"15403": "https://wiki.hoyolab.com/pc/genshin/entry/2019"}
    if not include_weapon_wiki:
        weapon_wiki = {}
    return {
        "json": {
            "data": {
                "avatar_wiki": {
                    "10000005": "https://wiki.hoyolab.com/pc/genshin/entry/1",
                    "10000021": "https://wiki.hoyolab.com/pc/genshin/entry/14",
                },
                "weapon_wiki": weapon_wiki,
                "list": [
                    {
                        "base": {
                            "id": 10000005,
                            "name": "Traveler",
                            "level": 20,
                            "rarity": 5,
                            "actived_constellation_num": 0,
                        },
                        "weapon": {
                            "id": 15403,
                            "name": "Favonius Warbow",
                            "level": 20,
                            "promote_level": 1,
                            "affix_level": 1,
                            "rarity": 4,
                            "type_name": "Bow",
                            "icon": "must-not-leak",
                        },
                    },
                    {
                        "base": {
                            "id": 10000021,
                            "name": "Amber",
                            "level": 20,
                            "rarity": 4,
                            "actived_constellation_num": 6,
                            "icon": "must-not-leak",
                        },
                        "weapon": {
                            "id": 15403,
                            "name": "Favonius Warbow",
                            "level": 20,
                            "promote_level": 1,
                            "affix_level": 1,
                            "rarity": 4,
                            "type_name": "Bow",
                            "desc": "must-not-leak",
                        },
                    },
                ],
            }
        }
    }


class CharacterStatSnapshotSmokeTest(unittest.TestCase):
    def test_report_builds_snapshot_and_skips_traveler(self) -> None:
        report = build_character_stat_snapshot_smoke_report(
            account_characters=[
                {"id": 10000021, "name": "Amber", "level": 20, "constellation": 6},
            ],
            account_weapons=[
                {
                    "id": 15403,
                    "name": "Favonius Warbow",
                    "level": 20,
                    "refinement": 5,
                    "equipped_by": {"id": 10000021, "name": "Amber"},
                }
            ],
            account_details=account_details(),
            character_catalog=character_catalog(),
            weapon_catalog=weapon_catalog(),
            language="en-us",
            limit=1,
        )

        self.assertEqual(report["selection"]["special_deferred"], 1)
        self.assertEqual(report["selection"]["selected_snapshots"], 1)
        snapshot = report["snapshots"][0]
        self.assertEqual(snapshot["account_character"]["name"], "Amber")
        self.assertEqual(snapshot["account_weapon"]["refinement"], 5)
        self.assertIn(WARNING_CHARACTER_ASCENSION_PHASE_ASSUMED, snapshot["warnings"])
        self.assertTrue(snapshot["observations"]["artifact_summary_missing"])
        self.assertTrue(snapshot["observations"]["final_totals_not_computed"])
        self.assertFalse(_contains_forbidden_key(report, {"icon", "image", "side_icon", "desc"}))

    def test_inspection_reports_no_character_phase_and_weapon_promote_level(self) -> None:
        inspection = inspect_account_promote_phase_fields(
            account_characters=[{"id": 10000021, "name": "Amber", "level": 20}],
            account_weapons=[{"id": 15403, "name": "Favonius Warbow", "level": 20}],
            account_details=account_details(),
        )

        self.assertEqual(inspection["account_character_promote_like_fields"], [])
        self.assertEqual(inspection["detail_base_promote_like_fields"], [])
        self.assertIn(
            "not_found",
            inspection["character_ascension_phase_source"],
        )
        self.assertEqual(inspection["detail_weapon_promote_like_fields"], ["promote_level"])
        self.assertIn(
            "weapon.promote_level",
            inspection["weapon_ascension_phase_source"],
        )

    def test_missing_weapon_mapping_does_not_fake_catalog_weapon(self) -> None:
        report = build_character_stat_snapshot_smoke_report(
            account_characters=[
                {"id": 10000021, "name": "Amber", "level": 20, "constellation": 6},
            ],
            account_weapons=[],
            account_details=account_details(include_weapon_wiki=False),
            character_catalog=character_catalog(),
            weapon_catalog=weapon_catalog(),
            language="en-us",
            limit=1,
        )

        snapshot = report["snapshots"][0]
        self.assertIsNone(snapshot["weapon_catalog"])
        self.assertIn(WARNING_WEAPON_WIKI_MAPPING_MISSING, snapshot["warnings"])
        self.assertIn(WARNING_WEAPON_STATS_UNAVAILABLE, snapshot["warnings"])


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, dict):
        return any(
            key in forbidden or _contains_forbidden_key(item, forbidden)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


if __name__ == "__main__":
    unittest.main()
