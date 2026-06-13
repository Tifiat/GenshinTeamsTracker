from __future__ import annotations

import os
import tempfile
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()

from PySide6.QtWidgets import QApplication

from ui.pvp_browser.window import (
    PVP_DRAFT_STAGE_COMPLETED_RESULT,
    PvpPlayRightPanel,
    PvpWorkspace,
)


def main() -> int:
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = PvpWorkspace(
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
        _assign_all_picks(workspace)
        if not workspace.assignment_ready() or not workspace.continue_to_weapons():
            print("failed: assignment validation")
            return 1
        _assign_weapons(workspace)
        if not workspace.weapons_ready() or not workspace.continue_to_timers():
            print("failed: weapon validation")
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
    for seat in ("player_1", "player_2"):
        picks = board["unified_pool"]["result_zones"][seat]["picked"]
        for index, character_id in enumerate(picks):
            workspace.select_assignment_character(seat, character_id)
            workspace.assign_selected_character_to_slot(seat, index // 4, index % 4)


def _assign_weapons(workspace: PvpWorkspace) -> None:
    session = workspace.active_draft_session
    for seat in ("player_1", "player_2"):
        deck = session.controller.session_state.deck_for(seat)
        stack = deck.weapons[0]
        for team in workspace.assignment_slots_by_seat[seat]:
            for character_id in team:
                if character_id:
                    workspace.assign_weapon_stack(seat, character_id, stack.stack_key)


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


if __name__ == "__main__":
    raise SystemExit(main())
