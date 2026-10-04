from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from run_workspace.display_settings import set_use_system_scaling


PROJECT_ROOT = Path(__file__).resolve().parents[3]
QT_PROBE = """
import json
import sys
from ui.utils.app_scaling import configure_startup_display_scaling
assert 'PySide6.QtGui' not in sys.modules
configure_startup_display_scaling(
    platform='win32', settings_file=sys.argv[1],
    monitor_width_detector=lambda: int(sys.argv[3]),
)
from PySide6.QtGui import QFont, QFontMetricsF, QGuiApplication
app = QGuiApplication(['display-dpi-test', '-platform', 'offscreen:configfile=' + sys.argv[2]])
screen = app.primaryScreen()
font = QFont('Arial', 12)
print(json.dumps({
    'logical_dpi': screen.logicalDotsPerInch(),
    'dpr': screen.devicePixelRatio(),
    'logical_width': screen.geometry().width(),
    'font_height': QFontMetricsF(font).height(),
}))
"""


class StartupDisplayScalingQtTests(unittest.TestCase):
    def _probe(self, *, enabled: bool, width: int, native_dpi: int) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            settings = folder / "settings.json"
            set_use_system_scaling(enabled, settings_file=settings)
            config = folder / "offscreen.json"
            config.write_text(json.dumps({"screens": [{
                "name": "dpi-test", "x": 0, "y": 0,
                "width": width, "height": 1440,
                "logicalDpi": native_dpi, "logicalBaseDpi": 96, "dpr": 1.0,
            }]}), encoding="utf-8")
            env = dict(os.environ)
            for key in (
                "GTT_UI_SCALE", "QT_SCALE_FACTOR", "QT_SCALE_FACTOR_ROUNDING_POLICY",
                "QT_ENABLE_HIGHDPI_SCALING", "QT_FONT_DPI", "QT_SCREEN_SCALE_FACTORS",
                "QT_USE_PHYSICAL_DPI", "GTT_PERF_LOG",
            ):
                env.pop(key, None)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["QT_QPA_PLATFORM"] = "offscreen"
            completed = subprocess.run(
                # Qt separates platform options with ':', including Windows drive
                # prefixes. A relative config path works on every test platform.
                [sys.executable, "-c", QT_PROBE, str(settings),
                 os.path.relpath(config, PROJECT_ROOT).replace("\\", "/"), str(width)],
                cwd=PROJECT_ROOT, env=env, capture_output=True, text=True,
                timeout=20,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            return json.loads(completed.stdout.strip())

    def test_off_ignores_simulated_windows_150_percent_in_geometry_and_point_fonts(self) -> None:
        normal = self._probe(enabled=False, width=2560, native_dpi=96)
        scaled = self._probe(enabled=False, width=2560, native_dpi=144)
        self.assertEqual(scaled["logical_dpi"], 96)
        self.assertEqual(scaled["dpr"], 1)
        self.assertEqual(scaled["logical_width"], 2560)
        self.assertAlmostEqual(scaled["font_height"], normal["font_height"])

    def test_on_uses_simulated_windows_150_percent(self) -> None:
        scaled = self._probe(enabled=True, width=2560, native_dpi=144)
        self.assertEqual(scaled["dpr"], 1.5)
        self.assertAlmostEqual(scaled["logical_width"], 2560 / 1.5, delta=1)
        self.assertEqual(scaled["logical_dpi"], 96)

    def test_small_rdp_at_100_percent_preserves_adaptive_geometry_and_fonts(self) -> None:
        off = self._probe(enabled=False, width=1366, native_dpi=96)
        on = self._probe(enabled=True, width=1366, native_dpi=96)
        self.assertAlmostEqual(off["dpr"], 1366 / 1920, places=5)
        self.assertEqual(off["logical_width"], 1920)
        self.assertEqual(off["logical_dpi"], 96)
        self.assertEqual(off, on)


if __name__ == "__main__":
    unittest.main()
