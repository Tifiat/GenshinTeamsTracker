from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ui.artifact_browser.window import ArtifactBrowserWindow


def main() -> int:
    app = QApplication(sys.argv)

    window = ArtifactBrowserWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())