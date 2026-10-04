from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from run_workspace import app_settings
from run_workspace.settings_defaults import (
    DEFAULT_SETTINGS,
    default_for,
    default_settings,
    settings_default,
)


class SettingsDefaultsTest(unittest.TestCase):
    def test_defaults_include_known_preferences_and_are_copied(self) -> None:
        defaults = default_settings()

        self.assertEqual(defaults["ui_language"], "ru")
        self.assertTrue(defaults["hoyolab_change_equipment_on_import"])
        self.assertFalse(defaults["hoyolab_login_hint_dismissed"])
        self.assertFalse(defaults["gcsim_optimizer_fast_mode"])
        self.assertEqual(defaults["gcsim_optimizer_set_group_limit"], 3)
        self.assertEqual(defaults["gcsim_optimizer_builds_per_group"], 3)
        defaults["hoyolab_login_hint_dismissed"] = True
        self.assertFalse(default_settings()["hoyolab_login_hint_dismissed"])
        self.assertFalse(DEFAULT_SETTINGS["hoyolab_login_hint_dismissed"])

    def test_optimizer_limits_follow_context_fast_mode(self) -> None:
        context = {"gcsim_optimizer_fast_mode": True}

        self.assertEqual(
            default_for("gcsim_optimizer_set_group_limit", settings_context=context),
            5,
        )
        self.assertEqual(
            settings_default("gcsim_optimizer_builds_per_group", context=context),
            21,
        )
        self.assertEqual(
            default_for("gcsim_optimizer_set_group_limit", settings_context={"gcsim_optimizer_fast_mode": "bad"}),
            3,
        )

    def test_default_consumers_use_the_central_registry(self) -> None:
        from hoyolab_export.account_equipment import (
            AUTO_APPLY_HOYOLAB_EQUIPMENT_ON_IMPORT_DEFAULT,
        )
        from localization.i18n import DEFAULT_LANGUAGE
        from run_workspace.gcsim.settings import (
            GcsimOptimizerSettings,
            optimizer_output_defaults,
        )
        from ui.utils.pvp_colors import (
            PVP_PLAYER_1_COLOR_DEFAULT,
            PVP_PLAYER_2_COLOR_DEFAULT,
        )

        self.assertEqual(DEFAULT_LANGUAGE, settings_default("ui_language"))
        self.assertEqual(
            AUTO_APPLY_HOYOLAB_EQUIPMENT_ON_IMPORT_DEFAULT,
            settings_default("hoyolab_change_equipment_on_import"),
        )
        self.assertEqual(PVP_PLAYER_1_COLOR_DEFAULT, settings_default("pvp_player_1_color"))
        self.assertEqual(PVP_PLAYER_2_COLOR_DEFAULT, settings_default("pvp_player_2_color"))
        self.assertEqual(
            (
                GcsimOptimizerSettings().set_group_limit,
                GcsimOptimizerSettings().builds_per_group,
            ),
            (
                settings_default("gcsim_optimizer_set_group_limit"),
                settings_default("gcsim_optimizer_builds_per_group"),
            ),
        )
        for fast_mode in (False, True):
            context = {"gcsim_optimizer_fast_mode": fast_mode}
            self.assertEqual(
                optimizer_output_defaults(fast_mode),
                (
                    settings_default("gcsim_optimizer_set_group_limit", context=context),
                    settings_default("gcsim_optimizer_builds_per_group", context=context),
                ),
            )

    def test_known_registry_default_beats_legacy_fallback_unknown_uses_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"

            self.assertFalse(app_settings.get_app_bool_setting(
                "gcsim_optimizer_fast_mode", True, settings_file=settings_file,
            ))
            self.assertEqual(
                app_settings.get_app_setting("new_extension_setting", "legacy", settings_file=settings_file),
                "legacy",
            )

    def test_persisted_values_override_defaults_and_derive_optimizer_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"
            app_settings.write_app_settings({
                "gcsim_optimizer_fast_mode": True,
                "hoyolab_change_equipment_on_import": False,
            }, settings_file)

            self.assertTrue(app_settings.get_app_bool_setting(
                "gcsim_optimizer_fast_mode", False, settings_file=settings_file,
            ))
            self.assertFalse(app_settings.get_app_bool_setting(
                "hoyolab_change_equipment_on_import", True, settings_file=settings_file,
            ))
            self.assertEqual(app_settings.get_app_setting(
                "gcsim_optimizer_set_group_limit", 3, settings_file=settings_file,
            ), 5)
            self.assertEqual(app_settings.get_app_setting(
                "gcsim_optimizer_builds_per_group", 3, settings_file=settings_file,
            ), 21)

    def test_invalid_boolean_uses_registered_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"
            app_settings.write_app_settings({
                "hoyolab_login_hint_dismissed": "not-a-bool",
                "extension_toggle": "not-a-bool",
            }, settings_file)

            self.assertFalse(app_settings.get_app_bool_setting(
                "hoyolab_login_hint_dismissed", True, settings_file=settings_file,
            ))
            self.assertTrue(app_settings.get_app_bool_setting(
                "extension_toggle", True, settings_file=settings_file,
            ))

    def test_reset_clears_unknown_keys_and_returns_effective_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "nested" / "settings.json"
            app_settings.write_app_settings({
                "ui_language": "en",
                "hoyolab_login_hint_dismissed": True,
                "obsolete_dont_show_again": True,
                "future_dialog_suppressed": True,
            }, settings_file)

            effective = app_settings.reset_app_settings(settings_file)

            self.assertEqual(app_settings.read_app_settings(settings_file), {})
            self.assertEqual(effective["ui_language"], "ru")
            self.assertFalse(effective["hoyolab_login_hint_dismissed"])
            self.assertEqual(app_settings.get_app_setting("ui_language", "en", settings_file=settings_file), "ru")
            self.assertFalse(app_settings.get_app_bool_setting(
                "hoyolab_login_hint_dismissed", True, settings_file=settings_file,
            ))
            self.assertEqual(
                app_settings.get_app_setting("obsolete_dont_show_again", True, settings_file=settings_file),
                True,
            )

    def test_failed_atomic_reset_preserves_previous_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"
            original = {"hoyolab_login_hint_dismissed": True, "keep": "old"}
            app_settings.write_app_settings(original, settings_file)

            with patch.object(app_settings.os, "replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    app_settings.reset_app_settings(settings_file)

            self.assertEqual(app_settings.read_app_settings(settings_file), original)
            self.assertEqual(list(settings_file.parent.glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
