from __future__ import annotations

import unittest

from run_workspace.abyss.source_data import (
    HP_SOURCE_NANOKA_RESOLVED,
    HP_SOURCE_UNAVAILABLE,
    MATCH_METHOD_VARIANT_STRIP,
    AbyssSourceDataUnavailable,
    load_abyss_floor12_source_data,
)


def composition_report(period: str, rows: list[dict]) -> dict:
    return {
        "source": {
            "url": (
                "https://genshin-impact.fandom.com/wiki/"
                f"Spiral_Abyss/Floors/{period}"
            ),
            "period_date_from_url": period,
            "mediawiki_parse_api_url": f"https://example.test/fandom/{period}",
        },
        "floors": [
            {
                "floor": 12,
                "warnings": [],
                "chambers": [],
            }
        ],
        "enemy_rows": rows,
    }


def nanoka_report(tower_id: str, rows: list[dict]) -> dict:
    return {
        "towers": [
            {
                "tower_id": tower_id,
                "period": {"detail_close": "2026-06-16 04:00:00"},
                "source_urls": {
                    "page_url": f"https://gi.nanoka.cc/tower/{tower_id}/",
                    "detail_json_url": f"https://static.nanoka.cc/en/tower/{tower_id}.json",
                },
                "enemy_rows": rows,
            }
        ]
    }


def fandom_row(
    name: str,
    *,
    chamber: int,
    side: int,
    wave: int,
    count: int = 1,
    level: int = 95,
) -> dict:
    return {
        "floor": 12,
        "chamber": chamber,
        "side": side,
        "side_name": "First Half" if side == 1 else "Second Half",
        "wave": wave,
        "display_name": name,
        "count": count,
        "level": level,
        "enemy_page_url": f"https://genshin-impact.fandom.com/wiki/{name.replace(' ', '_')}",
        "icon_url": f"https://static.wikia.nocookie.net/{name}.png",
    }


def nanoka_row(
    name: str,
    *,
    chamber: int,
    side: int,
    hp: int,
    monster_id: str | int,
    level: int = 95,
) -> dict:
    return {
        "floor": 12,
        "chamber": chamber,
        "side": side,
        "enemy_display_name": name,
        "monster_id": str(monster_id),
        "level": level,
        "hp_resolved": hp,
        "hp_source_path": f"tower.floor12.chamber{chamber}.side{side}.{monster_id}.hp",
        "icon_url": f"https://static.nanoka.cc/{monster_id}.png",
        "enemy_detail_url": f"https://gi.nanoka.cc/monster/{monster_id}",
    }


