from __future__ import annotations

import unittest

from PySide6.QtCore import QRect, QSize

from ui.utils.owner_icon_badge import (
    owner_badge_rect_for_icon_rect,
    owner_badge_size_for_icon,
)


class OwnerIconBadgeTest(unittest.TestCase):
    def test_default_badge_geometry_matches_accepted_side_icon_ratio(self) -> None:
        icon_rect = QRect(100, 50, 70, 70)
        badge_size = owner_badge_size_for_icon(icon_rect.size())
        badge_rect = owner_badge_rect_for_icon_rect(icon_rect, badge_size)

        self.assertEqual(badge_size, QSize(43, 43))
        self.assertEqual(badge_rect, QRect(114, 79, 43, 43))

    def test_badge_geometry_scales_with_icon_rect(self) -> None:
        small_icon = QRect(100, 50, 70, 70)
        large_icon = QRect(200, 100, 140, 140)

        small_size = owner_badge_size_for_icon(small_icon.size())
        large_size = owner_badge_size_for_icon(large_icon.size())
        small_rect = owner_badge_rect_for_icon_rect(small_icon, small_size)
        large_rect = owner_badge_rect_for_icon_rect(large_icon, large_size)

        self.assertEqual(large_size.width(), small_size.width() * 2)
        self.assertEqual(large_size.height(), small_size.height() * 2)
        self.assertEqual(large_rect.x() - large_icon.x(), (small_rect.x() - small_icon.x()) * 2)
        self.assertEqual(large_rect.y() - large_icon.y(), (small_rect.y() - small_icon.y()) * 2)


if __name__ == "__main__":
    unittest.main()
