from __future__ import annotations

import argparse
import sys
from typing import Any, Mapping

from PySide6.QtWidgets import QApplication, QMainWindow

from hoyolab_export.team_card_data_smoke import (
    build_team_card_data_smoke_report_from_paths,
)
from run_workspace.team_builder import create_empty_team_builder_state
from run_workspace.team_card_view_model import build_team_card_view_model_from_state
from ui.team_card_prototype import TeamCardPrototypeWidget


DEFAULT_SMOKE_CHARACTER_NAME = "Тома"
DEFAULT_SMOKE_BUILD_ID = 20
DEFAULT_SMOKE_WEAPON_ID = "13407"
DEFAULT_SMOKE_WEAPON_LEVEL = 70
DEFAULT_SMOKE_WEAPON_REFINEMENT = 5
DEFAULT_SMOKE_WEAPON_PROMOTE_LEVEL = 4


def build_real_smoke_team_builder_state(
    *,
    character_name: str = DEFAULT_SMOKE_CHARACTER_NAME,
    build_id: int = DEFAULT_SMOKE_BUILD_ID,
    weapon_id: str = DEFAULT_SMOKE_WEAPON_ID,
    weapon_level: int = DEFAULT_SMOKE_WEAPON_LEVEL,
    weapon_refinement: int = DEFAULT_SMOKE_WEAPON_REFINEMENT,
    weapon_promote_level: int = DEFAULT_SMOKE_WEAPON_PROMOTE_LEVEL,
):
    report = build_team_card_data_smoke_report_from_paths(
        character_name=character_name,
        build_id=int(build_id),
        weapon_id=weapon_id,
        weapon_level=int(weapon_level),
        weapon_refinement=int(weapon_refinement),
        weapon_promote_level=int(weapon_promote_level),
    )
    state = create_empty_team_builder_state(team_count=1)
    state = state.set_character(0, 0, _selected_character(report))
    selected_weapon = report.get("selected_weapon")
    if isinstance(selected_weapon, Mapping):
        state = state.set_weapon(0, 0, selected_weapon)
    state = state.set_artifact_build(0, 0, report.get("selected_build") or {})
    state = state.attach_character_details_data(
        0,
        0,
        _details_data_from_smoke_report(report),
    )
    return state


def build_fake_team_builder_state():
    state = create_empty_team_builder_state(team_count=1)
    state = state.set_character(
        0,
        0,
        {
            "id": "10000050",
            "name": "Тома",
            "level": 70,
            "element": "Pyro",
            "rarity": 4,
            "constellation": 6,
        },
    )
    state = state.set_weapon(
        0,
        0,
        {
            "id": "13407",
            "name": "Копьё Фавония",
            "level": 70,
            "refinement": 5,
            "type_name": "Древковое",
        },
    )
    state = state.set_artifact_build(0, 0, {"build_id": 20, "build_name": "test111"})
    state = state.attach_character_details_data(
        0,
        0,
        _fake_character_details_data(),
    )
    return state


def show_team_card_prototype(state, *, title: str = "TeamCard Prototype") -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    model = build_team_card_view_model_from_state(state, title=title)
    widget = TeamCardPrototypeWidget(model)
    window = QMainWindow()
    window.setWindowTitle(title)
    window.setCentralWidget(widget)
    window.resize(980, 360)
    window.show()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Open the isolated read-only TeamCard prototype in a standalone "
            "window. This does not integrate with the main app."
        )
    )
    parser.add_argument("--fake", action="store_true", help="Use local fake data.")
    parser.add_argument("--character-name", default=DEFAULT_SMOKE_CHARACTER_NAME)
    parser.add_argument("--build-id", type=int, default=DEFAULT_SMOKE_BUILD_ID)
    parser.add_argument("--weapon-id", default=DEFAULT_SMOKE_WEAPON_ID)
    parser.add_argument("--weapon-level", type=int, default=DEFAULT_SMOKE_WEAPON_LEVEL)
    parser.add_argument(
        "--weapon-refinement",
        type=int,
        default=DEFAULT_SMOKE_WEAPON_REFINEMENT,
    )
    parser.add_argument(
        "--weapon-promote-level",
        type=int,
        default=DEFAULT_SMOKE_WEAPON_PROMOTE_LEVEL,
    )
    args = parser.parse_args(argv)

    if args.fake:
        state = build_fake_team_builder_state()
        title = "TeamCard Prototype (Fake)"
    else:
        state = build_real_smoke_team_builder_state(
            character_name=args.character_name,
            build_id=args.build_id,
            weapon_id=args.weapon_id,
            weapon_level=args.weapon_level,
            weapon_refinement=args.weapon_refinement,
            weapon_promote_level=args.weapon_promote_level,
        )
        title = "TeamCard Prototype"
    return show_team_card_prototype(state, title=title)


