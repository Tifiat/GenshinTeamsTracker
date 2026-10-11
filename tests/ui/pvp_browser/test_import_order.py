from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


class PvpImportOrderTest(unittest.TestCase):
    def test_shared_tooltip_and_clock_imports_do_not_require_window_to_load_first(self) -> None:
        root = Path(__file__).resolve().parents[3]
        env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "GTT_LANGUAGE": "en", "PYTHONIOENCODING": "utf-8"}
        for first in ("ui.right_panel.pvp._shared", "ui.pvp_browser.draft_clock_widget"):
            with self.subTest(first=first):
                source = (
                    f"import importlib; importlib.import_module('{first}'); "
                    "from ui.right_panel.pvp.draft.panel import PvpDraftRightPanel; "
                    "from ui.pvp_browser import PvpDecksWorkspace, PvpDecksRightPanel; "
                    "from PySide6.QtWidgets import QWidget; "
                    "assert all(issubclass(cls, QWidget) for cls in "
                    "(PvpDraftRightPanel, PvpDecksWorkspace, PvpDecksRightPanel))"
                )
                result = subprocess.run(
                    [sys.executable, "-c", source], cwd=root, env=env,
                    capture_output=True, text=True, encoding="utf-8", timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
