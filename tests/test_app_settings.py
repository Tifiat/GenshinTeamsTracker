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


if __name__ == "__main__":
    unittest.main()
