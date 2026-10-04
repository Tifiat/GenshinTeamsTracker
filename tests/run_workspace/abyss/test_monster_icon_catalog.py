from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

from run_workspace.abyss.monster_icon_catalog import (
    NANOKA_MONSTER_PAGE_URL,
    NanokaMonsterIconCatalog,
    enrich_missing_monster_icons,
    fetch_nanoka_monster_icon_catalog,
    parse_nanoka_monster_icon_catalog,
    resolve_nanoka_icon_url,
)
from run_workspace.abyss.source_data import (
    HP_SOURCE_NANOKA_RESOLVED,
    HP_SOURCE_UNAVAILABLE,
    MATCH_METHOD_STRICT,
    MATCH_METHOD_UNMATCHED,
    AbyssFloorSourceData,
    build_abyss_floor_source_data_from_reports,
)
from run_workspace.abyss.source_data_fetchers import (
    AbyssSourceFetchError,
    NANOKA_ICON_BASE,
)


def _floor_data() -> AbyssFloorSourceData:
    composition_rows = [
        _fandom_row("Hydro Hilichurl Rogue", wave=1),
        _fandom_row("Hydro Hilichurl Rogue", wave=2),
        _fandom_row("Existing Portrait", wave=3),
    ]
    nanoka_rows = [
        {
            "floor": 12,
            "chamber": 1,
            "side": 1,
            "enemy_display_name": "Existing Portrait",
            "monster_id": "9001",
            "level": 100,
            "hp_resolved": 500,
            "hp_source_path": "tower.floor12.chamber1.side1.9001.hp",
            "icon_url": "https://static.nanoka.cc/assets/gi/Existing.webp",
            "enemy_detail_url": "https://gi.nanoka.cc/monster/9001",
        }
    ]
    return build_abyss_floor_source_data_from_reports(
        period_start="2026-09-16",
        tower_id="123",
        floor=12,
        composition_report={
            "source": {
                "url": "https://genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors/2026-09-16",
                "period_date_from_url": "2026-09-16",
                "mediawiki_parse_api_url": "https://example.test/parse",
            },
            "floors": [{"floor": 12, "warnings": [], "chambers": []}],
            "enemy_rows": composition_rows,
        },
        nanoka_report={
            "towers": [
                {
                    "tower_id": "123",
                    "enemy_rows": nanoka_rows,
                    "source_urls": {},
                }
            ]
        },
    )


def _fandom_row(name: str, *, wave: int) -> dict[str, object]:
    return {
        "floor": 12,
        "chamber": 1,
        "side": 1,
        "side_name": "First Half",
        "wave": wave,
        "count": 1,
        "level": 100,
        "display_name": name,
        "enemy_page_url": None,
        "icon_url": None,
    }


