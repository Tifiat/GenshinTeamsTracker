from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from run_workspace.pvp.abyss_rules import AbyssRuleset
from run_workspace.pvp.draft_options import DraftMatchOptions, parse_restart_penalties
from tests.run_workspace.pvp.test_abyss_snapshot_phases import source_with_phases


class DraftMatchOptionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = AbyssRuleset.from_source(*source_with_phases())

    def test_source_defaults_and_pinned_snapshot_stay_unchanged(self) -> None:
        before = self.rules.to_dict()
        hash_before = self.rules.content_hash
        resolved = DraftMatchOptions().resolve(self.rules)
        self.assertEqual(resolved, DraftMatchOptions(
            preban_cost_step=60,
            pick_time_ms=60000,
            reserve_time_ms=300000,
            auto_on_expire=True,
            free_restarts=3,
            paid_restarts=(5, 5, 10),
            first_seat="player_1",
            games_count=1,
            alternate_first=True,
        ))
        self.assertEqual(self.rules.to_dict(), before)
        self.assertEqual(self.rules.content_hash, hash_before)
        with self.assertRaises(FrozenInstanceError):
            resolved.free_restarts = 4

    def test_explicit_zero_and_empty_paid_override_source(self) -> None:
        options = DraftMatchOptions(free_restarts=0, paid_restarts=(),
                                    pick_time_ms=0, auto_on_expire=False,
                                    first_seat="player_2", games_count=5,
                                    alternate_first=False)
        resolved = options.resolve(self.rules)
        self.assertEqual(resolved.free_restarts, 0)
        self.assertEqual(resolved.paid_restarts, ())
        self.assertEqual(resolved.pick_time_ms, 0)
        self.assertEqual(resolved.reserve_time_ms, 300000)
        self.assertFalse(resolved.auto_on_expire)
        self.assertEqual((resolved.first_seat, resolved.games_count, resolved.alternate_first),
                         ("player_2", 5, False))
        self.assertEqual(resolved.to_dict()["paid_restarts"], ())

    def test_free_draft_defaults_are_resolved(self) -> None:
        self.assertEqual(DraftMatchOptions().resolve(None), DraftMatchOptions(
            preban_cost_step=0, pick_time_ms=0, reserve_time_ms=0,
            auto_on_expire=True, free_restarts=0, paid_restarts=(),
            first_seat="player_1", games_count=1, alternate_first=True,
        ))

    def test_game_order_options_validate_and_survive_resolution(self) -> None:
        options = DraftMatchOptions(first_seat="player_2", games_count=9,
                                    alternate_first=False)
        for rules in (None, self.rules):
            with self.subTest(rules=rules is not None):
                resolved = options.resolve(rules)
                self.assertEqual((resolved.first_seat, resolved.games_count,
                                  resolved.alternate_first), ("player_2", 9, False))
        for bad in ("", "player_3", None, True, 1):
            with self.subTest(first=bad), self.assertRaises(ValueError):
                DraftMatchOptions(first_seat=bad)
        for bad in (0, 10, True, 1.0, "2"):
            with self.subTest(games=bad), self.assertRaises(ValueError):
                DraftMatchOptions(games_count=bad)
        for bad in (0, 1, None, "true"):
            with self.subTest(alternate=bad), self.assertRaises(ValueError):
                DraftMatchOptions(alternate_first=bad)

    def test_restart_bounds_and_immutable_tuple_shape(self) -> None:
        DraftMatchOptions(free_restarts=100, paid_restarts=(0, 86400, 1.25))
        DraftMatchOptions(paid_restarts=(0,) * 100)
        for bad in (-1, 101, True, 1.0, "1"):
            with self.subTest(free=bad), self.assertRaises(ValueError):
                DraftMatchOptions(free_restarts=bad)
        bad_paid = ([5], (True,), (-1,), (86400.01,), (float("inf"),),
                    (float("nan"),), ((5,),), ("5",), (0,) * 101)
        for bad in bad_paid:
            with self.subTest(paid=bad), self.assertRaises(ValueError):
                DraftMatchOptions(paid_restarts=bad)


class ParseRestartPenaltiesTests(unittest.TestCase):
    def test_blank_and_decimal_list(self) -> None:
        self.assertEqual(parse_restart_penalties(" \t"), ())
        self.assertEqual(parse_restart_penalties("5 / 5 / 10"), (5, 5, 10))
        self.assertEqual(parse_restart_penalties("+5 / .5 / 5. / 0"), (5, 0.5, 5.0, 0))
        self.assertEqual(parse_restart_penalties("86400"), (86400,))
        self.assertEqual(len(parse_restart_penalties("/".join(["0"] * 100))), 100)

    def test_rejects_malformed_or_out_of_bounds_input(self) -> None:
        bad_texts = ("/", "5/", "/5", "5//10", "-1", "1e2", "NaN", "inf",
                     "1,5", "5 5", "++5", "86400.01", "0/" * 100,
                     "/".join(["0"] * 101))
        for bad in bad_texts:
            with self.subTest(text=bad), self.assertRaises(ValueError):
                parse_restart_penalties(bad)
        with self.assertRaises(ValueError):
            parse_restart_penalties([5])


if __name__ == "__main__":
    unittest.main()
