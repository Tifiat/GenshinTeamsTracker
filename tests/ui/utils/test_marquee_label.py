from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication

from ui.utils.marquee_label import MarqueeButton


class MarqueeButtonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_inactive_button_does_not_create_timer_for_text_sync(self) -> None:
        button = MarqueeButton("Very long character target name")

        self.assertIsNone(button._timer)

        button.setText("Another long character target name")
        button._sync_timer(text_width=500, available_width=10)

        self.assertIsNone(button._timer)

    def test_active_overflow_creates_timer_on_demand(self) -> None:
        button = MarqueeButton("Very long character target name")
        button.setCheckable(True)
        button.setChecked(True)

        button._sync_timer(text_width=500, available_width=10)

        self.assertIsNotNone(button._timer)
        self.assertTrue(button._timer.isActive())


if __name__ == "__main__":
    unittest.main()
