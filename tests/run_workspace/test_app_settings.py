from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from run_workspace.app_settings import (
    get_app_bool_setting,
    read_app_settings,
    set_app_bool_setting,
)
from ui.utils.pvp_colors import (
    PVP_PLAYER_1_COLOR_DEFAULT,
    PVP_PLAYER_2_COLOR_DEFAULT,
    pvp_player_color,
    reset_pvp_player_colors,
    set_pvp_player_color,
)


class AppSettingsTest(unittest.TestCase):
    def test_bool_setting_write_preserves_existing_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"
            settings_file.write_text(
                json.dumps({"ui_language": "en"}, indent=2),
                encoding="utf-8",
            )

            set_app_bool_setting(
                "abyss_fact_dps_multi_target_enabled",
                True,
                settings_file=settings_file,
            )

            data = read_app_settings(settings_file)

        self.assertEqual(data["ui_language"], "en")
        self.assertTrue(data["abyss_fact_dps_multi_target_enabled"])

    def test_missing_bool_setting_uses_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"

            enabled = get_app_bool_setting(
                "abyss_fact_dps_multi_target_enabled",
                False,
                settings_file=settings_file,
            )

        self.assertFalse(enabled)

    def test_pvp_player_colors_are_scoped_settings_with_stable_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"

            self.assertEqual(
                pvp_player_color("player_1", settings_file=settings_file),
                PVP_PLAYER_1_COLOR_DEFAULT,
            )
            self.assertEqual(
                pvp_player_color("player_2", settings_file=settings_file),
                PVP_PLAYER_2_COLOR_DEFAULT,
            )
            set_pvp_player_color(
                "player_1",
                "#123ABC",
                settings_file=settings_file,
            )
            self.assertEqual(
                pvp_player_color("player_1", settings_file=settings_file),
                "#123abc",
            )

            reset_pvp_player_colors(settings_file=settings_file)

            self.assertEqual(
                pvp_player_color("player_1", settings_file=settings_file),
                PVP_PLAYER_1_COLOR_DEFAULT,
            )
            self.assertEqual(
                pvp_player_color("player_2", settings_file=settings_file),
                PVP_PLAYER_2_COLOR_DEFAULT,
            )


if __name__ == "__main__":
    unittest.main()