class NanokaMonsterIconCatalogTest(unittest.TestCase):
    def test_parse_uses_actual_monster_json_name_and_icon_fields(self) -> None:
        catalog = parse_nanoka_monster_icon_catalog(
            {
                "200101": {
                    "en": "Abyss Mage: Pyro",
                    "icon": "UI_MonsterIcon_AbyssMage_Fire",
                }
            }
        )

        self.assertEqual(
            catalog,
            {
                "abyssmagepyro": (
                    f"{NANOKA_ICON_BASE}/UI_MonsterIcon_AbyssMage_Fire.webp",
                )
            },
        )
        self.assertEqual(
            resolve_nanoka_icon_url("abyss mage pyro", catalog),
            f"{NANOKA_ICON_BASE}/UI_MonsterIcon_AbyssMage_Fire.webp",
        )

    def test_parse_skips_missing_names_and_unsafe_icon_keys(self) -> None:
        catalog = parse_nanoka_monster_icon_catalog(
            {
                "1": {"en": "Safe Enemy", "icon": "UI_MonsterIcon_Safe_1"},
                "2": {"en": "Path Enemy", "icon": "../escape"},
                "3": {"en": "Slash Enemy", "icon": "UI/Monster"},
                "4": {"en": "Hyphen Enemy", "icon": "UI-Monster"},
                "5": {"en": "No Icon"},
                "6": {"icon": "UI_MonsterIcon_No_Name"},
            }
        )

        self.assertEqual(
            catalog,
            {
                "safeenemy": (
                    f"{NANOKA_ICON_BASE}/UI_MonsterIcon_Safe_1.webp",
                )
            },
        )

    def test_explicit_aliases_resolve_without_general_variant_stripping(self) -> None:
        catalog: NanokaMonsterIconCatalog = {
            "legatusgolem": (f"{NANOKA_ICON_BASE}/Legatus.webp",),
            "chimericburrowbeast": (f"{NANOKA_ICON_BASE}/Burrowbeast.webp",),
            "oprichnikifirebladeshocktrooper": (
                f"{NANOKA_ICON_BASE}/Fireblade.webp",
            ),
            "primogeovishap": (f"{NANOKA_ICON_BASE}/Geovishap.webp",),
        }

        self.assertEqual(
            resolve_nanoka_icon_url("Statue of Marble and Brass", catalog),
            f"{NANOKA_ICON_BASE}/Legatus.webp",
        )
        self.assertEqual(
            resolve_nanoka_icon_url("Battle-Hardened Chimeric Burrowbeast", catalog),
            f"{NANOKA_ICON_BASE}/Burrowbeast.webp",
        )
        self.assertEqual(
            resolve_nanoka_icon_url(
                "Battle-Hardened Fireblade Shock Trooper",
                catalog,
            ),
            f"{NANOKA_ICON_BASE}/Fireblade.webp",
        )
        self.assertIsNone(resolve_nanoka_icon_url("Primo Geovishap (Cryo)", catalog))

    def test_same_icon_duplicates_are_unique_but_conflicting_icons_are_ambiguous(self) -> None:
        same_icon = parse_nanoka_monster_icon_catalog(
            {
                "1": {"en": "Duplicate Name", "icon": "UI_MonsterIcon_Shared"},
                "2": {"en": "Duplicate Name", "icon": "UI_MonsterIcon_Shared"},
            }
        )
        conflicting_icons = parse_nanoka_monster_icon_catalog(
            {
                "1": {"en": "Duplicate Name", "icon": "UI_MonsterIcon_One"},
                "2": {"en": "Duplicate Name", "icon": "UI_MonsterIcon_Two"},
            }
        )

        self.assertEqual(
            resolve_nanoka_icon_url("Duplicate Name", same_icon),
            f"{NANOKA_ICON_BASE}/UI_MonsterIcon_Shared.webp",
        )
        self.assertIsNone(resolve_nanoka_icon_url("Duplicate Name", conflicting_icons))

    def test_alias_collision_is_rejected(self) -> None:
        catalog: NanokaMonsterIconCatalog = {
            "chimericburrowbeast": (
                f"{NANOKA_ICON_BASE}/One.webp",
                f"{NANOKA_ICON_BASE}/Two.webp",
            )
        }

        self.assertIsNone(
            resolve_nanoka_icon_url("Battle-Hardened Chimeric Burrowbeast", catalog)
        )

    def test_manifest_route_fetches_version_matched_monster_json_once(self) -> None:
        manifest_url = "https://static.nanoka.cc/gi/7.1.51/tower.json"
        monster_url = "https://static.nanoka.cc/gi/7.1.51/monster.json"
        payload = {
            "200101": {
                "en": "Abyss Mage: Pyro",
                "icon": "UI_MonsterIcon_AbyssMage_Fire",
            }
        }
        with (
            patch(
                "run_workspace.abyss.monster_icon_catalog._fetch_json",
                return_value=payload,
            ) as fetch_json,
            patch("run_workspace.abyss.monster_icon_catalog._fetch_text") as fetch_text,
        ):
            catalog = fetch_nanoka_monster_icon_catalog(manifest_url)

        fetch_json.assert_called_once_with(monster_url, timeout=20)
        fetch_text.assert_not_called()
        self.assertIn("abyssmagepyro", catalog)

    def test_invalid_manifest_url_is_rejected_without_network_access(self) -> None:
        with patch(
            "run_workspace.abyss.monster_icon_catalog._fetch_json"
        ) as fetch_json:
            with self.assertRaises(AbyssSourceFetchError):
                fetch_nanoka_monster_icon_catalog(
                    "http://static.nanoka.cc/gi/7.1.51/tower.json"
                )

        fetch_json.assert_not_called()

    def test_discovery_reads_monster_page_then_matching_monster_json(self) -> None:
        html = (
            '<script data-sveltekit-fetched '
            'data-url="https://static.nanoka.cc/gi/7.1.51/monster.json"></script>'
        )
        payload = {
            "200101": {
                "en": "Abyss Mage: Pyro",
                "icon": "UI_MonsterIcon_AbyssMage_Fire",
            }
        }
        with (
            patch(
                "run_workspace.abyss.monster_icon_catalog._fetch_text",
                return_value=html,
            ) as fetch_text,
            patch(
                "run_workspace.abyss.monster_icon_catalog._fetch_json",
                return_value=payload,
            ) as fetch_json,
        ):
            catalog = fetch_nanoka_monster_icon_catalog()

        fetch_text.assert_called_once_with(NANOKA_MONSTER_PAGE_URL, timeout=20)
        fetch_json.assert_called_once_with(
            "https://static.nanoka.cc/gi/7.1.51/monster.json",
            timeout=20,
        )
        self.assertIn("abyssmagepyro", catalog)

    def test_fetch_failure_is_returned_to_the_optional_source_caller(self) -> None:
        failure = AbyssSourceFetchError("catalog unavailable")
        with patch(
            "run_workspace.abyss.monster_icon_catalog._fetch_json",
            side_effect=failure,
        ):
            with self.assertRaises(AbyssSourceFetchError) as raised:
                fetch_nanoka_monster_icon_catalog(
                    "https://static.nanoka.cc/gi/7.1.51/tower.json"
                )

        self.assertIs(raised.exception, failure)

    def test_enrichment_fills_only_icons_and_preserves_hp_and_waves(self) -> None:
        data = _floor_data()
        data = replace(
            data,
            side_summaries=tuple(
                replace(
                    side,
                    waves=tuple(
                        replace(
                            wave,
                            enemies=tuple(replace(enemy) for enemy in wave.enemies),
                        )
                        for wave in side.waves
                    ),
                )
                for side in data.side_summaries
            ),
        )
        catalog: NanokaMonsterIconCatalog = {
            "hydrohilichurlrogue": (f"{NANOKA_ICON_BASE}/HydroRogue.webp",),
            "existingportrait": (f"{NANOKA_ICON_BASE}/Wrong.webp",),
        }

        enriched = enrich_missing_monster_icons(data, catalog)

        self.assertEqual(
            [row.nanoka_icon_url for row in enriched.enemy_rows],
            [
                f"{NANOKA_ICON_BASE}/HydroRogue.webp",
                f"{NANOKA_ICON_BASE}/HydroRogue.webp",
                "https://static.nanoka.cc/assets/gi/Existing.webp",
            ],
        )
        self.assertEqual(
            [row.nanoka_hp for row in enriched.enemy_rows],
            [None, None, 500],
        )
        self.assertEqual(
            [row.nanoka_monster_id for row in enriched.enemy_rows],
            [None, None, "9001"],
        )
        self.assertEqual(enriched.enemy_rows[0].hp_source, HP_SOURCE_UNAVAILABLE)
        self.assertEqual(enriched.enemy_rows[0].match_method, MATCH_METHOD_UNMATCHED)
        self.assertEqual(enriched.enemy_rows[2].hp_source, HP_SOURCE_NANOKA_RESOLVED)
        self.assertEqual(enriched.enemy_rows[2].match_method, MATCH_METHOD_STRICT)

        self.assertEqual(
            [wave.wave for wave in enriched.side_summaries[0].waves],
            [1, 2, 3],
        )
        self.assertEqual(
            [wave.enemies[0].nanoka_icon_url for wave in enriched.side_summaries[0].waves],
            [
                f"{NANOKA_ICON_BASE}/HydroRogue.webp",
                f"{NANOKA_ICON_BASE}/HydroRogue.webp",
                "https://static.nanoka.cc/assets/gi/Existing.webp",
            ],
        )
        self.assertEqual(enriched.side_summaries[0].solo_target_hp, 500)
        self.assertEqual(enriched.side_summaries[0].multi_target_hp, 500)
        self.assertIsNone(data.enemy_rows[0].nanoka_icon_url)
        self.assertEqual(data.enemy_rows[2].nanoka_icon_url, "https://static.nanoka.cc/assets/gi/Existing.webp")


if __name__ == "__main__":
    unittest.main()
