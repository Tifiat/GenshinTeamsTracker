"""Pure presentation checks over synthetic, already detached Theory v3 rows."""
from __future__ import annotations

from copy import deepcopy
import math
import unittest

from run_workspace.gcsim.optimizer_theory_presentation import (
    GO_TO_CONFIG_STAT,
    TheoryResultIndex,
    noncrit_upgrades,
    theory_score_display,
    validate_theory_family,
)
from tests.run_workspace.gcsim.theory_output_fixture import (
    EXPECTED_GROUP_TUPLES,
    EXPECTED_PENDING_TUPLES,
    WEARERS,
    family_row,
    output_snapshot,
    refresh_measurement_identity,
    snapshot_with_rows,
)


def _one_alias(key: str, score: float = 1000.0) -> dict:
    row = family_row(key, score, (1000.0 - score) / 10)
    return row


def _share_package(row: dict, source: dict) -> None:
    row["aliases"][0]["packages"] = deepcopy(source["aliases"][0]["packages"])
    refresh_measurement_identity(row)


def _change_main(row: dict, actor: int, slot: int, main: str) -> None:
    slot_name = ("flower", "plume", "sands", "goblet", "circlet")[slot]
    row["witness45"]["Mains"][actor][slot] = main
    row["allocations"][actor]["main_stats"][slot_name] = main
    refresh_measurement_identity(row)


class TheoryScoreDisplayTests(unittest.TestCase):
    def test_boundaries_use_unrounded_percent_and_adaptive_text(self) -> None:
        at_green = theory_score_display(970, 1000)
        below_green = theory_score_display(969.999, 1000)
        at_orange = theory_score_display(950, 1000)
        below_orange = theory_score_display(949.999, 1000)
        below_reference = theory_score_display(999.999, 1000)
        at_reference = theory_score_display(1000, 1000)

        self.assertEqual((at_green.percent, at_green.percent_text, at_green.color_band), (97.0, "97.0", "green"))
        self.assertEqual(below_green.color_band, "orange")
        self.assertLess(float(below_green.percent_text), 97)
        self.assertEqual(at_orange.color_band, "orange")
        self.assertEqual(below_orange.color_band, "red")
        self.assertLess(float(below_orange.percent_text), 95)
        self.assertLess(float(below_reference.percent_text), 100)
        self.assertEqual(below_reference.deficit_text, "<0.1")
        self.assertTrue(below_reference.nonzero_deficit)
        self.assertEqual((at_reference.percent_text, at_reference.deficit_text), ("100.0", "0"))
        self.assertFalse(at_reference.nonzero_deficit)

    def test_zero_tiny_positive_and_dps_display(self) -> None:
        zero = theory_score_display(0, 1000)
        negative_zero = theory_score_display(-0.0, 1000)
        tiny = theory_score_display(.0001, 1000)
        large = theory_score_display(12345.5, 12345.5)
        self.assertEqual((zero.percent_text, zero.deficit_text, zero.dps_text), ("0.0", "100.0", "0"))
        self.assertEqual((negative_zero.percent_text, negative_zero.dps_text), ("0.0", "0"))
        self.assertGreater(float(tiny.percent_text), 0)
        self.assertEqual(large.dps_text, "12346")
        self.assertNotIn(",", large.dps_text)
        self.assertNotIn("e", large.dps_text.lower())
        self.assertFalse(large.deficit_text.startswith("-"))

    def test_invalid_scores_fail_closed(self) -> None:
        for score, reference in (
            (-1, 100), (101, 100), (0, 0), (1, -1),
            (math.nan, 100), (math.inf, 100), (1, math.inf),
            (True, 100), (1, math.nan),
        ):
            with self.subTest(score=score, reference=reference):
                self.assertIsNone(theory_score_display(score, reference))


