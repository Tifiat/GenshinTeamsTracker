"""Interactive public-fixture editor, without AppShell/accounts or simulation.

Run with --engine-root pointing to an explicit local engine source installation.
Apply validates the in-memory draft and displays code; no profile is written.
"""

import argparse
import os
from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--engine-root", type=Path, required=True)
    cli.add_argument("--language", choices=("ru", "en", "pt-br"), default="ru")
    cli.add_argument("--browser", action="store_true", help="Show the real Browser widget with an explicit public team; no AppShell or accounts")
    args = cli.parse_args()
    os.environ["GTT_LANGUAGE"] = args.language
    sys.path.insert(0, str(ROOT))
    from run_workspace.gcsim.engine_store import load_engine_manifest
    from run_workspace.gcsim.rotation_editor.integration import load_environment
    from localization import tr
    from PySide6.QtWidgets import QApplication
    from ui.gcsim_browser.rotation_editor import RotationEditorWindow

    installation = SimpleNamespace(path=args.engine_root, engine_id=args.engine_root.name,
        manifest=load_engine_manifest(args.engine_root))
    environment = load_environment(installation)
    source = (ROOT / "run_workspace/gcsim/smoke_fixtures/rotation_chasca_ororon_furina_bennett.txt").read_text(encoding="utf-8")
    names = {key: tr("rotation.character." + key) for key in ("furina", "chasca", "bennett", "ororon")}
    app = QApplication.instance() or QApplication([])
    if args.browser:
        from ui.gcsim_browser.window import GcsimBrowserWorkspace, GcsimBrowserTeamSlotPreview
        from run_workspace.gcsim.rotation_editor.team import TeamContext, TeamMember
        window = GcsimBrowserWorkspace()
        window.rotation_team_provider = lambda index: TeamContext(f"public:{index}", tuple(TeamMember(key, title, "public:" + key) for key, title in names.items()))
        window._load_rotation_environment = lambda: environment
        window.rotation_editor.setPlainText(source)
        window.set_team_preview(0, [GcsimBrowserTeamSlotPreview(name=title) for title in names.values()])
        window.setWindowTitle(tr("rotation.editor.browser_preview_title"))
        window.resize(1000, 800)
    else:
        window = RotationEditorWindow(source, environment.dialect, names=names, character_options=environment.character_options, allowed_actors=tuple(names))
        window.reload_button.setVisible(False)
        window.setWindowTitle(tr("rotation.editor.preview_title"))
        window.applied.connect(lambda _: window.set_message(tr("rotation.editor.preview_applied")))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
