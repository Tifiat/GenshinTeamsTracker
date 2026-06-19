from __future__ import annotations

import argparse
import os
from collections import defaultdict, deque
from contextlib import closing
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()

from PySide6.QtWidgets import QApplication

from hoyolab_export.artifact_db import connect_db, init_db
from ui.pvp_browser.build_flow import _asset_weapon_keys
from ui.pvp_browser.timers import PvpTimersResultWidget
from ui.pvp_browser.window import PvpWorkspace
from ui.right_panel.pvp._shared import PVP_DRAFT_STAGE_COMPLETED_RESULT
from ui.right_panel.pvp.play.panel import PvpPlayRightPanel

# This smoke drives the left/main PvP workspace while instantiating the moved
# right-panel play page from ui.right_panel.pvp.


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the offscreen PvP UI full-flow smoke.",
    )
    parser.add_argument(
        "--account",
        action="store_true",
        help=(
            "Use local PvP deck presets/account assets instead of temp synthetic "
            "fixtures. Reads local data but writes no session/history files."
        ),
    )
    parser.add_argument(
        "--player-1-deck",
        default="",
        help="Optional Player 1 deck preset id for --account mode.",
    )
    parser.add_argument(
        "--player-2-deck",
        default="",
        help="Optional Player 2 deck preset id for --account mode.",
    )
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication([])
    if args.account:
        return _run_account_smoke(
            app,
            player_1_deck_id=args.player_1_deck,
            player_2_deck_id=args.player_2_deck,
        )
    return _run_synthetic_smoke(app)


def _run_synthetic_smoke(app: QApplication) -> int:
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
        if not _enter_timers_and_finalize(workspace, app):
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


def _run_account_smoke(
    app: QApplication,
    *,
    player_1_deck_id: str = "",
    player_2_deck_id: str = "",
) -> int:
    workspace = PvpWorkspace()
    deck_1 = player_1_deck_id or workspace.default_player_1_deck_id()
    deck_2 = player_2_deck_id or workspace.default_player_2_deck_id()
    if not deck_1 or not deck_2:
        print("failed: no local PvP deck presets available")
        return 1
    if not workspace.start_local_draft(deck_1, deck_2):
        print(f"failed: start local draft: {workspace.last_play_status()}")
        return 1

    _complete_draft(workspace, app)
    if not workspace.continue_to_assignment():
        print(f"failed: continue to assignment: {workspace.last_draft_status()}")
        return 1
    if workspace.build_flow_context is None:
        print("failed: scoped build context missing")
        return 1
    _assign_all_picks(workspace)
    try:
        _assign_compatible_weapons(workspace)
    except RuntimeError as exc:
        print(f"failed: {exc}")
        return 1
    for seat in ("player_1", "player_2"):
        if not workspace.ready_build_seat(seat):
            print(f"failed: ready {seat}: {workspace.last_draft_status()}")
            return 1
    if not workspace.weapons_ready():
        print("failed: scoped ready validation")
        return 1
    if not _enter_timers_and_finalize(workspace, app):
        print(f"failed: finalize result: {workspace.last_draft_status()}")
        return 1

    result = workspace.active_draft_session.controller.state.match_result
    if result is None or workspace.draft_stage != PVP_DRAFT_STAGE_COMPLETED_RESULT:
        print("failed: result missing")
        return 1
    print(
        "PvP UI account full-flow smoke: "
        f"status={result.status}, winner={result.winner_seat}, "
        f"diff={result.seconds_difference}s, decks={deck_1}/{deck_2}"
    )
    return 0


def _enter_timers_and_finalize(workspace: PvpWorkspace, app: QApplication) -> bool:
    timer_widget = workspace.draft_workspace.findChild(PvpTimersResultWidget)
    if timer_widget is None:
        return False
    for index in range(3):
        if not timer_widget.set_timer_seconds_for_test("player_1", index, 540):
            return False
    for index, seconds in enumerate((530, 540, 540)):
        if not timer_widget.set_timer_seconds_for_test("player_2", index, seconds):
            return False
    if not timer_widget.finalize_button.isEnabled():
        return False
    timer_widget.finalize_button.click()
    app.processEvents()
    return workspace.draft_stage == PVP_DRAFT_STAGE_COMPLETED_RESULT