class TheoryFamilyTests(unittest.TestCase):
    def test_measured_below_band_row_remains_selectable(self) -> None:
        best = family_row("best", 1000, 0)
        pending = family_row("verified-pending", 900, 10)
        pending["reason"] = "below_verified_practical_band"
        self.assertTrue(validate_theory_family(pending))
        snapshot = snapshot_with_rows([best, pending])
        snapshot["pending"] = [snapshot["co_leaders"].pop()]
        snapshot["found_group_families"] = snapshot["found_group_tuples"] = 1
        self.assertEqual(len(TheoryResultIndex(snapshot)), 2)

    def test_full45_and_only_upgrade_noncrit_units(self) -> None:
        row = family_row("valid", 1000, 0)
        self.assertTrue(validate_theory_family(row))
        self.assertEqual(GO_TO_CONFIG_STAT["energy_recharge"], "er")
        self.assertEqual(GO_TO_CONFIG_STAT["physical_damage_bonus"], "phys%")
        self.assertEqual(GO_TO_CONFIG_STAT["healing_bonus"], "heal")

        by_key = dict(noncrit_upgrades(row, 0))
        self.assertEqual(noncrit_upgrades(row, WEARERS[0]), noncrit_upgrades(row, 0))
        self.assertEqual(by_key["energy_recharge"], 5.0)
        self.assertEqual(by_key["em"], 2.5)
        self.assertEqual(by_key["hp_percent"], 3.75)
        self.assertEqual(sum(by_key.values()), 11.25)
        self.assertNotIn("crit_rate", by_key)
        self.assertNotIn("crit_damage", by_key)
        self.assertEqual(row["allocations"][0]["spent_roll_units"], 45)
        self.assertGreater(row["allocations"][0]["substats"][6]["roll_units"], by_key["em"])

    def test_malformed_full45_rows_and_illegal_mains_are_rejected(self) -> None:
        valid = family_row("valid", 1000, 0)
        mutations = (
            lambda row: row["allocations"].pop(),
            lambda row: row["allocations"][0]["substats"].reverse(),
            lambda row: row["witness45"]["Lines"][0][0].__setitem__(0, 8),  # flower main collision
            lambda row: row["witness45"]["Lines"][0][0].__setitem__(1, 3),  # duplicate line
            lambda row: row["witness45"]["Upgrades"][0][0].__setitem__(slice(0, 2), [1.3, 1.45]),
            lambda row: row["witness45"]["Upgrades"][0][0].__setitem__(0, 0.25),
            lambda row: row["allocations"][0].__setitem__("spent_roll_units", 44),
            lambda row: row["allocations"][0]["substats"][0].__setitem__("roll_units", 99),
            lambda row: next(
                stat for stat in row["allocations"][0]["substats"] if stat["roll_units"] > 0
            ).__setitem__("stat_value", 0),
            lambda row: _change_main(row, 0, 3, "healing_bonus"),  # invalid goblet
            lambda row: row.__setitem__("status", "running"),
            lambda row: row.__setitem__("complete", False),
        )
        for mutate in mutations:
            row = deepcopy(valid)
            mutate(row)
            with self.subTest(mutation=mutate):
                self.assertFalse(validate_theory_family(row))
        with self.assertRaises(ValueError):
            noncrit_upgrades({"family": "incomplete"}, 0)


