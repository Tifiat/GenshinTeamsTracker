from __future__ import annotations

import unittest

from ui.utils.app_scaling import (
    MIN_AUTO_SCALE,
    QT_SCALE_FACTOR_ENV,
    configure_startup_ui_scale,
)


class AppScalingTest(unittest.TestCase):
    def test_forced_scale_sets_qt_scale_factor(self) -> None:
        env = {"GTT_UI_SCALE": "0.75"}

        result = configure_startup_ui_scale(env, platform="linux")

        self.assertEqual(result.reason, "forced")
        self.assertEqual(result.action, "set")
        self.assertEqual(result.scale, 0.75)
        self.assertEqual(env[QT_SCALE_FACTOR_ENV], "0.75")

    def test_forced_scale_never_upscales(self) -> None:
        env = {"GTT_UI_SCALE": "1.5"}

        result = configure_startup_ui_scale(env, platform="linux")

        self.assertEqual(result.scale, 1.0)
        self.assertEqual(env[QT_SCALE_FACTOR_ENV], "1")

    def test_existing_qt_scale_factor_is_preserved_without_override(self) -> None:
        env = {QT_SCALE_FACTOR_ENV: "0.8"}

        result = configure_startup_ui_scale(
            env,
            platform="win32",
            monitor_width_detector=lambda: 1366,
        )

        self.assertEqual(result.reason, "existing_qt_scale_factor")
        self.assertEqual(result.action, "skipped")
        self.assertEqual(env[QT_SCALE_FACTOR_ENV], "0.8")

    def test_auto_scale_downscales_small_windows_monitor(self) -> None:
        env = {"GTT_UI_SCALE": "auto"}

        result = configure_startup_ui_scale(
            env,
            platform="win32",
            monitor_width_detector=lambda: 1366,
        )

        self.assertEqual(result.reason, "auto")
        self.assertEqual(result.action, "set")
        self.assertAlmostEqual(result.scale or 0.0, 1366 / 1920)
        self.assertEqual(env[QT_SCALE_FACTOR_ENV], "0.711458")

    def test_auto_scale_leaves_reference_or_wider_monitor_untouched(self) -> None:
        env = {}

        result = configure_startup_ui_scale(
            env,
            platform="win32",
            monitor_width_detector=lambda: 2560,
        )

        self.assertEqual(result.reason, "auto_no_downscale")
        self.assertEqual(result.action, "skipped")
        self.assertNotIn(QT_SCALE_FACTOR_ENV, env)

    def test_auto_scale_clamps_very_small_detected_width(self) -> None:
        env = {}

        result = configure_startup_ui_scale(
            env,
            platform="win32",
            monitor_width_detector=lambda: 400,
        )

        self.assertEqual(result.scale, MIN_AUTO_SCALE)
        self.assertEqual(env[QT_SCALE_FACTOR_ENV], "0.6")

    def test_non_windows_auto_scale_is_skipped(self) -> None:
        env = {"GTT_UI_SCALE": "auto"}

        result = configure_startup_ui_scale(env, platform="linux")

        self.assertEqual(result.reason, "unsupported_platform")
        self.assertEqual(result.action, "skipped")
        self.assertNotIn(QT_SCALE_FACTOR_ENV, env)


if __name__ == "__main__":
    unittest.main()

