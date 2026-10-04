from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from run_workspace.display_settings import (
    USE_SYSTEM_SCALING_SETTING,
    set_use_system_scaling,
    use_system_scaling,
)


class DisplaySettingsTests(unittest.TestCase):
    def test_missing_or_invalid_setting_defaults_off_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            self.assertFalse(use_system_scaling(settings_file=path))
            self.assertFalse(path.exists())
            for content in ("{}", "[]", "invalid json", json.dumps({USE_SYSTEM_SCALING_SETTING: 2})):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    self.assertFalse(use_system_scaling(settings_file=path))
                    self.assertEqual(path.read_text(encoding="utf-8"), content)

    def test_saved_choice_roundtrips_and_preserves_other_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps({"ui_language": "en", "other": [1, 2]}), encoding="utf-8")
            for enabled in (True, False):
                with self.subTest(enabled=enabled):
                    set_use_system_scaling(enabled, settings_file=path)
                    self.assertEqual(use_system_scaling(settings_file=path), enabled)
                    data = json.loads(path.read_text(encoding="utf-8"))
                    self.assertIs(data[USE_SYSTEM_SCALING_SETTING], enabled)
                    self.assertEqual(data["ui_language"], "en")
                    self.assertEqual(data["other"], [1, 2])

    def test_legacy_string_booleans_use_shared_settings_parser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            for stored, expected in (("true", True), ("on", True), ("false", False), ("off", False)):
                with self.subTest(stored=stored):
                    path.write_text(json.dumps({USE_SYSTEM_SCALING_SETTING: stored}), encoding="utf-8")
                    self.assertIs(use_system_scaling(settings_file=path), expected)


if __name__ == "__main__":
    unittest.main()
