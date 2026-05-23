from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from PySide6.QtWidgets import QApplication, QMainWindow

from hoyolab_export.account_storage import (
    AccountCharacterRuntimeRecord,
    AccountWeaponObservedStack,
    list_account_characters,
    list_account_weapon_observed_stacks,
)
from hoyolab_export.artifact_db import ARTIFACT_DB_PATH, connect_db
from hoyolab_export.display_stat_effects import get_weapon_passive_tooltip
from hoyolab_export.paths import PROJECT_ROOT
from run_workspace.right_panel_prototype_view_model import (
    MODE_ABYSS,
    MODE_DPS_DUMMY,
    build_fake_right_panel_prototype_state,
    build_right_panel_prototype_view_model,
)
from run_workspace.team_builder import TeamBuilderState, create_empty_team
from ui.right_panel_prototype import RIGHT_PANEL_PROTOTYPE_MIN_WIDTH, RightPanelPrototypeWidget


ARTIFACT_SET_ICON_DIR = PROJECT_ROOT / "assets" / "artifact_sets"
REAL_NO_PRESET_CHARACTER_LIMIT = 4
TRAVELER_CHARACTER_IDS = {"10000005", "10000007"}
LINNEA_CHARACTER_ID = "10000130"
LINNEA_SIGNATURE_WEAPON_ID = "15516"
YELAN_CHARACTER_ID = "10000060"
YELAN_SIGNATURE_WEAPON_ID = "15508"


def show_right_panel_prototype(
    state: TeamBuilderState,
    *,
    title: str = "Right Panel / TeamBuilder Prototype v6",
) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    current_mode = MODE_ABYSS
    selected_team_index = 0
    selected_slot_index = 0
    external_bonuses_enabled = True

    def make_model():
        return build_right_panel_prototype_view_model(
            state,
            mode=current_mode,
            selected_team_index=selected_team_index,
            selected_slot_index=selected_slot_index,
            external_bonuses_enabled=external_bonuses_enabled,
        )

    widget = RightPanelPrototypeWidget(make_model())
    window = QMainWindow()
    window.setWindowTitle(title)
    window.setCentralWidget(widget)
    window.setMinimumSize(RIGHT_PANEL_PROTOTYPE_MIN_WIDTH, 640)
    window.resize(RIGHT_PANEL_PROTOTYPE_MIN_WIDTH, 940)

    def on_mode_requested(mode: str) -> None:
        nonlocal current_mode, selected_team_index, selected_slot_index
        current_mode = MODE_DPS_DUMMY if mode == MODE_DPS_DUMMY else MODE_ABYSS
        selected_team_index = 0
        selected_slot_index = 0
        widget.set_model(make_model())

    def on_slot_selected(team_index: int, slot_index: int) -> None:
        nonlocal selected_team_index, selected_slot_index
        selected_team_index = int(team_index)
        selected_slot_index = int(slot_index)
        widget.set_model(make_model())

    def on_external_bonuses_toggled(enabled: bool) -> None:
        nonlocal external_bonuses_enabled
        external_bonuses_enabled = bool(enabled)
        widget.set_model(make_model())

    widget.mode_requested.connect(on_mode_requested)
    widget.slot_selected.connect(on_slot_selected)
    widget.external_bonuses_toggled.connect(on_external_bonuses_toggled)
    window.show()
    return app.exec()