class TheoryResultIndexTests(unittest.TestCase):
    def test_one_verified_alias_per_row_and_fixed_reference_survive(self) -> None:
        snapshot = output_snapshot()
        index = TheoryResultIndex(snapshot)
        expected = EXPECTED_GROUP_TUPLES + EXPECTED_PENDING_TUPLES
        self.assertEqual(tuple(entry.alias["tuple_key"] for entry in index), expected)
        self.assertGreater(len(index), 5)
        self.assertEqual(len(index), len(expected))
        self.assertEqual(index.rejected_count, 0)
        self.assertEqual(index[-1].refinement_level, 2)
        self.assertEqual(index[-2].refinement_level, 0)  # shallow pending still eligible
        self.assertEqual(index.reference, 1000.0)
        self.assertEqual(theory_score_display(index[0].score, index.reference).color_band, "green")
        snapshot["reference_score"] = 2000.0
        self.assertEqual(index.reference, 1000.0)

    def test_explicit_incomplete_malformed_and_unsupported_rows_do_not_become_builds(self) -> None:
        good = family_row("good", 1000, 0)
        good["search_status"] = "partial"
        running = family_row("running", 900, 10)
        running["status"] = "running"
        incomplete = family_row("incomplete", 900, 10)
        incomplete["available"] = False
        malformed = family_row("malformed", 900, 10)
        _change_main(malformed, 0, 3, "healing_bonus")
        bad_coordinates = family_row("bad-coordinates", 900, 10)
        bad_coordinates["allocations"][0]["substats"].reverse()
        pending = family_row("below", 940, 6, refinement=0)
        pending["reason"] = "below_practical_band_not_deeply_refined"
        pending["measurement"]["origins"][0]["family"] = "internal-frame-hash"
        unsupported = family_row("unsupported", 900, 10)
        unsupported["reason"] = "running"
        snapshot = snapshot_with_rows([good, running, incomplete, malformed, bad_coordinates])
        snapshot["pending"] = [pending, unsupported]
        snapshot["unavailable"] = deepcopy(good["aliases"])

        index = TheoryResultIndex(snapshot)
        self.assertEqual(tuple(entry.family for entry in index), (good["family"], pending["family"]))
        self.assertEqual(index.rejected_count, 5)
        self.assertEqual(index.entries[-1].refinement_level, 0)

    def test_outer_status_reference_and_candidate_identity_fail_closed(self) -> None:
        good = _one_alias("good")
        duplicate = _one_alias("duplicate", 990)
        _share_package(duplicate, good)
        _change_main(duplicate, 0, 3, "pyro_damage_bonus")
        duplicate["aliases"][0]["tuple_key"] = good["aliases"][0]["tuple_key"]
        over_reference = _one_alias("over-reference", 1001)
        snapshot = snapshot_with_rows([good, duplicate, over_reference])
        snapshot["reference_score"] = 1000.0
        index = TheoryResultIndex(snapshot)
        self.assertEqual(tuple(entry.family for entry in index), (good["family"], duplicate["family"]))
        self.assertEqual(index.rejected_count, 1)

        for change in (
            {"status": "running"}, {"phase": "running"},
            {"schema_version": 1}, {"reference_score": 0},
            {"reference_score": math.nan},
        ):
            changed = dict(snapshot)
            changed.update(change)
            with self.subTest(change=change):
                invalid = TheoryResultIndex(changed)
                self.assertEqual(invalid.entries, ())
                self.assertEqual(invalid.rejected_count, 3)

    def test_replacements_are_existing_whole_team_mains_with_exact_packages(self) -> None:
        base = _one_alias("base")
        pyro = _one_alias("pyro", 990)
        pyro_duplicate = _one_alias("pyro-duplicate", 985)
        other_actor = _one_alias("other-actor", 980)
        different_package = _one_alias("different-package", 975)
        for row in (pyro, pyro_duplicate, other_actor):
            _share_package(row, base)
        _change_main(pyro, 0, 3, "pyro_damage_bonus")
        _change_main(pyro_duplicate, 0, 3, "pyro_damage_bonus")
        _change_main(other_actor, 1, 2, "atk_percent")
        # Package order is presentation-only; the complete wearer/sets mapping matches.
        pyro["aliases"][0]["packages"].reverse()
        refresh_measurement_identity(pyro)
        snapshot = snapshot_with_rows([base, pyro, pyro_duplicate, other_actor, different_package])

        index = TheoryResultIndex(snapshot)
        self.assertEqual(len(index), 5)
        self.assertEqual(index.replacement_indices(0), (1, 3))
        self.assertEqual(index.replacement_indices(1), (0, 3))
        self.assertEqual(len(index.package_groups), 2)
        self.assertEqual(index.replacement_indices(4), ())
        self.assertNotIn(2, index.replacement_indices(0))  # same full mains as entry 1
        self.assertNotIn(4, index.replacement_indices(0))  # one package differs
        with self.assertRaises(IndexError):
            index.replacement_indices(5)

    def test_measurement_receipt_is_bound_to_exact_candidate_and_measured_score(self) -> None:
        row = family_row("measured", 987.0, 1.3, formula_score=5000.0)
        snapshot = snapshot_with_rows([row])
        self.assertEqual(TheoryResultIndex(snapshot)[0].score, 987.0)
        self.assertEqual(snapshot["reference_score"], 987.0)
        no_diagnostic_codes = deepcopy(row)
        no_diagnostic_codes["measurement"]["origins"][0].pop("diagnostic_codes")
        self.assertTrue(validate_theory_family(no_diagnostic_codes))

        for mutate in (
            lambda candidate: candidate["measurement"]["build_identity"]["packages"][0]["sets"].clear(),
            lambda candidate: candidate["measurement"].update(candidate_sha256="invalid"),
            lambda candidate: (
                candidate["measurement"].update(candidate_sha256="f" * 64),
                candidate.update(family="f" * 64),
            ),
            lambda candidate: candidate["measurement"].update(frame_sha256="invalid"),
            lambda candidate: candidate["measurement"].update(standard_error=0.0),
            lambda candidate: candidate["measurement"].update(origins=[{"kind": "x"}]),
        ):
            changed = deepcopy(row)
            mutate(changed)
            self.assertFalse(validate_theory_family(changed))

        zero_variance = deepcopy(row)
        zero_variance["measurement"].update(standard_deviation=0.0, standard_error=0.0)
        self.assertTrue(validate_theory_family(zero_variance))

        single = family_row("single", 0.0, 0.0, iterations=1)
        zero_snapshot = snapshot_with_rows([single])
        self.assertEqual(TheoryResultIndex(zero_snapshot)[0].score, 0.0)
        self.assertIsNone(theory_score_display(0.0, 0.0))

    def test_same_alias_tuple_can_have_distinct_measured_main_variants(self) -> None:
        first = _one_alias("main-a", 1000)
        second = _one_alias("main-b", 995)
        _share_package(second, first)
        _change_main(second, 0, 3, "pyro_damage_bonus")
        second["aliases"][0]["tuple_key"] = first["aliases"][0]["tuple_key"]
        snapshot = snapshot_with_rows([first, second])
        index = TheoryResultIndex(snapshot)
        self.assertEqual(tuple(entry.alias["tuple_key"] for entry in index), (
            first["aliases"][0]["tuple_key"], second["aliases"][0]["tuple_key"],
        ))
        self.assertEqual(index.replacement_indices(0), (1,))


if __name__ == "__main__":
    unittest.main()