class AbyssSourceDataTest(unittest.TestCase):
    def test_fisher_regression_keeps_five_waves_and_hp_modes(self) -> None:
        fandom_rows = [
            fandom_row(
                "Fisher of Hidden Depths",
                chamber=1,
                side=1,
                wave=wave,
                count=3,
            )
            for wave in range(1, 6)
        ]
        data = load_abyss_floor12_source_data(
            "2026-02-16",
            "116",
            composition_report=composition_report("2026-02-16", fandom_rows),
            nanoka_report=nanoka_report(
                "116",
                [
                    nanoka_row(
                        "Fisher of Hidden Depths",
                        chamber=1,
                        side=1,
                        hp=100,
                        monster_id="fisher",
                    )
                ],
            ),
        )

        self.assertEqual(len(data.enemy_rows), 5)
        self.assertEqual(data.matched_count, 5)
        side = data.side_summary(1, 1)
        self.assertEqual(len(side.waves), 5)
        self.assertEqual([wave.wave for wave in side.waves], [1, 2, 3, 4, 5])
        self.assertTrue(
            all(
                wave.enemies[0].primary_display_name == "Fisher of Hidden Depths"
                and wave.enemies[0].enemy_count == 3
                for wave in side.waves
            )
        )
        self.assertEqual(side.solo_target_hp, 500)
        self.assertEqual(side.multi_target_hp, 1500)

    def test_current_style_join_preserves_fandom_names_and_nanoka_hp(self) -> None:
        names = [
            ("Super-Heavy Landrover: Mechanized Fortress", "Super-Heavy Landrover: Mechanized Fortress"),
            ("Lord of the Hidden Depths: Whisperer of Nightmares", "Lord of the Hidden Depths: Whisperer of Nightmares"),
            ("Ruin Drake: Earthguard", "Ruin Drake: Earthguard"),
            ("Primo Geovishap (Cryo)", "Primo Geovishap"),
            ("Battle-Hardened Grounded Geoshroom", "Battle-Hardened Grounded Geoshroom"),
            ("Hexadecatonic Battle-Hardened Mandragora", "Hexadecatonic Battle-Hardened Mandragora"),
            ("Battle-Scarred Rock Crab", "Battle-Scarred Rock Crab"),
            ("Hydro Hilichurl Rogue", "Hydro Hilichurl Rogue"),
            ("Fatui Electro Cicin Mage", "Fatui Electro Cicin Mage"),
            ("Abyss Lector: Fathomless Flames", "Abyss Lector: Fathomless Flames"),
        ]
        fandom_rows = [
            fandom_row(
                fandom_name,
                chamber=(index // 4) + 1,
                side=(index % 2) + 1,
                wave=(index % 3) + 1,
                level=100,
            )
            for index, (fandom_name, _nanoka_name) in enumerate(names)
        ]
        nanoka_rows = [
            nanoka_row(
                nanoka_name,
                chamber=(index // 4) + 1,
                side=(index % 2) + 1,
                hp=1_000_000 + index,
                monster_id=f"m{index}",
                level=100,
            )
            for index, (_fandom_name, nanoka_name) in enumerate(names)
        ]
        data = load_abyss_floor12_source_data(
            "2026-05-16",
            "119",
            composition_report=composition_report("2026-05-16", fandom_rows),
            nanoka_report=nanoka_report("119", nanoka_rows),
        )

        self.assertEqual(len(data.enemy_rows), 10)
        self.assertEqual(data.matched_count, 10)
        self.assertEqual(data.unmatched_count, 0)
        self.assertEqual(data.ambiguous_count, 0)

        primo = next(
            row for row in data.enemy_rows if row.primary_display_name == "Primo Geovishap (Cryo)"
        )
        self.assertEqual(primo.matched_nanoka_display_name, "Primo Geovishap")
        self.assertEqual(primo.match_method, MATCH_METHOD_VARIANT_STRIP)
        self.assertEqual(primo.hp_source, HP_SOURCE_NANOKA_RESOLVED)

        crab = next(
            row for row in data.enemy_rows if row.primary_display_name == "Battle-Scarred Rock Crab"
        )
        self.assertEqual(crab.matched_nanoka_display_name, "Battle-Scarred Rock Crab")
        self.assertEqual(crab.nanoka_hp, 1_000_006)
        self.assertEqual(crab.hp_source, HP_SOURCE_NANOKA_RESOLVED)

    def test_missing_nanoka_keeps_composition_with_unavailable_hp(self) -> None:
        data = load_abyss_floor12_source_data(
            "2026-05-16",
            "119",
            composition_report=composition_report(
                "2026-05-16",
                [fandom_row("Unmatched Enemy", chamber=1, side=1, wave=1)],
            ),
        )

        row = data.enemy_rows[0]
        self.assertEqual(row.hp_source, HP_SOURCE_UNAVAILABLE)
        self.assertIsNone(row.nanoka_hp)
        self.assertIn("nanoka_report_unavailable", data.global_warnings)
        self.assertIn("side_hp_partial_or_unavailable", data.side_summary(1, 1).warnings)

    def test_loader_requires_composition_input(self) -> None:
        with self.assertRaises(AbyssSourceDataUnavailable):
            load_abyss_floor12_source_data("2026-05-16", "119")


if __name__ == "__main__":
    unittest.main()
