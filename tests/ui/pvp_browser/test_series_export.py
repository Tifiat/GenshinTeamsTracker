from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from run_workspace.pvp.match_result import (
    ChamberTimer,
    PlayerMatchTimers,
    calculate_abyss_match_result,
    calculate_match_result,
)
from run_workspace.pvp.schedule import SEAT_PLAYER_1, SEAT_PLAYER_2
from run_workspace.pvp.tournament_series import TournamentSeries
from ui.pvp_browser.result_export import (
    ResultExportLabels,
    _series_view,
    render_series_image,
)


LABELS = ResultExportLabels(
    title="РЕЗУЛЬТАТ",
    single_game="Одна игра",
    chamber="Зал {number}",
    raw_total="Время",
    adjusted_total="С учётом штрафа",
    difference="Разница",
    winner="Победитель",
    draw="Ничья",
    restarts="Перезапуски",
    paid_restarts="Платные",
    penalty="Штраф",
    technical_loss="Техническое поражение",
)


def _timers(seat: str, seconds: tuple[int, int, int]) -> PlayerMatchTimers:
    return PlayerMatchTimers(
        seat=seat,
        chambers=tuple(
            ChamberTimer("room-series", f"chamber-{index}", value)
            for index, value in enumerate(seconds, 1)
        ),
    )


def _completed_series() -> TournamentSeries:
    series = TournamentSeries(configured_games=2, initial_first_seat=SEAT_PLAYER_1)
    first = calculate_abyss_match_result(
        _timers(SEAT_PLAYER_1, (90, 100, 110)),
        _timers(SEAT_PLAYER_2, (80, 90, 100)),
        restarts_by_seat={SEAT_PLAYER_1: 2, SEAT_PLAYER_2: 0},
        free_restarts=1,
        paid_restarts=(45,),
        source_hash="synthetic-source",
    )
    second = calculate_match_result(
        _timers(SEAT_PLAYER_1, (80, 90, 100)),
        _timers(SEAT_PLAYER_2, (90, 110, 120)),
    )
    return series.with_game_result(1, first).with_game_result(2, second)


class SeriesExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_two_game_series_keeps_seat_columns_stable_and_sums_adjusted_scores(self) -> None:
        series = _completed_series()
        self.assertEqual(series.games[1].first_seat, SEAT_PLAYER_2)

        view = _series_view(
            series, ("Первый", "Второй"), LABELS,
            game_label="Игра {number}", total_label="Серия",
        )
        self.assertEqual(view.names, ("Первый", "Второй"))
        self.assertEqual(view.games[0].chambers[0], ("Зал 1", "1:30", "1:20"))
        self.assertEqual(view.games[0].raw_totals, ("5:00", "4:30"))
        self.assertEqual(view.games[0].adjusted_totals, ("5:45", "4:30"))
        self.assertTrue(view.games[0].has_adjustment)
        self.assertEqual(view.games[0].difference, "Разница: 1:15")
        self.assertEqual(view.games[1].chambers[0], ("Зал 1", "1:20", "1:30"))
        self.assertEqual(view.games[1].raw_totals, ("4:30", "5:20"))
        self.assertFalse(view.games[1].has_adjustment)
        self.assertEqual(view.adjusted_totals, ("10:15", "9:50"))
        self.assertEqual(view.difference, "Разница: 0:25")
        self.assertEqual(view.verdict, "Победитель: Второй")

        image = render_series_image(
            series, "Первый", "Второй", LABELS,
            game_label="Игра {number}", total_label="Серия", width=1000,
        )
        self.assertEqual(image.width(), 1000)
        self.assertGreater(image.height(), 600)
        self.assertEqual(image.pixelColor(0, 0), QColor("#35d5ed"))
        self.assertEqual(image.pixelColor(999, image.height() - 1), QColor("#081724"))

    def test_incomplete_series_and_invalid_player_names_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            render_series_image(TournamentSeries(configured_games=2), "A", "B", LABELS)

        series = _completed_series()
        with self.assertRaises(ValueError):
            render_series_image(series, " ", "B", LABELS)
        with self.assertRaises(ValueError):
            render_series_image(series, "A", None, LABELS)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
