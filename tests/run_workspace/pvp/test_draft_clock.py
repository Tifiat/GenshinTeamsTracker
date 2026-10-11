from __future__ import annotations

import unittest

from run_workspace.pvp.draft_clock import DraftClock
from run_workspace.pvp.schedule import SEAT_PLAYER_1, SEAT_PLAYER_2


class FakeNow:
    def __init__(self) -> None:
        self.seconds = 0.0

    def __call__(self) -> float:
        return self.seconds

    def move_ms(self, milliseconds: int) -> None:
        self.seconds += milliseconds / 1000


class DraftClockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = FakeNow()
        self.clock = DraftClock(1000, 2000, now=self.now)
        self.clock.start("first", SEAT_PLAYER_1)

    def test_base_then_reserve_and_repeated_snapshots(self) -> None:
        self.now.move_ms(1000)
        at_base = self.clock.snapshot()
        self.assertEqual(at_base.pick_remaining_ms, 0)
        self.assertEqual(at_base.reserve_remaining_ms[SEAT_PLAYER_1], 2000)
        self.assertTrue(at_base.running)
        self.now.move_ms(375)
        first = self.clock.snapshot()
        second = self.clock.snapshot()
        self.assertEqual(first, second)
        self.assertEqual(first.reserve_remaining_ms[SEAT_PLAYER_1], 1625)
        self.assertEqual(first.reserve_remaining_ms[SEAT_PLAYER_2], 2000)
        with self.assertRaises(TypeError):
            first.reserve_remaining_ms[SEAT_PLAYER_1] = 0

    def test_advance_restarts_pick_and_keeps_seat_reserve(self) -> None:
        self.now.move_ms(1500)
        self.assertTrue(self.clock.advance("second", SEAT_PLAYER_1))
        second = self.clock.snapshot()
        self.assertEqual(second.pick_remaining_ms, 1000)
        self.assertEqual(second.reserve_remaining_ms[SEAT_PLAYER_1], 1500)
        self.now.move_ms(1250)
        self.assertEqual(self.clock.snapshot().reserve_remaining_ms[SEAT_PLAYER_1], 1250)
        self.clock.advance("third", SEAT_PLAYER_2)
        self.assertEqual(self.clock.snapshot().reserve_remaining_ms[SEAT_PLAYER_1], 1250)
        self.now.move_ms(1200)
        self.assertEqual(self.clock.snapshot().reserve_remaining_ms[SEAT_PLAYER_2], 1800)
        self.clock.advance("fourth", SEAT_PLAYER_1)
        self.assertEqual(self.clock.snapshot().pick_remaining_ms, 1000)
        self.assertEqual(self.clock.snapshot().reserve_remaining_ms[SEAT_PLAYER_1], 1250)

    def test_unchanged_action_key_does_not_reset(self) -> None:
        self.now.move_ms(1250)
        self.assertFalse(self.clock.advance("first", SEAT_PLAYER_2))
        self.assertEqual(self.clock.snapshot().active_seat, SEAT_PLAYER_1)
        self.assertEqual(self.clock.snapshot().reserve_remaining_ms[SEAT_PLAYER_1], 1750)
        self.now.move_ms(250)
        self.assertEqual(self.clock.snapshot().reserve_remaining_ms[SEAT_PLAYER_1], 1500)

    def test_pause_resume_freezes_both_allowances(self) -> None:
        self.now.move_ms(1200)
        self.clock.pause()
        self.assertTrue(self.clock.snapshot().paused)
        self.now.move_ms(5000)
        paused = self.clock.snapshot()
        self.assertEqual(paused.reserve_remaining_ms[SEAT_PLAYER_1], 1800)
        self.assertFalse(paused.running)
        self.clock.resume()
        self.assertFalse(self.clock.snapshot().paused)
        self.now.move_ms(400)
        self.assertEqual(self.clock.snapshot().reserve_remaining_ms[SEAT_PLAYER_1], 1400)

    def test_expiry_exact_boundary_and_backward_sample(self) -> None:
        self.now.move_ms(2999)
        self.assertFalse(self.clock.snapshot().expired)
        self.now.move_ms(1)
        exhausted = self.clock.snapshot()
        self.assertTrue(exhausted.expired)
        self.assertFalse(exhausted.running)
        self.assertEqual(exhausted.reserve_remaining_ms[SEAT_PLAYER_1], 0)
        self.now.seconds = 0.0
        self.assertTrue(self.clock.snapshot().expired)
        self.assertEqual(self.clock.snapshot().reserve_remaining_ms[SEAT_PLAYER_1], 0)
        self.clock.advance("second", SEAT_PLAYER_2)
        self.assertFalse(self.clock.snapshot().expired)
        self.assertTrue(self.clock.snapshot().running)

    def test_zero_pick_disables_reserve_clock(self) -> None:
        clock = DraftClock(0, 2000, now=self.now)
        clock.start("first", SEAT_PLAYER_1)
        self.now.move_ms(100000)
        self.assertFalse(clock.snapshot().running)
        self.assertFalse(clock.snapshot().expired)
        self.assertEqual(clock.snapshot().reserve_remaining_ms[SEAT_PLAYER_1], 2000)
        clock.advance("second", SEAT_PLAYER_1)
        self.assertEqual(clock.snapshot().reserve_remaining_ms[SEAT_PLAYER_1], 2000)

    def test_long_gap_without_polling_caps_only_active_reserve(self) -> None:
        self.now.move_ms(100000)
        self.assertTrue(self.clock.snapshot().expired)
        self.assertEqual(self.clock.snapshot().reserve_remaining_ms[SEAT_PLAYER_1], 0)
        self.assertEqual(self.clock.snapshot().reserve_remaining_ms[SEAT_PLAYER_2], 2000)
        self.clock.advance("second", SEAT_PLAYER_1)
        self.assertEqual(self.clock.snapshot().pick_remaining_ms, 1000)
        self.assertEqual(self.clock.snapshot().reserve_remaining_ms[SEAT_PLAYER_1], 0)
        self.now.move_ms(999)
        self.assertFalse(self.clock.snapshot().expired)
        self.now.move_ms(1)
        self.assertTrue(self.clock.snapshot().expired)

    def test_finish_freezes_at_final_instant(self) -> None:
        self.now.move_ms(1400)
        self.clock.finish()
        finished = self.clock.snapshot()
        self.now.move_ms(10000)
        self.assertEqual(self.clock.snapshot(), finished)
        self.assertTrue(finished.finished)
        self.assertFalse(finished.running)
        self.assertEqual(finished.reserve_remaining_ms[SEAT_PLAYER_1], 1600)
        with self.assertRaises(RuntimeError):
            self.clock.advance("second", SEAT_PLAYER_2)

    def test_rejects_invalid_configuration_and_action(self) -> None:
        for bad in (-1, True, 1.5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                DraftClock(bad, 0, now=self.now)
            with self.subTest(reserve=bad), self.assertRaises(ValueError):
                DraftClock(1, bad, now=self.now)
        with self.assertRaises(ValueError):
            self.clock.advance(None, SEAT_PLAYER_1)
        with self.assertRaises(ValueError):
            self.clock.advance("second", "other")


if __name__ == "__main__":
    unittest.main()
