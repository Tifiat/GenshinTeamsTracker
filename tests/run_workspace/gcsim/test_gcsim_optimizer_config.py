from __future__ import annotations

import re
import unittest

from run_workspace.gcsim.optimizer_config import (
    LEGAL_FIVE_STAR_CIRCLET_MAIN_STATS,
    LEGAL_FIVE_STAR_GOBLET_MAIN_STATS,
    LEGAL_FIVE_STAR_SANDS_MAIN_STATS,
    OPTIMIZER_CONFIG_INVALID_CHARACTER,
    OPTIMIZER_CONFIG_DUPLICATE_CHARACTER,
    OPTIMIZER_CONFIG_INVALID_LAYOUT,
    OPTIMIZER_CONFIG_INVALID_OFFPIECE,
    OPTIMIZER_CONFIG_LAYOUT_MISMATCH,
    OPTIMIZER_CONFIG_NONCANONICAL_STATEMENT,
    OPTIMIZER_CONFIG_READY,
    OPTIMIZER_CONFIG_STATS_ROW_MISSING,
    GcsimFiveStarMainStatLayout,
    apply_gcsim_optimizer_worker_budget,
    iter_legal_four_star_set_main_stat_layouts,
    iter_legal_five_star_main_stat_layouts,
    render_five_star_main_stat_line,
    render_four_star_set_main_stat_line,
    render_gcsim_four_star_set_optimizer_config,
    render_gcsim_substat_optimizer_config,
)


BASE_CONFIG = """mona char lvl=90/90 cons=0 talent=9,9,9;
mona add weapon="favoniuscodex" refine=5 lvl=90/90;
mona add set="emblemofseveredfate" count=4;
mona add stats hp=4780 atk=311 er=0.518 hydro%=0.466 cr=0.311 cd=0.662;

bennett char lvl=90/90 cons=6 talent=9,12,13;
bennett add weapon="mistsplitterreforged" refine=1 lvl=90/90;
bennett add set="noblesseoblige" count=4;
bennett add stats hp=4780 atk=311 atk%=0.466 pyro%=0.466 cr=0.311 er=0.551;

options iteration=1000 duration=90 workers=4;
target lvl=100 resist=0.1 radius=2 pos=0,2.4 hp=999999999;
energy every interval=480,720 amount=1;
active mona;

while .total_time < 90 {
  mona skill;
  bennett burst;
}
"""


def layouts() -> dict[str, GcsimFiveStarMainStatLayout]:
    return {
        "mona": GcsimFiveStarMainStatLayout(
            sands="er",
            goblet="hydro%",
            circlet="cr",
        ),
        "bennett": GcsimFiveStarMainStatLayout(
            sands="hp%",
            goblet="hp%",
            circlet="heal",
        ),
    }


