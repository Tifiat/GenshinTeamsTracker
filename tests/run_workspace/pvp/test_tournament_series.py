from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
import unittest

from run_workspace.pvp.match_result import (
    MATCH_STATUS_DRAW, MATCH_STATUS_FINISHED, MATCH_STATUS_TECHNICAL_LOSS,
    ChamberTimer, MatchResult, PlayerMatchTimers, TechnicalLoss,
)
from run_workspace.pvp.schedule import SEAT_PLAYER_1, SEAT_PLAYER_2
from run_workspace.pvp.tournament_series import SERIES_STATUS_IN_PROGRESS, TournamentSeries


def _result(
    player_1_raw: int,
    player_2_raw: int,
    *,
    adjusted: tuple[object, object] | None = None,
) -> MatchResult:
    player_1 = PlayerMatchTimers(SEAT_PLAYER_1, (ChamberTimer("room", "chamber", player_1_raw),))
    player_2 = PlayerMatchTimers(SEAT_PLAYER_2, (ChamberTimer("room", "chamber", player_2_raw),))
    score_1, score_2 = adjusted if adjusted is not None else (player_1_raw, player_2_raw)
    source_scoring = None
    if adjusted is not None:
        source_scoring = {
            "mode": "SHIYU",
            "paid_restarts": [30],
            "per_seat": {
                SEAT_PLAYER_1: {"adjusted_seconds": score_1},
                SEAT_PLAYER_2: {"adjusted_seconds": score_2},
            },
        }
    if Decimal(str(score_1)) == Decimal(str(score_2)):
        status, winner = MATCH_STATUS_DRAW, None
    elif Decimal(str(score_1)) < Decimal(str(score_2)):
        status, winner = MATCH_STATUS_FINISHED, SEAT_PLAYER_1
    else:
        status, winner = MATCH_STATUS_FINISHED, SEAT_PLAYER_2
    return MatchResult(
        player_1_timers=player_1,
        player_2_timers=player_2,
        status=status,
        winner_seat=winner,
        seconds_difference=abs(player_1_raw - player_2_raw),
        source_scoring=source_scoring,
    )


