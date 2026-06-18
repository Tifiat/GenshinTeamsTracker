from __future__ import annotations

import os
from contextlib import closing
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()

from PySide6.QtWidgets import QApplication

from hoyolab_export.artifact_db import connect_db, init_db
from ui.pvp_browser.window import PvpWorkspace
from ui.right_panel.pvp._shared import PVP_DRAFT_STAGE_COMPLETED_RESULT
from ui.right_panel.pvp.play.panel import PvpPlayRightPanel

# This smoke drives the left/main PvP workspace while instantiating the moved
# right-panel play page from ui.right_panel.pvp.


def main() -> int:
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "pvp-smoke.sqlite"
        _seed_scoped_equipment_db(db_path)
        workspace = PvpWorkspace(
            db_path=db_path,
            deck_dir=temp_dir,
            character_assets_provider=lambda: _character_assets(24),
            weapon_assets_provider=lambda: [_weapon_asset()],
        )
        if not workspace.decks_workspace.create_deck("Mirror"):
            print("failed: create deck")
            return 1
        if not workspace.decks_workspace.save_edit(name="Mirror"):
            print("failed: save deck")
            return 1

        play_panel = PvpPlayRightPanel(workspace)
        play_panel.start_button.click()
        app.processEvents()
        if workspace.active_draft_session is None:
            print("failed: draft session was not created")
            return 1

        _complete_draft(workspace, app)
        if not workspace.continue_to_assignment():
            print("failed: continue to assignment")
            return 1
        if workspace.build_flow_context is None:
            print("failed: scoped build context missing")
            return 1
        _assign_all_picks(workspace)
        _assign_weapons(workspace)
        for seat in ("player_1", "player_2"):
            if not workspace.ready_build_seat(seat):
                print(f"failed: ready {seat}: {workspace.last_draft_status()}")
                return 1
        if not workspace.weapons_ready():
            print("failed: scoped ready validation")
            return 1
        for index, text in enumerate(("01:00", "01:00", "01:00")):
            workspace.set_timer_text("player_1", index, text)
        for index, text in enumerate(("01:10", "01:00", "01:00")):
            workspace.set_timer_text("player_2", index, text)
        if not workspace.finalize_match_result():
            print("failed: finalize result")
            return 1

        result = workspace.active_draft_session.controller.state.match_result
        if result is None or workspace.draft_stage != PVP_DRAFT_STAGE_COMPLETED_RESULT:
            print("failed: result missing")
            return 1
        print(
            "PvP UI full-flow smoke: "
            f"status={result.status}, winner={result.winner_seat}, "
            f"diff={result.seconds_difference}s"
        )
    return 0


def _complete_draft(workspace: PvpWorkspace, app: QApplication) -> None:
    guard = 0
    while not workspace.active_draft_session.board_dict()["status"]["draft_finished"]:
        guard += 1
        if guard >= 40:
            raise RuntimeError("draft did not complete")
        workspace.draft_workspace.legal_card_buttons[0].click()
        app.processEvents()


def _assign_all_picks(workspace: PvpWorkspace) -> None:
    board = workspace.active_draft_session.board_dict()
    assets_by_id = {
        _character_id_from_asset(asset): asset
        for asset in workspace.character_assets
    }
    for seat in ("player_1", "player_2"):
        picks = board["unified_pool"]["result_zones"][seat]["picked"]
        for character_id in picks:
            asset = assets_by_id[str(character_id)]
            if not workspace.handle_build_character_clicked(seat, asset):
                raise RuntimeError(f"character assignment failed: {seat} {character_id}")


def _assign_weapons(workspace: PvpWorkspace) -> None:
    weapon_asset = workspace.weapon_assets[0]
    for seat in ("player_1", "player_2"):
        for team_index in range(2):
            for slot_index in range(4):
                workspace.handle_build_slot_clicked(seat, team_index, slot_index)
                if not workspace.handle_build_weapon_clicked(seat, weapon_asset):
                    raise RuntimeError(
                        f"weapon assignment failed: {seat} {team_index}:{slot_index}"
                    )


def _character_id_from_asset(asset: dict[str, Any]) -> str:
    return str(
        asset.get("metadata", {})
        .get("character", {})
        .get("id")
        or ""
    ).strip()


def _character_assets(count: int) -> list[dict[str, Any]]:
    return [
        _character_asset(str(20000000 + index), f"Char {index}")
        for index in range(count)
    ]


def _character_asset(character_id: str, name: str) -> dict[str, Any]:
    return {
        "path": "portrait.png",
        "filename": "portrait.png",
        "metadata": {
            "character": {
                "id": character_id,
                "name": name,
                "level": 90,
                "rarity": 5,
                "constellation": 6,
                "element": "Pyro",
                "weapon_type": 1,
                "weapon_type_name": "Sword",
                "portrait_path": "portrait.png",
            }
        },
    }


def _weapon_asset() -> dict[str, Any]:
    return {
        "path": "weapon.png",
        "filename": "weapon.png",
        "metadata": {
            "known_count": 24,
            "weapon": {
                "id": "11401",
                "name": "Sword",
                "level": 90,
                "rarity": 4,
                "refinement": 5,
                "weapon_type": 1,
                "weapon_type_name": "Sword",
                "type_name": "Sword",
                "icon_path": "weapon.png",
                "source_key": "smoke-sword",
                "weapon_fingerprint": "smoke-sword",
                "known_count": 24,
            },
        },
    }


def _seed_scoped_equipment_db(db_path: Path) -> None:
    with closing(connect_db(db_path)) as conn:
        init_db(conn)
        conn.executemany(
            """
            INSERT INTO account_characters (
                character_id,
                name,
                weapon_type,
                weapon_type_name
            )
            VALUES (?, ?, 1, 'Sword')
            """,
            [
                (20000000 + index, f"Char {index}")
                for index in range(24)
            ],
        )
        conn.execute(
            """
            INSERT INTO account_weapon_observed_stacks (
                weapon_fingerprint,
                weapon_id,
                name,
                weapon_type,
                weapon_type_name,
                rarity,
                level,
                refinement,
                icon_path,
                known_count
            )
            VALUES ('smoke-sword', 11401, 'Sword', 1, 'Sword', 4, 90, 5, 'weapon.png', 24)
            """
        )
        conn.commit()


if __name__ == "__main__":
    raise SystemExit(main())