class GcsimOptimizerConfigTest(unittest.TestCase):
    def test_replaces_only_stats_rows_with_exact_five_main_stats(self) -> None:
        result = render_gcsim_substat_optimizer_config(BASE_CONFIG, layouts())

        self.assertTrue(result.ready)
        self.assertEqual(result.status, OPTIMIZER_CONFIG_READY)
        self.assertEqual(
            result.config_text,
            BASE_CONFIG.replace(
                (
                    "mona add stats hp=4780 atk=311 er=0.518 hydro%=0.466 "
                    "cr=0.311 cd=0.662;"
                ),
                (
                    "mona add stats hp=4780 atk=311 er=0.518 hydro%=0.466 "
                    "cr=0.311;"
                ),
            ).replace(
                (
                    "bennett add stats hp=4780 atk=311 atk%=0.466 pyro%=0.466 "
                    "cr=0.311 er=0.551;"
                ),
                (
                    "bennett add stats hp=4780 atk=311 hp%=0.466 hp%=0.466 "
                    "heal=0.359;"
                ),
            ),
        )
        self.assertEqual(
            [item.character_key for item in result.characters],
            ["mona", "bennett"],
        )
        self.assertFalse(result.source_notes["account_substats_carried_forward"])

        pinned_main_row = re.compile(
            r"(?m)^[a-z]+\s+add\s+stats\s+hp=(4780|3571)\b[^;]*;"
        )
        rows = pinned_main_row.findall(result.config_text)
        self.assertEqual(len(rows), 2)
        for item in result.characters:
            payload = item.line.split(" add stats ", 1)[1].removesuffix(";")
            self.assertEqual(len(payload.split()), 5)

    def test_canonical_crlf_rows_remain_supported(self) -> None:
        config = BASE_CONFIG.replace("\n", "\r\n")

        result = render_gcsim_substat_optimizer_config(config, layouts())

        self.assertTrue(result.ready)
        self.assertIn("\r\n", result.config_text)
        self.assertNotIn("\n", result.config_text.replace("\r\n", ""))

    def test_rejects_hidden_or_multiline_stats_statements(self) -> None:
        poisoned_configs = (
            BASE_CONFIG.replace(
                'mona add weapon="favoniuscodex" refine=5 lvl=90/90;',
                'mona add weapon="favoniuscodex" refine=5 lvl=90/90; '
                "mona add stats cr=1;",
            ),
            BASE_CONFIG.replace("mona add stats ", "mona add\n stats ", 1),
        )

        for poisoned in poisoned_configs:
            with self.subTest(poisoned=poisoned):
                result = render_gcsim_substat_optimizer_config(
                    poisoned,
                    layouts(),
                )
                self.assertFalse(result.ready)
                self.assertEqual(
                    result.status,
                    OPTIMIZER_CONFIG_NONCANONICAL_STATEMENT,
                )

    def test_removes_stale_optimizer_substat_rows_and_is_idempotent(self) -> None:
        config = BASE_CONFIG.replace(
            "mona add stats hp=4780 atk=311 er=0.518 hydro%=0.466 cr=0.311 cd=0.662;",
            (
                "mona add stats hp=4780 atk=311 er=0.518 hydro%=0.466 cr=0.311;\n"
                "mona add stats hp%=0.0496*2 cr=0.0331*8 cd=0.0662*8;"
            ),
        )

        first = render_gcsim_substat_optimizer_config(config, layouts())
        second = render_gcsim_substat_optimizer_config(first.config_text, layouts())

        self.assertTrue(first.ready)
        self.assertEqual(first.config_text, second.config_text)
        self.assertEqual(first.config_text.count("mona add stats"), 1)
        self.assertNotIn("0.0496*2", first.config_text)

    def test_repeated_main_stat_is_not_aggregated(self) -> None:
        line = render_five_star_main_stat_line(
            "furina",
            {"sands": "hp%", "goblet": "hp%", "circlet": "hp%"},
        )

        self.assertEqual(
            line,
            (
                "furina add stats hp=4780 atk=311 hp%=0.466 hp%=0.466 "
                "hp%=0.466;"
            ),
        )
        self.assertEqual(line.count("hp%="), 3)

    def test_all_generated_layouts_are_slot_legal(self) -> None:
        generated = tuple(iter_legal_five_star_main_stat_layouts())

        self.assertEqual(
            len(generated),
            len(LEGAL_FIVE_STAR_SANDS_MAIN_STATS)
            * len(LEGAL_FIVE_STAR_GOBLET_MAIN_STATS)
            * len(LEGAL_FIVE_STAR_CIRCLET_MAIN_STATS),
        )
        self.assertEqual(len(set(generated)), len(generated))
        for layout in generated:
            line = render_five_star_main_stat_line("mona", layout)
            self.assertEqual(
                len(line.split(" add stats ", 1)[1].removesuffix(";").split()),
                5,
            )

    def test_illegal_slot_main_stat_fails_closed(self) -> None:
        invalid = layouts()
        invalid["mona"] = GcsimFiveStarMainStatLayout(
            sands="hydro%",
            goblet="hydro%",
            circlet="cr",
        )

        result = render_gcsim_substat_optimizer_config(BASE_CONFIG, invalid)

        self.assertFalse(result.ready)
        self.assertEqual(result.status, OPTIMIZER_CONFIG_INVALID_LAYOUT)
        self.assertEqual(result.config_text, "")
        self.assertIn("sands", result.issues[0].message)

    def test_layout_keys_must_exactly_match_declared_team(self) -> None:
        missing = layouts()
        del missing["bennett"]

        result = render_gcsim_substat_optimizer_config(BASE_CONFIG, missing)

        self.assertFalse(result.ready)
        self.assertEqual(result.status, OPTIMIZER_CONFIG_LAYOUT_MISMATCH)
        self.assertEqual(result.issues[0].character_key, "bennett")

    def test_rejects_layout_keys_that_collide_after_normalization(self) -> None:
        duplicate_layouts = {
            "mona": layouts()["mona"],
            " mona ": layouts()["mona"],
            "bennett": layouts()["bennett"],
        }

        result = render_gcsim_substat_optimizer_config(BASE_CONFIG, duplicate_layouts)

        self.assertFalse(result.ready)
        self.assertEqual(result.status, OPTIMIZER_CONFIG_DUPLICATE_CHARACTER)
        self.assertIn("ambiguous", result.issues[0].message)

    def test_character_key_must_match_pinned_optimizer_regex(self) -> None:
        config = BASE_CONFIG.replace("mona", "pyro_traveler")
        invalid_layouts = layouts()
        invalid_layouts["pyro_traveler"] = invalid_layouts.pop("mona")

        result = render_gcsim_substat_optimizer_config(config, invalid_layouts)

        self.assertFalse(result.ready)
        self.assertEqual(result.status, OPTIMIZER_CONFIG_INVALID_CHARACTER)
        self.assertEqual(result.config_text, "")

    def test_missing_replaceable_stats_row_fails_closed(self) -> None:
        config = BASE_CONFIG.replace(
            "mona add stats hp=4780 atk=311 er=0.518 hydro%=0.466 cr=0.311 cd=0.662;\n",
            "",
        )

        result = render_gcsim_substat_optimizer_config(config, layouts())

        self.assertFalse(result.ready)
        self.assertEqual(result.status, OPTIMIZER_CONFIG_STATS_ROW_MISSING)
        self.assertEqual(result.issues[0].character_key, "mona")

    def test_four_star_set_renderer_keeps_one_five_star_offpiece_per_character(self) -> None:
        result = render_gcsim_four_star_set_optimizer_config(
            BASE_CONFIG,
            layouts(),
            {"mona": "flower", "bennett": "goblet"},
        )

        self.assertTrue(result.ready)
        self.assertIn(
            "mona add stats hp=4780 atk=232 er=0.387 hydro%=0.348 cr=0.232;",
            result.config_text,
        )
        self.assertIn(
            "bennett add stats hp=3571 atk=232 hp%=0.348 hp%=0.466 heal=0.268;",
            result.config_text,
        )
        self.assertEqual(
            result.source_notes["four_star_set_offpiece_slots"],
            {"mona": "flower", "bennett": "goblet"},
        )

    def test_four_star_set_renderer_supports_mixed_team_rarities(self) -> None:
        result = render_gcsim_four_star_set_optimizer_config(
            BASE_CONFIG,
            layouts(),
            {"bennett": "goblet"},
        )

        self.assertTrue(result.ready)
        self.assertIn(
            "mona add stats hp=4780 atk=311 er=0.518 hydro%=0.466 cr=0.311;",
            result.config_text,
        )
        self.assertIn(
            "bennett add stats hp=3571 atk=232 hp%=0.348 hp%=0.466 heal=0.268;",
            result.config_text,
        )

    def test_four_star_set_line_and_generator_cover_every_offpiece_slot(self) -> None:
        line = render_four_star_set_main_stat_line(
            "bennett",
            {"sands": "er", "goblet": "pyro%", "circlet": "cd"},
            offpiece_slot="circlet",
        )
        generated = tuple(iter_legal_four_star_set_main_stat_layouts())

        self.assertEqual(
            line,
            "bennett add stats hp=3571 atk=232 er=0.387 pyro%=0.348 cd=0.622;",
        )
        self.assertEqual(
            len(generated),
            len(tuple(iter_legal_five_star_main_stat_layouts())) * 5,
        )
        self.assertEqual({offpiece for _, offpiece in generated}, {
            "flower", "plume", "sands", "goblet", "circlet"
        })

    def test_four_star_set_renderer_rejects_invalid_offpiece(self) -> None:
        result = render_gcsim_four_star_set_optimizer_config(
            BASE_CONFIG,
            layouts(),
            {"mona": "weapon", "bennett": "goblet"},
        )

        self.assertFalse(result.ready)
        self.assertEqual(result.status, OPTIMIZER_CONFIG_INVALID_OFFPIECE)

    def test_four_star_set_renderer_rejects_empty_offpiece(self) -> None:
        result = render_gcsim_four_star_set_optimizer_config(
            BASE_CONFIG,
            layouts(),
            {"mona": ""},
        )

        self.assertFalse(result.ready)
        self.assertEqual(result.status, OPTIMIZER_CONFIG_INVALID_OFFPIECE)

    def test_four_star_set_renderer_rejects_normalized_offpiece_collision(self) -> None:
        result = render_gcsim_four_star_set_optimizer_config(
            BASE_CONFIG,
            layouts(),
            {"mona": "flower", " mona ": "goblet"},
        )

        self.assertFalse(result.ready)
        self.assertEqual(result.status, OPTIMIZER_CONFIG_DUPLICATE_CHARACTER)
        self.assertIn("ambiguous", result.issues[0].message)

    def test_worker_budget_is_explicit_and_idempotently_replaced(self) -> None:
        with_workers = apply_gcsim_optimizer_worker_budget(BASE_CONFIG, 8)
        replaced = apply_gcsim_optimizer_worker_budget(with_workers, 3)

        self.assertIn("options iteration=1000 duration=90 workers=3;", replaced)
        self.assertEqual(replaced.count("workers="), 1)

    def test_worker_budget_rejects_missing_or_multiple_options_lines(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one"):
            apply_gcsim_optimizer_worker_budget("target hp=1;", 2)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            apply_gcsim_optimizer_worker_budget(
                "options iteration=1;\noptions workers=2;",
                2,
            )
        with self.assertRaisesRegex(ValueError, "exactly one options statement"):
            apply_gcsim_optimizer_worker_budget(
                "options iteration=1; options workers=999;\n",
                2,
            )
        with self.assertRaisesRegex(ValueError, "canonical row"):
            apply_gcsim_optimizer_worker_budget(
                "options iteration=1\n workers=999;\n",
                2,
            )

    def test_worker_budget_collapses_duplicate_worker_tokens(self) -> None:
        rendered = apply_gcsim_optimizer_worker_budget(
            "options iteration=1 workers=20 workers=999;",
            4,
        )

        self.assertEqual(rendered, "options iteration=1 workers=4;")
        self.assertEqual(rendered.count("workers="), 1)


if __name__ == "__main__":
    unittest.main()