def _selected_character(report: Mapping[str, Any]) -> dict[str, Any]:
    selected_character = report.get("selected_character")
    if not isinstance(selected_character, Mapping):
        return {}
    return {
        "id": selected_character.get("id"),
        "name": selected_character.get("name"),
        "level": selected_character.get("level"),
        "element": selected_character.get("element"),
        "rarity": selected_character.get("rarity"),
        "constellation": selected_character.get("constellation"),
    }


def _details_data_from_smoke_report(report: Mapping[str, Any]) -> dict[str, Any]:
    full_details = report.get("character_details_full")
    if isinstance(full_details, Mapping):
        return dict(full_details)

    selected_build = report.get("selected_build")
    if not isinstance(selected_build, Mapping):
        selected_build = {}
    stat_snapshot_summary = report.get("stat_snapshot_summary")
    if not isinstance(stat_snapshot_summary, Mapping):
        stat_snapshot_summary = {}
    return {
        "status": _nested_text(report, "character_details_data", "status") or "partial",
        "account_character": report.get("selected_character"),
        "account_weapon": report.get("selected_weapon"),
        "selected_build": dict(selected_build),
        "account_stat_sheet": _nested_mapping(report, "account_stat_sheet"),
        "ascension_bonus": _nested_mapping(report, "ascension_bonus"),
        "stat_snapshot": {
            "character_base": dict(stat_snapshot_summary.get("character_base") or {}),
            "weapon": dict(stat_snapshot_summary.get("weapon") or {}),
            "artifact": {
                "summary": _artifact_summary_from_report(report),
                "warnings": _nested_list(report, "artifact_contribution", "warnings"),
            }
        },
        "warnings": _nested_list(report, "character_details_data", "warnings"),
        "gcsim_readiness": _nested_mapping(report, "character_details_data", "gcsim_readiness"),
    }


def _artifact_summary_from_report(report: Mapping[str, Any]) -> dict[str, Any]:
    artifact = _nested_mapping(report, "artifact_contribution")
    return {
        "build_id": artifact.get("build_id"),
        "build_name": artifact.get("build_name"),
        "active_set_bonuses": artifact.get("active_set_bonuses") or [],
        "stat_totals": artifact.get("stat_totals") or [],
        "crit_value": artifact.get("crit_value"),
        "proc_count": artifact.get("proc_count"),
        "missing_positions": artifact.get("missing_positions") or [],
    }


def _fake_character_details_data() -> dict[str, Any]:
    return {
        "status": "ready",
        "account_character": {
            "id": "10000050",
            "name": "Тома",
            "level": 70,
            "element": "Pyro",
            "rarity": 4,
            "constellation": 6,
        },
        "account_weapon": {
            "id": "13407",
            "name": "Копьё Фавония",
            "level": 70,
            "refinement": 5,
        },
        "selected_build": {
            "build_id": 20,
            "build_name": "test111",
        },
        "stat_snapshot": {
            "artifact": {
                "summary": {
                    "build_id": 20,
                    "build_name": "test111",
                    "active_set_bonuses": [
                        {
                            "owned_count": 2,
                            "piece_count": 2,
                            "set_name": "Серенада шёлковой луны",
                            "set_uid": "SilkenMoonsSerenade",
                        },
                        {
                            "owned_count": 2,
                            "piece_count": 2,
                            "set_name": "Эмблема рассечённой судьбы",
                            "set_uid": "EmblemOfSeveredFate",
                        },
                    ],
                    "crit_value": 95.6,
                    "proc_count": 12,
                    "missing_positions": [5],
                },
                "warnings": [
                    "artifact_build_incomplete",
                    "set_bonus_formulas_not_included",
                ],
            }
        },
        "warnings": [
            "final_totals_not_computed",
            "artifact_build_incomplete",
            "set_bonus_formulas_not_included",
        ],
    }


def _nested_mapping(data: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    value: Any = data
    for key in keys:
        if not isinstance(value, Mapping):
            return {}
        value = value.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _nested_text(data: Mapping[str, Any], *keys: str) -> str:
    value: Any = data
    for key in keys:
        if not isinstance(value, Mapping):
            return ""
        value = value.get(key)
    return str(value or "").strip()


def _nested_list(data: Mapping[str, Any], *keys: str) -> list[Any]:
    value: Any = data
    for key in keys:
        if not isinstance(value, Mapping):
            return []
        value = value.get(key)
    return list(value) if isinstance(value, list) else []


if __name__ == "__main__":
    raise SystemExit(main())
