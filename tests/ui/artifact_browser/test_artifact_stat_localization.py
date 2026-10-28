from __future__ import annotations

import unittest

from ui.artifact_browser.stat_types import (
    ATK_PERCENT,
    ENERGY_RECHARGE,
    localized_stat_label,
    stat_label_language,
)


class ArtifactStatLocalizationTest(unittest.TestCase):
    def test_content_language_maps_to_supported_locale(self) -> None:
        self.assertEqual(stat_label_language("ru-ru"), "ru")
        self.assertEqual(stat_label_language("en-us"), "en")
        self.assertEqual(stat_label_language("pt-br"), "pt-br")

    def test_localized_stat_label_uses_content_language(self) -> None:
        self.assertEqual(
            localized_stat_label(
                ENERGY_RECHARGE,
                language="ru-ru",
                fallback="Energy Recharge",
            ),
            "Восстановление энергии",
        )
        self.assertEqual(
            localized_stat_label(
                ATK_PERCENT,
                language="en-us",
                fallback="Сила атаки %",
            ),
            "ATK %",
        )

    def test_localized_stat_label_keeps_fallback_for_unsupported_language(self) -> None:
        self.assertEqual(
            localized_stat_label(
                ENERGY_RECHARGE,
                language="de-de",
                fallback="Energy Recharge",
            ),
            "Energy Recharge",
        )


if __name__ == "__main__":
    unittest.main()