def build_real_thoma_state() -> TeamBuilderState:
    from ui.team_card_prototype_smoke import build_real_smoke_team_builder_state

    real_state = build_real_smoke_team_builder_state()
    state = TeamBuilderState(teams=(real_state.team(0), create_empty_team()))
    state = _attach_no_preset_account_characters(
        state,
        limit=REAL_NO_PRESET_CHARACTER_LIMIT,
    )
    state = _attach_specific_account_character_weapon(
        state,
        team_index=0,
        slot_index=1,
        character_id=LINNEA_CHARACTER_ID,
        weapon_id=LINNEA_SIGNATURE_WEAPON_ID,
    )
    state = _attach_specific_account_character_weapon(
        state,
        team_index=0,
        slot_index=2,
        character_id=YELAN_CHARACTER_ID,
        weapon_id=YELAN_SIGNATURE_WEAPON_ID,
    )
    return _attach_prototype_visual_assets(state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Open the isolated future right panel / TeamBuilder visual prototype. "
            "This does not modify or replace the main app right panel."
        )
    )
    parser.add_argument(
        "--real-thoma",
        action="store_true",
        help=(
            "Use the existing no-network Thoma + build id 20 smoke data for "
            "one selected slot plus several local no-preset account characters. "
            "Fake data is used by default."
        ),
    )
    args = parser.parse_args(argv)

    state = build_real_thoma_state() if args.real_thoma else build_fake_right_panel_prototype_state()
    title = (
        "Right Panel / TeamBuilder Prototype v6 (Real Thoma + local no-preset slots)"
        if args.real_thoma
        else "Right Panel / TeamBuilder Prototype v6 (Fake Data)"
    )
    return show_right_panel_prototype(state, title=title)


def _attach_no_preset_account_characters(
    state: TeamBuilderState,
    *,
    limit: int,
) -> TeamBuilderState:
    characters, weapon_stacks = _load_sqlite_account_runtime_records()
    if not characters:
        return state

    used_character_ids = {
        str(slot.character.id)
        for team in state.teams
        for slot in team.slots
        if slot.character is not None and slot.character.id
    }
    target_slots = (
        (0, 1),
        (0, 2),
        (0, 3),
        (1, 0),
        (1, 1),
    )

    result = state
    added = 0
    for record in characters:
        if added >= int(limit):
            break
        character_id = _text(record.character_id)
        if (
            not character_id
            or character_id in used_character_ids
            or character_id in TRAVELER_CHARACTER_IDS
        ):
            continue
        if added >= len(target_slots):
            break

        team_index, slot_index = target_slots[added]
        character = record.to_team_builder_character_ref()
        weapon_stack = _weapon_stack_for_character_record(
            weapon_stacks,
            record=record,
        )
        weapon = weapon_stack.to_team_builder_weapon_ref() if weapon_stack else {}
        details = _details_from_account_record(
            record,
            weapon_stack,
            source_note="prototype_weapon_option_by_type_not_equipped",
        )
        result = result.set_character(team_index, slot_index, character)
        if weapon:
            result = result.set_weapon(team_index, slot_index, weapon)
        result = result.attach_character_details_data(team_index, slot_index, details)
        used_character_ids.add(character_id)
        added += 1
    return result


def _attach_specific_account_character_weapon(
    state: TeamBuilderState,
    *,
    team_index: int,
    slot_index: int,
    character_id: str,
    weapon_id: str,
) -> TeamBuilderState:
    characters, weapon_stacks = _load_sqlite_account_runtime_records()
    character = next(
        (record for record in characters if _text(record.character_id) == _text(character_id)),
        None,
    )
    weapon_stack = next(
        (stack for stack in weapon_stacks if _text(stack.weapon_id) == _text(weapon_id)),
        None,
    )
    if character is None:
        return state

    result = state.set_character(
        team_index,
        slot_index,
        character.to_team_builder_character_ref(),
    )
    if weapon_stack is not None:
        result = result.set_weapon(
            team_index,
            slot_index,
            weapon_stack.to_team_builder_weapon_ref(),
        )
    details = _details_from_account_record(
        character,
        weapon_stack,
        source_note="prototype_explicit_weapon_option",
    )
    return result.attach_character_details_data(team_index, slot_index, details)


def _attach_prototype_visual_assets(state: TeamBuilderState) -> TeamBuilderState:
    result = state
    for team_index, team in enumerate(state.teams):
        for slot in team.slots:
            if slot.character is None:
                continue
            details = dict(slot.character_details_data or {})
            account_character = _mapping(details.get("account_character"))
            account_weapon = _mapping(details.get("account_weapon"))
            build_mini_sets = _build_mini_sets_from_details(details)
            portrait_path = _existing_project_path(account_character.get("portrait_path"))
            weapon_path = _existing_project_path(account_weapon.get("icon_path"))
            if (
                portrait_path is None
                and weapon_path is None
                and not build_mini_sets
            ):
                continue
            if portrait_path is not None:
                details["portrait_path"] = str(portrait_path)
            if weapon_path is not None:
                details["weapon_image_path"] = str(weapon_path)
            if build_mini_sets:
                details["build_mini_sets"] = build_mini_sets
            result = result.attach_character_details_data(
                team_index,
                slot.slot_index,
                details,
            )
    return result


