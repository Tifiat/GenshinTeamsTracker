from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics, QImage
from PySide6.QtWidgets import QApplication

from run_workspace.pvp.match_result import (
    ChamberTimer,
    PlayerMatchTimers,
    calculate_abyss_match_result,
    calculate_match_result,
)
from run_workspace.pvp.schedule import SEAT_PLAYER_1, SEAT_PLAYER_2
from ui.pvp_browser.result_export import (
    ResultExportLabels,
    _view,
    _wrapped,
    render_result_image,
    save_result_png,
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
            ChamberTimer("room-12", f"chamber-{index}", value)
            for index, value in enumerate(seconds, 1)
        ),
    )


class ResultExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.font_ids = []
        if not QFontDatabase.families() and os.name == "nt":
            for filename in ("segoeui.ttf", "segoeuib.ttf"):
                font_id = QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / filename))
                if font_id >= 0:
                    cls.font_ids.append(font_id)

    @classmethod
    def tearDownClass(cls) -> None:
        for font_id in cls.font_ids:
            QFontDatabase.removeApplicationFont(font_id)

    def test_free_game_uses_three_actual_chambers_and_raw_totals(self) -> None:
        result = calculate_match_result(
            _timers(SEAT_PLAYER_1, (90, 100, 110)),
            _timers(SEAT_PLAYER_2, (80, 90, 150)),
        )
        view = _view(result, ("Первый", "Второй"), LABELS)
        self.assertEqual(view.chambers, (
            ("Зал 1", "1:30", "1:20"),
            ("Зал 2", "1:40", "1:30"),
            ("Зал 3", "1:50", "2:30"),
        ))
        self.assertEqual(view.raw_totals, ("5:00", "5:20"))
        self.assertIsNone(view.adjusted_totals)
        self.assertEqual(view.verdict, "Победитель: Первый")
        self.assertEqual(view.difference, "Разница: 0:20")

        with TemporaryDirectory() as temporary:
            destination = Path(temporary) / "chosen result.png"
            image = render_result_image(result, "Первый", "Второй", LABELS)
            self.assertEqual(image.width(), 1400)
            self.assertGreater(image.height(), 800)
            self.assertFalse(destination.exists())
            save_result_png(image, destination)
            loaded = QImage(str(destination))
            self.assertEqual(loaded.size(), image.size())
            self.assertGreater(destination.stat().st_size, 5000)
            self.assertNotEqual(loaded.pixelColor(0, 0), loaded.pixelColor(100, 200))

    def test_source_scoring_displays_actual_adjustment_without_private_fields(self) -> None:
        result = calculate_abyss_match_result(
            _timers(SEAT_PLAYER_1, (90, 100, 110)),
            _timers(SEAT_PLAYER_2, (80, 90, 100)),
            restarts_by_seat={SEAT_PLAYER_1: 2, SEAT_PLAYER_2: 0},
            free_restarts=1,
            paid_restarts=(45,),
            source_hash="private-rules-hash",
        )
        view = _view(result, ("А", "Б"), LABELS)
        self.assertEqual(view.raw_totals, ("5:00", "4:30"))
        self.assertEqual(view.adjusted_totals, ("5:45", "4:30"))
        self.assertEqual(view.source_details[0], (
            "Перезапуски: 2", "Платные: 1", "Штраф: +0:45",
        ))
        self.assertEqual(view.verdict, "Победитель: Б")
        self.assertEqual(view.difference, "Разница: 1:15")
        self.assertNotIn("private-rules-hash", repr(view))
        image = render_result_image(result, "А", "Б", LABELS)
        self.assertEqual(image.width(), 1400)
        self.assertGreater(image.height(), 900)

    def test_tie_and_long_cyrillic_names_remain_readable(self) -> None:
        name = "Очень длинное имя игрока из нескольких русских слов " * 4
        result = calculate_match_result(
            _timers(SEAT_PLAYER_1, (100, 100, 100)),
            _timers(SEAT_PLAYER_2, (120, 90, 90)),
        )
        view = _view(result, (name, "Соперник"), LABELS)
        self.assertEqual(view.verdict, "Ничья")
        self.assertEqual(view.difference, "Разница: 0:00")
        font = QFont("Segoe UI", 31)
        font.setBold(True)
        wrapped = _wrapped(name, font, 576)
        self.assertGreater(len(wrapped), 2)
        self.assertEqual("".join(wrapped).replace(" ", ""), name.replace(" ", ""))
        self.assertTrue(all(QFontMetrics(font).horizontalAdvance(line) <= 576 for line in wrapped))
        image = render_result_image(result, name, "Соперник", LABELS)
        self.assertGreater(image.height(), 900)


if __name__ == "__main__":
    unittest.main()
