"""The HoYoLAB equipment choice has a first-run default and a saved override."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from hoyolab_export.account_equipment import AUTO_APPLY_HOYOLAB_EQUIPMENT_ON_IMPORT_DEFAULT
from hoyolab_export.import_settings import (
    CHANGE_EQUIPMENT_SETTING,
    change_equipment_on_import,
    set_change_equipment_on_import,
)


class ImportSettingsTest(unittest.TestCase):
    def test_first_run_defaults_to_changing_equipment_without_writing_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_file = Path(temp_dir) / "settings.json"
            self.assertTrue(AUTO_APPLY_HOYOLAB_EQUIPMENT_ON_IMPORT_DEFAULT)
            self.assertTrue(change_equipment_on_import(settings_file=settings_file))
            self.assertFalse(settings_file.exists())

            settings_file.write_text(json.dumps({"ui_language": "ru"}), encoding="utf-8")
            self.assertTrue(change_equipment_on_import(settings_file=settings_file))

    def test_saved_disabled_choice_survives_future_reads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_file = Path(temp_dir) / "settings.json"
            set_change_equipment_on_import(False, settings_file=settings_file)
            self.assertFalse(change_equipment_on_import(settings_file=settings_file))
            saved = json.loads(settings_file.read_text(encoding="utf-8"))
            self.assertIs(saved[CHANGE_EQUIPMENT_SETTING], False)

            set_change_equipment_on_import(True, settings_file=settings_file)
            self.assertTrue(change_equipment_on_import(settings_file=settings_file))


if __name__ == "__main__":
    unittest.main()