class TournamentSeriesTests(unittest.TestCase):
    def test_default_and_alternating_first_seat_keep_stable_players(self) -> None:
        self.assertEqual(TournamentSeries().configured_games, 1)
        self.assertEqual(TournamentSeries().first_seat_for_game(1), SEAT_PLAYER_1)
        self.assertEqual(TournamentSeries(configured_games=2).first_seat_for_game(2), SEAT_PLAYER_2)
        fixed = TournamentSeries(configured_games=3, initial_first_seat=SEAT_PLAYER_2, alternate_first=False)
        self.assertEqual([fixed.first_seat_for_game(index) for index in range(1, 4)], [SEAT_PLAYER_2] * 3)
        series = TournamentSeries(configured_games=3, initial_first_seat=SEAT_PLAYER_2)
        self.assertEqual(
            [series.first_seat_for_game(index) for index in range(1, 4)],
            [SEAT_PLAYER_2, SEAT_PLAYER_1, SEAT_PLAYER_2],
        )
        for index in range(1, 4):
            series = series.with_game_result(index, _result(10 + index, 20 + index))
        self.assertEqual([game.first_seat for game in series.games], [SEAT_PLAYER_2, SEAT_PLAYER_1, SEAT_PLAYER_2])
        self.assertEqual(series.totals, {SEAT_PLAYER_1: Decimal(36), SEAT_PLAYER_2: Decimal(66)})
        self.assertEqual(series.winner_seat, SEAT_PLAYER_1)

    def test_sequential_results_and_duplicate_protection(self) -> None:
        series = TournamentSeries(configured_games=2)
        result = _result(10, 20)
        with self.assertRaisesRegex(ValueError, "order"):
            series.with_game_result(2, result)
        recorded = series.with_game_result(1, result)
        self.assertEqual(series.games, ())
        self.assertIs(recorded.with_game_result(1, _result(10, 20)), recorded)
        with self.assertRaisesRegex(ValueError, "overwritten"):
            recorded.with_game_result(1, _result(11, 20))
        complete = recorded.with_game_result(2, _result(30, 25))
        self.assertIsNone(complete.next_game_index)
        with self.assertRaisesRegex(ValueError, "outside"):
            complete.with_game_result(3, result)

    def test_adjusted_restart_seconds_determine_series_when_raw_totals_reverse(self) -> None:
        series = TournamentSeries(configured_games=2)
        series = series.with_game_result(1, _result(90, 100, adjusted=("130.25", "100")))
        self.assertEqual(series.status, SERIES_STATUS_IN_PROGRESS)
        self.assertIsNone(series.winner_seat)
        self.assertEqual(series.next_game_index, 2)
        self.assertEqual(series.to_dict()["totals"], {SEAT_PLAYER_1: "130.25", SEAT_PLAYER_2: 100})
        series = series.with_game_result(2, _result(80, 100, adjusted=(80, 100)))
        self.assertEqual(sum(game.result.player_1_timers.total_elapsed_seconds for game in series.games), 170)
        self.assertEqual(sum(game.result.player_2_timers.total_elapsed_seconds for game in series.games), 200)
        self.assertEqual(series.totals, {SEAT_PLAYER_1: Decimal("210.25"), SEAT_PLAYER_2: Decimal(200)})
        self.assertEqual(series.winner_seat, SEAT_PLAYER_2)
        self.assertEqual(series.seconds_difference, Decimal("10.25"))
        payload = series.to_dict()
        self.assertEqual(payload["status"], MATCH_STATUS_FINISHED)
        self.assertEqual(payload["winner_seat"], SEAT_PLAYER_2)
        self.assertEqual(payload["seconds_difference"], "10.25")
        self.assertEqual(payload["games"][0]["result"]["source_scoring"]["mode"], "SHIYU")

    def test_draw_is_decided_only_after_all_games(self) -> None:
        series = TournamentSeries(configured_games=2).with_game_result(1, _result(10, 20))
        self.assertIsNone(series.winner_seat)
        self.assertEqual(series.status, SERIES_STATUS_IN_PROGRESS)
        series = series.with_game_result(2, _result(20, 10))
        self.assertTrue(series.complete)
        self.assertEqual(series.status, MATCH_STATUS_DRAW)
        self.assertIsNone(series.winner_seat)
        self.assertEqual(series.seconds_difference, 0)
        self.assertIsNone(series.to_dict()["next_game_index"])

    def test_recorded_scoring_is_detached_and_json_serializable(self) -> None:
        original = _result(90, 100, adjusted=(120, 100))
        series = TournamentSeries().with_game_result(1, original)
        self.assertIsNot(series.games[0].result, original)
        original.source_scoring["per_seat"][SEAT_PLAYER_1]["adjusted_seconds"] = 1  # type: ignore[index]
        original.source_scoring["paid_restarts"].append(999)  # type: ignore[union-attr]
        self.assertEqual(series.totals[SEAT_PLAYER_1], Decimal(120))
        with self.assertRaises(TypeError):
            series.games[0].result.source_scoring["per_seat"][SEAT_PLAYER_1]["adjusted_seconds"] = 1  # type: ignore[index]
        payload = series.to_dict()
        self.assertEqual(payload["games"][0]["result"]["source_scoring"]["paid_restarts"], [30])
        self.assertEqual(payload["games"][0]["result"]["source_scoring"]["per_seat"][SEAT_PLAYER_1]["adjusted_seconds"], 120)
        json.dumps(payload)

    def test_invalid_game_count_and_index(self) -> None:
        for count in (0, 10, True, 1.5, "3"):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, "configured_games"):
                TournamentSeries(configured_games=count)  # type: ignore[arg-type]
        for index in (0, 3, True, 1.5, "1"):
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "game_index"):
                TournamentSeries(configured_games=2).first_seat_for_game(index)  # type: ignore[arg-type]

    def test_invalid_starter_and_alternation_type(self) -> None:
        with self.assertRaisesRegex(ValueError, "initial_first_seat"):
            TournamentSeries(initial_first_seat="unknown")
        with self.assertRaisesRegex(ValueError, "alternate_first"):
            TournamentSeries(alternate_first=1)  # type: ignore[arg-type]

    def test_nonfinite_or_invalid_adjusted_seconds_rejected(self) -> None:
        valid = _result(10, 20, adjusted=(10, 20))
        for value in (float("nan"), float("inf"), "NaN", "Infinity", -1, True, None):
            source = {"mode": "SHIYU", "per_seat": {
                SEAT_PLAYER_1: {"adjusted_seconds": value},
                SEAT_PLAYER_2: {"adjusted_seconds": 20},
            }}
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "seconds"):
                TournamentSeries().with_game_result(1, replace(valid, source_scoring=source))

    def test_unknown_scoring_and_technical_loss_rejected(self) -> None:
        valid = _result(10, 20)
        invalid_results = (
            replace(valid, status="unknown"),
            replace(valid, status=MATCH_STATUS_TECHNICAL_LOSS),
            replace(valid, technical_losses=(TechnicalLoss(SEAT_PLAYER_1, "disconnect"),)),
            replace(valid, source_scoring={"mode": "SHIYU"}),
            replace(valid, source_scoring={"mode": "SHIYU", "per_seat": {SEAT_PLAYER_1: {"adjusted_seconds": 10}}}),
            replace(valid, source_scoring={"mode": "unknown", "per_seat": {
                SEAT_PLAYER_1: {"adjusted_seconds": 10}, SEAT_PLAYER_2: {"adjusted_seconds": 20},
            }}),
            replace(valid, winner_seat=SEAT_PLAYER_2),
            replace(valid, seconds_difference=float("nan")),
        )
        for invalid in invalid_results:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                TournamentSeries().with_game_result(1, invalid)

    def test_invalid_raw_timer_and_direct_game_construction_rejected(self) -> None:
        valid = _result(10, 20)
        invalid_timers = PlayerMatchTimers(SEAT_PLAYER_1, (ChamberTimer("room", "chamber", -5),))
        with self.assertRaisesRegex(ValueError, "elapsed_seconds"):
            TournamentSeries().with_game_result(1, replace(valid, player_1_timers=invalid_timers))
        game = TournamentSeries().with_game_result(1, valid).games[0]
        with self.assertRaisesRegex(ValueError, "sequential"):
            TournamentSeries(configured_games=2, games=(replace(game, game_index=2),))


if __name__ == "__main__":
    unittest.main()
