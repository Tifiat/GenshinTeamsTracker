from __future__ import annotations

import unittest

from run_workspace.gcsim.farming_profile_config import (
    GCSIM_SCREENING_PROFILE_CONTRACT,
    GCSIM_SCREENING_STAT_AXES,
    GCSIM_SUBSTAT_ROLL_VALUES,
    GcsimScreeningProfileError,
    allocate_gcsim_screening_substats,
    apply_gcsim_screening_runtime_options,
    build_default_gcsim_screening_profile_bank,
    render_gcsim_screening_profile_config,
)
from run_workspace.gcsim.farming_search import StatProfile, StatWeight
from run_workspace.gcsim.optimizer_config import (
    GcsimFiveStarMainStatLayout,
    render_five_star_main_stat_line,
    render_four_star_set_main_stat_line,
)


class GcsimFarmingProfileConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.layout = GcsimFiveStarMainStatLayout(
            sands="hp%",
            goblet="hydro%",
            circlet="cr",
        )
        self.bank = build_default_gcsim_screening_profile_bank()

    def test_pinned_axis_values_match_optimizer_contract(self) -> None:
        self.assertEqual(
            tuple(axis.key for axis in GCSIM_SCREENING_STAT_AXES),
            tuple(GCSIM_SUBSTAT_ROLL_VALUES),
        )
        self.assertEqual(GCSIM_SUBSTAT_ROLL_VALUES["cr"], 0.0331)
        self.assertEqual(GCSIM_SUBSTAT_ROLL_VALUES["em"], 19.82)
        self.assertEqual(GCSIM_SUBSTAT_ROLL_VALUES["hp"], 253.94)
        self.assertNotIn(
            "balanced",
            tuple(profile.profile_id for profile in self.bank.profiles),
        )

    def test_balanced_profile_spends_exact_twenty_liquid_rolls(self) -> None:
        allocation = allocate_gcsim_screening_substats(
            self.layout,
            self.bank.profile("baseline"),
        )

        self.assertEqual(allocation.total_liquid_substats, 20)
        self.assertEqual(sum(dict(allocation.liquid_rolls_by_axis).values()), 20)
        self.assertEqual(set(dict(allocation.liquid_rolls_by_axis).values()), {2})
        self.assertTrue(
            allocation.investment_signature.startswith(
                GCSIM_SCREENING_PROFILE_CONTRACT + ":"
            )
        )
        self.assertTrue(all(item.fixed_rolls == 2 for item in allocation.rolls))

    def test_focus_profile_respects_main_stat_reduced_cap_then_spills(self) -> None:
        hp_layout = GcsimFiveStarMainStatLayout(
            sands="hp%",
            goblet="hydro%",
            circlet="cr",
        )
        allocation = allocate_gcsim_screening_substats(
            hp_layout,
            self.bank.profile("focus/hp"),
        )
        rolls = {item.axis_key: item for item in allocation.rolls}

        # Flower owns an HP main, so pinned upstream reduces the liquid cap from
        # ten to eight (10 - fixed_count * one matching main).
        self.assertEqual(rolls["hp"].liquid_cap, 8)
        self.assertEqual(rolls["hp"].liquid_rolls, 8)
        self.assertEqual(sum(item.liquid_rolls for item in allocation.rolls), 20)
        self.assertGreater(
            sum(item.liquid_rolls for item in allocation.rolls if item.axis_key != "hp"),
            0,
        )

    def test_duplicate_hp_main_reduces_focus_cap_to_six(self) -> None:
        layout = GcsimFiveStarMainStatLayout(
            sands="hp%",
            goblet="hp%",
            circlet="cr",
        )
        # hp% has two matching variable main stats in this deliberately legal
        # GCSIM layout, so the response envelope must honor both.
        allocation = allocate_gcsim_screening_substats(
            layout,
            self.bank.profile("focus/hp%"),
        )
        hp_percent = next(item for item in allocation.rolls if item.axis_key == "hp%")
        self.assertEqual(hp_percent.liquid_cap, 6)
        self.assertEqual(hp_percent.liquid_rolls, 6)

    def test_four_star_package_matches_upstream_roll_and_rarity_penalty(self) -> None:
        allocation = allocate_gcsim_screening_substats(
            self.layout,
            self.bank.profile("baseline"),
            four_star_piece_count=4,
        )

        self.assertEqual(allocation.total_liquid_substats, 12)
        self.assertAlmostEqual(allocation.rarity_modifier, 0.84)
        cr = next(item for item in allocation.rolls if item.axis_key == "cr")
        self.assertAlmostEqual(cr.effective_roll_value, 0.0331 * 0.84)
        self.assertEqual(sum(item.liquid_rolls for item in allocation.rolls), 12)

        five_star = allocate_gcsim_screening_substats(
            self.layout,
            self.bank.profile("baseline"),
        )
        self.assertEqual(
            allocation.investment_signature,
            five_star.investment_signature,
        )

    def test_materially_different_envelopes_have_different_signatures(self) -> None:
        baseline = allocate_gcsim_screening_substats(
            self.layout,
            self.bank.profile("baseline"),
        )
        no_liquid = allocate_gcsim_screening_substats(
            self.layout,
            self.bank.profile("baseline"),
            total_liquid_substats=0,
        )
        skewed_reference = allocate_gcsim_screening_substats(
            self.layout,
            self.bank.profile("baseline"),
            reference_weights=(StatWeight(axis_key="em", weight=1.0),),
        )

        self.assertNotEqual(
            baseline.investment_signature,
            no_liquid.investment_signature,
        )
        self.assertNotEqual(
            baseline.investment_signature,
            skewed_reference.investment_signature,
        )

    def test_custom_profile_cannot_create_or_drop_liquid_rolls(self) -> None:
        profile = StatProfile(
            profile_id="mostly-em",
            kind="custom",
            weights=(
                StatWeight(axis_key="em", weight=0.8),
                StatWeight(axis_key="er", weight=0.2),
            ),
        )
        allocation = allocate_gcsim_screening_substats(self.layout, profile)
        values = dict(allocation.liquid_rolls_by_axis)

        self.assertEqual(sum(values.values()), 20)
        self.assertEqual(values["em"], 10)
        self.assertGreater(values["er"], 0)

    def test_unknown_profile_axis_is_rejected(self) -> None:
        profile = StatProfile(
            profile_id="unsupported",
            kind="custom",
            weights=(StatWeight(axis_key="imaginaryp", weight=1.0),),
        )
        with self.assertRaisesRegex(GcsimScreeningProfileError, "unsupported axis"):
            allocate_gcsim_screening_substats(self.layout, profile)

    def test_renderer_appends_profile_only_after_exact_main_row(self) -> None:
        main_line = render_five_star_main_stat_line("furina", self.layout)
        config = (
            "furina char lvl=90/90 cons=0 talent=9,9,9;\n"
            f"{main_line}\n"
            "options swap_delay=12 iteration=1000 workers=16;\n"
            "target lvl=100 resist=0.1;\n"
        )

        result = render_gcsim_screening_profile_config(
            config,
            main_stat_layouts={"furina": self.layout},
            profiles={"furina": self.bank.profile("focus/em")},
        )

        lines = result.config_text.splitlines()
        main_index = lines.index(main_line)
        self.assertTrue(lines[main_index + 1].startswith("furina add stats atk%="))
        self.assertIn(" em=19.82*", lines[main_index + 1])
        self.assertEqual(result.characters[0].profile_id, "focus/em")
        self.assertTrue(
            result.investment_signature.startswith(
                GCSIM_SCREENING_PROFILE_CONTRACT + ":"
            )
        )

    def test_renderer_supports_mixed_four_star_set_and_one_five_star_offpiece(self) -> None:
        main_line = render_four_star_set_main_stat_line(
            "furina",
            self.layout,
            offpiece_slot="goblet",
        )
        config = (
            "furina char lvl=90/90 cons=0 talent=9,9,9;\n"
            f"{main_line}\n"
            "options iteration=10 workers=1;\n"
        )

        result = render_gcsim_screening_profile_config(
            config,
            main_stat_layouts={"furina": self.layout},
            profiles={"furina": self.bank.profile("baseline")},
            four_star_offpiece_slots={"furina": "goblet"},
        )

        allocation = result.characters[0].allocation
        self.assertEqual(allocation.four_star_piece_count, 4)
        self.assertEqual(allocation.total_liquid_substats, 12)
        self.assertIn("cr=0.027804*", result.characters[0].substat_line)

    def test_renderer_rejects_account_or_stale_optimizer_stats(self) -> None:
        config = (
            "furina char lvl=90/90 cons=0 talent=9,9,9;\n"
            "furina add stats hp=99999;\n"
            "options iteration=10 workers=1;\n"
        )
        with self.assertRaisesRegex(
            GcsimScreeningProfileError,
            "does not match the pinned candidate renderer",
        ):
            render_gcsim_screening_profile_config(
                config,
                main_stat_layouts={"furina": self.layout},
                profiles={"furina": self.bank.profile("baseline")},
            )

    def test_renderer_rejects_an_existing_second_stats_row(self) -> None:
        main_line = render_five_star_main_stat_line("furina", self.layout)
        config = (
            "furina char lvl=90/90 cons=0 talent=9,9,9;\n"
            f"{main_line}\n"
            "furina add stats cr=0.0331*2;\n"
            "options iteration=10 workers=1;\n"
        )
        with self.assertRaisesRegex(GcsimScreeningProfileError, "exactly one main-stat row"):
            render_gcsim_screening_profile_config(
                config,
                main_stat_layouts={"furina": self.layout},
                profiles={"furina": self.bank.profile("baseline")},
            )

    def test_renderer_rejects_hidden_stats_statement(self) -> None:
        main_line = render_five_star_main_stat_line("furina", self.layout)
        config = (
            "furina char lvl=90/90 cons=0 talent=9,9,9;\n"
            f"{main_line} furina add stats cr=1;\n"
            "options iteration=10 workers=1;\n"
        )
        with self.assertRaisesRegex(
            GcsimScreeningProfileError,
            "canonical semicolon-terminated row",
        ):
            render_gcsim_screening_profile_config(
                config,
                main_stat_layouts={"furina": self.layout},
                profiles={"furina": self.bank.profile("baseline")},
            )

    def test_renderer_separates_a_final_main_row_without_newline(self) -> None:
        main_line = render_five_star_main_stat_line("furina", self.layout)
        config = (
            "furina char lvl=90/90 cons=0 talent=9,9,9;\n"
            f"{main_line}"
        )

        result = render_gcsim_screening_profile_config(
            config,
            main_stat_layouts={"furina": self.layout},
            profiles={"furina": self.bank.profile("baseline")},
        )

        self.assertIn(f"{main_line}\nfurina add stats ", result.config_text)

    def test_runtime_options_replace_duplicate_existing_tokens_idempotently(self) -> None:
        config = "options workers=16 swap_delay=12 iteration=1000 workers=8;\n"
        rendered = apply_gcsim_screening_runtime_options(
            config,
            iterations=25,
            workers=3,
        )

        self.assertEqual(
            rendered,
            "options swap_delay=12 iteration=25 workers=3;\n",
        )
        self.assertEqual(
            apply_gcsim_screening_runtime_options(
                rendered,
                iterations=25,
                workers=3,
            ),
            rendered,
        )

    def test_runtime_options_require_one_line_and_plain_positive_integers(self) -> None:
        with self.assertRaisesRegex(GcsimScreeningProfileError, "exactly one"):
            apply_gcsim_screening_runtime_options("", iterations=10, workers=1)
        with self.assertRaisesRegex(GcsimScreeningProfileError, "exactly one"):
            apply_gcsim_screening_runtime_options(
                "options iteration=10 workers=1; "
                "options iteration=1 workers=999;\n",
                iterations=10,
                workers=1,
            )
        with self.assertRaisesRegex(GcsimScreeningProfileError, "canonical row"):
            apply_gcsim_screening_runtime_options(
                "options iteration=10\n workers=999;\n",
                iterations=10,
                workers=1,
            )
        with self.assertRaisesRegex(GcsimScreeningProfileError, "iterations must"):
            apply_gcsim_screening_runtime_options(
                "options iteration=10;\n",
                iterations=True,
                workers=1,
            )


if __name__ == "__main__":
    unittest.main()
