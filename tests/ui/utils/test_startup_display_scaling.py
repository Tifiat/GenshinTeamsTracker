from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

from run_workspace.display_settings import set_use_system_scaling
from ui.utils.app_scaling import (
    QT_ENABLE_HIGHDPI_SCALING_ENV,
    QT_FONT_DPI_ENV,
    QT_SCALE_FACTOR_ENV,
    configure_startup_display_scaling,
)


class StartupDisplayScalingTests(unittest.TestCase):
    def test_off_normalizes_windows_geometry_and_font_dpi_on_large_display(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            env = {
                QT_ENABLE_HIGHDPI_SCALING_ENV: "1", QT_FONT_DPI_ENV: "144",
                "QT_SCREEN_SCALE_FACTORS": "1.5;2", "QT_USE_PHYSICAL_DPI": "1",
            }
            result = configure_startup_display_scaling(
                env, platform="win32", settings_file=path, monitor_width_detector=lambda: 2560
            )
            self.assertEqual(env[QT_ENABLE_HIGHDPI_SCALING_ENV], "0")
            self.assertEqual(env[QT_FONT_DPI_ENV], "96")
            self.assertNotIn("QT_SCREEN_SCALE_FACTORS", env)
            self.assertNotIn("QT_USE_PHYSICAL_DPI", env)
            self.assertNotIn(QT_SCALE_FACTOR_ENV, env)
            self.assertEqual(result.reason, "auto_no_downscale")
            self.assertFalse(path.exists())

    def test_on_restores_windows_dpi_without_upscaling_physical_reference_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            set_use_system_scaling(True, settings_file=path)
            env = {
                QT_ENABLE_HIGHDPI_SCALING_ENV: "0", QT_FONT_DPI_ENV: "96",
                "QT_SCREEN_SCALE_FACTORS": "1.5;2", "QT_USE_PHYSICAL_DPI": "1",
            }
            result = configure_startup_display_scaling(
                env, platform="win32", settings_file=path, monitor_width_detector=lambda: 1920
            )
            self.assertEqual(env[QT_ENABLE_HIGHDPI_SCALING_ENV], "1")
            self.assertNotIn(QT_FONT_DPI_ENV, env)
            self.assertNotIn("QT_SCREEN_SCALE_FACTORS", env)
            self.assertNotIn("QT_USE_PHYSICAL_DPI", env)
            self.assertNotIn(QT_SCALE_FACTOR_ENV, env)
            self.assertEqual(result.scale, 1.0)

    def test_physical_rdp_downscale_is_the_same_with_both_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            for enabled in (False, True):
                with self.subTest(enabled=enabled):
                    set_use_system_scaling(enabled, settings_file=path)
                    env = {}
                    result = configure_startup_display_scaling(
                        env, platform="win32", settings_file=path, monitor_width_detector=lambda: 1366
                    )
                    self.assertEqual(env[QT_SCALE_FACTOR_ENV], "0.711458")
                    self.assertAlmostEqual(result.scale, 1366 / 1920)
                    self.assertEqual(env[QT_ENABLE_HIGHDPI_SCALING_ENV], str(int(enabled)))

    def test_saved_choice_is_reread_on_next_startup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            for enabled in (True, False):
                set_use_system_scaling(enabled, settings_file=path)
                env = {}
                configure_startup_display_scaling(
                    env, platform="win32", settings_file=path, monitor_width_detector=lambda: 2560
                )
                self.assertEqual(env[QT_ENABLE_HIGHDPI_SCALING_ENV], str(int(enabled)))

    def test_manual_app_scale_overrides_remain_independent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            for enabled in (False, True):
                set_use_system_scaling(enabled, settings_file=path)
                for env, expected in (({QT_SCALE_FACTOR_ENV: "0.8"}, "0.8"), ({"GTT_UI_SCALE": "0.9"}, "0.9")):
                    with self.subTest(enabled=enabled, env=env):
                        configure_startup_display_scaling(
                            env, platform="win32", settings_file=path, monitor_width_detector=lambda: 1366
                        )
                        self.assertEqual(env[QT_SCALE_FACTOR_ENV], expected)
                        self.assertEqual(env[QT_ENABLE_HIGHDPI_SCALING_ENV], str(int(enabled)))

    def test_failed_monitor_detection_still_applies_saved_os_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text("invalid json", encoding="utf-8")
            env = {}
            result = configure_startup_display_scaling(
                env, platform="win32", settings_file=path, monitor_width_detector=lambda: None
            )
            self.assertEqual(env[QT_ENABLE_HIGHDPI_SCALING_ENV], "0")
            self.assertEqual(env[QT_FONT_DPI_ENV], "96")
            self.assertEqual(result.reason, "monitor_detection_failed")
            self.assertNotIn(QT_SCALE_FACTOR_ENV, env)
            self.assertEqual(path.read_text(encoding="utf-8"), "invalid json")

    def test_non_windows_native_scaling_is_preserved(self) -> None:
        env = {QT_ENABLE_HIGHDPI_SCALING_ENV: "1", QT_FONT_DPI_ENV: "120", "QT_SCREEN_SCALE_FACTORS": "2"}
        original = dict(env)
        with patch("ui.utils.app_scaling.use_system_scaling") as read_setting:
            result = configure_startup_display_scaling(env, platform="linux")
        self.assertEqual(result.reason, "unsupported_platform")
        self.assertEqual(env, original)
        read_setting.assert_not_called()

    def test_launcher_applies_scaling_before_importing_app_shell(self) -> None:
        from ui import app_shell_smoke

        events = []
        shell = ModuleType("ui.app_shell")
        shell.launch_app_shell = lambda: events.append("launch") or 0
        original_import = __import__

        def import_spy(name, *args, **kwargs):
            if name == "ui.app_shell":
                events.append("import")
            return original_import(name, *args, **kwargs)

        with (
            patch.dict(sys.modules, {"ui.app_shell": shell}),
            patch("builtins.__import__", side_effect=import_spy),
            patch("run_workspace.profile_control.supervise_app", side_effect=AssertionError("No real supervisor in a fixture")) as supervisor,
            patch("run_workspace.profile_control.profile_operation_lock", return_value=nullcontext()),
            patch("run_workspace.profile_context.bootstrap_profile", side_effect=lambda: events.append("profile")),
            patch.object(app_shell_smoke, "configure_startup_display_scaling", side_effect=lambda: events.append("scale")),
        ):
            self.assertEqual(app_shell_smoke.main(["--profile-child"]), 0)
        supervisor.assert_not_called()
        self.assertEqual(events, ["profile", "scale", "import", "launch"])

    def test_public_launcher_delegates_without_bootstrapping_or_importing_ui(self) -> None:
        from ui import app_shell_smoke

        for arguments, forwarded in (([], []), (["--perf-log"], ["--perf-log"])):
            with (
                self.subTest(arguments=arguments),
                patch("run_workspace.profile_control.supervise_app", return_value=37) as supervisor,
                patch("run_workspace.profile_context.bootstrap_profile", side_effect=AssertionError("No real profile mutation")) as bootstrap,
                patch.object(app_shell_smoke, "configure_startup_display_scaling") as scaling,
            ):
                self.assertEqual(app_shell_smoke.main(arguments), 37)
                supervisor.assert_called_once_with(forwarded)
                bootstrap.assert_not_called()
                scaling.assert_not_called()


if __name__ == "__main__":
    unittest.main()