def _load_sqlite_account_runtime_records() -> tuple[
    tuple[AccountCharacterRuntimeRecord, ...],
    tuple[AccountWeaponObservedStack, ...],
]:
    with connect_db(ARTIFACT_DB_PATH) as conn:
        return (
            list_account_characters(conn),
            list_account_weapon_observed_stacks(conn),
        )


def _weapon_stack_for_character_record(
    weapon_stacks: tuple[AccountWeaponObservedStack, ...],
    *,
    record: AccountCharacterRuntimeRecord,
) -> AccountWeaponObservedStack | None:
    weapon_type = _optional_int(record.weapon_type)
    if weapon_type is None:
        return None
    candidates = [
        stack
        for stack in weapon_stacks
        if _optional_int(stack.weapon_type) == weapon_type
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda stack: (
            -(stack.rarity or 0),
            -(stack.level or 0),
            -(stack.refinement or 0),
            -(stack.promote_level or 0),
            stack.name.casefold(),
            stack.weapon_fingerprint,
        ),
    )[0]


def _details_from_account_record(
    record: AccountCharacterRuntimeRecord,
    weapon_stack: AccountWeaponObservedStack | None,
    *,
    source_note: str,
) -> dict[str, Any]:
    passive_reference = _weapon_passive_tooltip_for_stack(weapon_stack)
    return {
        "status": "partial",
        "account_character": record.to_team_builder_character_ref(),
        "account_weapon": (
            weapon_stack.to_team_builder_weapon_ref()
            if weapon_stack is not None
            else None
        ),
        "weapon_passive_reference": passive_reference,
        "selected_build": {},
        "source_notes": [
            "prototype_no_selected_artifact_preset",
            "account_sqlite_runtime",
            source_note,
        ],
        "warnings": [
            *record.warnings,
            *(weapon_stack.warnings if weapon_stack is not None else ()),
        ],
    }


def _weapon_passive_tooltip_for_stack(
    weapon_stack: AccountWeaponObservedStack | None,
) -> dict[str, Any]:
    if weapon_stack is None:
        return {}
    language = _account_content_language()
    try:
        with connect_db(ARTIFACT_DB_PATH) as conn:
            return get_weapon_passive_tooltip(
                conn,
                weapon_id=weapon_stack.weapon_id,
                language=language,
            )
    except Exception:
        return {}


def _account_content_language() -> str:
    path = PROJECT_ROOT / "data" / "hoyolab" / "account_language.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return _text(data.get("contentLanguage")) if isinstance(data, Mapping) else ""


def _build_mini_sets_from_details(details: Mapping[str, Any]) -> list[dict[str, Any]]:
    summary = _mapping(
        _mapping(_mapping(details.get("stat_snapshot")).get("artifact")).get("summary")
    )
    rows = summary.get("active_set_bonuses")
    if not isinstance(rows, list):
        return []

    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        piece_count = _optional_int(row.get("piece_count") or row.get("count")) or 0
        set_uid = _text(row.get("set_uid"))
        set_name = _text(row.get("set_name")) or set_uid
        if piece_count <= 0 or not (set_uid or set_name):
            continue
        icon_path = _artifact_set_icon_path(set_uid)
        result.append(
            {
                "set_uid": set_uid,
                "set_name": set_name,
                "piece_count": piece_count,
                "owned_count": _optional_int(row.get("owned_count")) or piece_count,
                "icon_path": str(icon_path) if icon_path is not None else "",
            }
        )
    return result


def _artifact_set_icon_path(set_uid: str) -> Path | None:
    if not set_uid:
        return None
    path = ARTIFACT_SET_ICON_DIR / f"{set_uid}_1.png"
    return path if path.exists() else None


def _existing_project_path(value: Any) -> Path | None:
    text = _text(value)
    if not text:
        return None
    path = Path(text)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path if path.exists() else None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


if __name__ == "__main__":
    raise SystemExit(main())
