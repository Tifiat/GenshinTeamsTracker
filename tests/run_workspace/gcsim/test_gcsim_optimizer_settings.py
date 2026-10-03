from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from run_workspace.gcsim.settings import (
    GcsimOptimizerSettings,
    effective_gcsim_optimizer_settings,
    set_gcsim_optimizer_builds_per_group,
    set_gcsim_optimizer_expanded_limits_enabled,
    set_gcsim_optimizer_fast_mode_enabled,
    set_gcsim_optimizer_set_group_limit,
)


class GcsimOptimizerSettingsTests(unittest.TestCase):
    def test_defaults_and_persisted_values_use_the_approved_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.json"

            self.assertEqual(
                effective_gcsim_optimizer_settings(settings_file=settings_file),
                GcsimOptimizerSettings(set_group_limit=3, builds_per_group=3),
            )

            settings_file.write_text(
                json.dumps(
                    {
                        "ui_language": "en",
                        "gcsim_optimizer_set_group_limit": 20,
                        "gcsim_optimizer_builds_per_group": 0,
                        "gcsim_optimizer_fast_mode": True,
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                effective_gcsim_optimizer_settings(settings_file=settings_file),
                GcsimOptimizerSettings(
                    set_group_limit=10,
                    builds_per_group=1,
                    fast_mode=True,
                ),
            )

    def test_setting_changes_only_write_to_the_requested_settings_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.json"
            settings_file.write_text(
                json.dumps({"ui_language": "pt-br"}),
                encoding="utf-8",
            )

            set_gcsim_optimizer_set_group_limit(5, settings_file=settings_file)
            set_gcsim_optimizer_builds_per_group(4, settings_file=settings_file)
            set_gcsim_optimizer_fast_mode_enabled(True, settings_file=settings_file)

            data = json.loads(settings_file.read_text(encoding="utf-8"))

        self.assertEqual(data["ui_language"], "pt-br")
        self.assertEqual(data["gcsim_optimizer_set_group_limit"], 5)
        self.assertEqual(data["gcsim_optimizer_builds_per_group"], 4)
        self.assertTrue(data["gcsim_optimizer_fast_mode"])

    def test_expanded_setting_lifts_recommendations_and_disabling_restores_them(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings_file = Path(temporary_directory) / "settings.json"

            set_gcsim_optimizer_expanded_limits_enabled(
                True,
                settings_file=settings_file,
            )
            set_gcsim_optimizer_set_group_limit(50, settings_file=settings_file)
            set_gcsim_optimizer_builds_per_group(49, settings_file=settings_file)

            self.assertEqual(
                effective_gcsim_optimizer_settings(settings_file=settings_file),
                GcsimOptimizerSettings(
                    set_group_limit=50,
                    builds_per_group=49,
                    expanded_limits=True,
                ),
            )

            set_gcsim_optimizer_expanded_limits_enabled(
                False,
                settings_file=settings_file,
            )
            self.assertEqual(
                effective_gcsim_optimizer_settings(settings_file=settings_file),
                GcsimOptimizerSettings(set_group_limit=5, builds_per_group=11),
            )
            data = json.loads(settings_file.read_text(encoding="utf-8"))

        self.assertFalse(data["gcsim_optimizer_expanded_limits"])
        self.assertEqual(data["gcsim_optimizer_set_group_limit"], 5)
        self.assertEqual(data["gcsim_optimizer_builds_per_group"], 11)

    def test_recommended_and_expanded_limits_and_mode_defaults(self) -> None:
        from run_workspace.gcsim.settings import optimizer_output_limits
        self.assertEqual(optimizer_output_limits(False), (5, 11))
        self.assertEqual(optimizer_output_limits(True), (10, 41))
        self.assertEqual(optimizer_output_limits(False, True), (50, 101))
        self.assertEqual(optimizer_output_limits(True, True), (50, 101))
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "settings.json"
            self.assertEqual(effective_gcsim_optimizer_settings(settings_file=settings_file), GcsimOptimizerSettings(3, 3))
            set_gcsim_optimizer_fast_mode_enabled(True, settings_file=settings_file)
            self.assertEqual(effective_gcsim_optimizer_settings(settings_file=settings_file), GcsimOptimizerSettings(5, 21, True))
            set_gcsim_optimizer_expanded_limits_enabled(True, settings_file=settings_file)
            set_gcsim_optimizer_set_group_limit(999999, settings_file=settings_file)
            set_gcsim_optimizer_builds_per_group(999999, settings_file=settings_file)
            self.assertEqual(effective_gcsim_optimizer_settings(settings_file=settings_file), GcsimOptimizerSettings(50, 101, True, True))


if __name__ == "__main__":
    unittest.main()