def _complete_draft(workspace: PvpWorkspace, app: QApplication) -> None:
    guard = 0
    while not workspace.active_draft_session.board_dict()["status"]["draft_finished"]:
        guard += 1
        if guard >= 40:
            raise RuntimeError("draft did not complete")
        if not workspace.draft_workspace.click_legal_character_for_test():
            raise RuntimeError("draft has no clickable legal portrait")
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


def _assign_compatible_weapons(workspace: PvpWorkspace) -> None:
    session = workspace.active_draft_session
    context = workspace.build_flow_context
    if session is None or context is None:
        raise RuntimeError("active draft/build context missing")
    assets_by_stack_key: dict[str, dict[str, Any]] = {}
    for asset in workspace.weapon_assets:
        for stack_key in _asset_weapon_keys(asset):
            assets_by_stack_key.setdefault(stack_key, asset)

    for seat in ("player_1", "player_2"):
        seat_context = context.seat(seat)
        if seat_context is None:
            raise RuntimeError(f"missing seat context: {seat}")
        deck = session.controller.session_state.deck_for(seat)
        character_by_id = deck.character_by_id
        stacks_by_type: dict[str, deque[Any]] = defaultdict(deque)
        for stack in deck.weapons:
            canonical_type = _canonical_weapon_type(stack.weapon_type)
            if not canonical_type:
                continue
            for _index in range(max(1, stack.count or 1)):
                stacks_by_type[canonical_type].append(stack)

        for team_index, team in enumerate(seat_context.controller.state.teams[:2]):
            for slot_index, slot in enumerate(team.slots[:4]):
                if slot.character is None:
                    raise RuntimeError(f"empty character slot: {seat} {team_index}:{slot_index}")
                character_id = str(slot.character.id)
                character = character_by_id.get(character_id)
                if character is None:
                    raise RuntimeError(f"character not in draft deck: {seat} {character_id}")
                canonical_type = _canonical_weapon_type(character.weapon_type)
                if not stacks_by_type[canonical_type]:
                    raise RuntimeError(
                        f"no compatible weapon stack: {seat} {character_id} {character.weapon_type}"
                    )
                stack = stacks_by_type[canonical_type].popleft()
                asset = assets_by_stack_key.get(stack.stack_key)
                if asset is None:
                    raise RuntimeError(f"weapon asset missing for stack: {seat} {stack.stack_key}")
                workspace.handle_build_slot_clicked(seat, team_index, slot_index)
                if not workspace.handle_build_weapon_clicked(seat, asset):
                    raise RuntimeError(
                        "weapon assignment failed: "
                        f"{seat} {team_index}:{slot_index} {stack.stack_key}"
                    )


def _character_id_from_asset(asset: dict[str, Any]) -> str:
    return str(
        asset.get("metadata", {})
        .get("character", {})
        .get("id")
        or ""
    ).strip()


_WEAPON_TYPE_BY_ID = {
    "1": "sword",
    "10": "catalyst",
    "11": "claymore",
    "12": "bow",
    "13": "polearm",
}
_WEAPON_TYPE_ALIASES = {
    "sword": "sword",
    "one_handed_sword": "sword",
    "одноручный_меч": "sword",
    "одноручное": "sword",
    "одноручное_оружие": "sword",
    "claymore": "claymore",
    "двуручный_меч": "claymore",
    "двуручное": "claymore",
    "двуручное_оружие": "claymore",
    "bow": "bow",
    "лук": "bow",
    "стрелковое": "bow",
    "стрелковое_оружие": "bow",
    "catalyst": "catalyst",
    "катализатор": "catalyst",
    "polearm": "polearm",
    "древковое": "polearm",
    "древковое_оружие": "polearm",
    "копье": "polearm",
    "копьё": "polearm",
}


def _canonical_weapon_type(value: object) -> str:
    raw = str(value or "").strip()
    if raw in _WEAPON_TYPE_BY_ID:
        return _WEAPON_TYPE_BY_ID[raw]
    token = raw.casefold().replace("-", "_").replace(" ", "_")
    while "__" in token:
        token = token.replace("__", "_")
    return _WEAPON_TYPE_ALIASES.get(token, "")


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
