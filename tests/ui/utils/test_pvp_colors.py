from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ui.utils import pvp_colors


class PvpColorCacheTest(unittest.TestCase):
    def setUp(self):
        pvp_colors._color_cache.clear()
        self.addCleanup(pvp_colors._color_cache.clear)

    def test_warmed_card_colors_do_no_filesystem_resolution_or_settings_reads(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            pvp_colors.set_pvp_player_color("player_1", "#123456", settings_file=path)
            colors = [pvp_colors.pvp_player_color(seat, settings_file=path)
                      for seat in ("player_1", "player_2")]
            with patch.object(Path, "resolve", side_effect=AssertionError("Hot color lookup resolved a path")), \
                    patch.object(pvp_colors, "get_app_setting", side_effect=AssertionError("Hot color lookup read settings")):
                for _ in range(400):
                    for index, seat in enumerate(("player_1", "player_2")):
                        self.assertEqual(pvp_colors.pvp_player_color(seat, settings_file=path), colors[index])

    def test_color_write_invalidates_path_aliases_and_keeps_other_seat(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            alias = path.parent / "sub" / ".." / path.name
            pvp_colors.set_pvp_player_color("player_2", "#abcdef", settings_file=path)
            pvp_colors.pvp_player_color("player_1", settings_file=alias)
            pvp_colors.set_pvp_player_color("player_1", "#123456", settings_file=path)
            self.assertEqual(pvp_colors.pvp_player_color("player_1", settings_file=alias), "#123456")
            self.assertEqual(pvp_colors.pvp_player_color("player_2", settings_file=path), "#abcdef")


if __name__ == "__main__":
    unittest.main()
