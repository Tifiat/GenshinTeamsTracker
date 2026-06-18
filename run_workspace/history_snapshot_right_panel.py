from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from localization import tr
from run_workspace.history_snapshot import (
    HISTORY_RUN_TYPE_ABYSS,
    HistoryAbyssSideResultSnapshot,
    HistoryResultSummarySnapshot,
    HistorySnapshotBundle,
    HistoryTeamSlotSnapshot,
)
from run_workspace.right_panel_prototype_view_model import (
    CHAMBER_TABLE_HEADERS,
    MODE_ABYSS,
    MODE_DPS_DUMMY,
    MODE_TABS,
    FactDpsEnemyTooltipViewModel,
    FactDpsTooltipViewModel,
    GcsimTooltipViewModel,
    RightPanelBonusSourceDisplayItem,
    RightPanelBuildMiniSetViewModel,
    RightPanelChamberRowViewModel,
    RightPanelDetailRowViewModel,
    RightPanelGcsimStatusViewModel,
    RightPanelPrototypeViewModel,
    RightPanelSelectedDetailsViewModel,
    RightPanelSlotPrototypeViewModel,
    RightPanelTeamPrototypeViewModel,
)
from run_workspace.team_card_view_model import TeamCardArtifactSummaryViewModel


def first_occupied_history_slot(
    bundle: HistorySnapshotBundle,
) -> tuple[int, int] | None:
    for team in _visible_teams(bundle):
        for slot in team.slots:
            if slot.character is not None:
                return int(team.team_index), int(slot.slot_index)
    return None


def build_history_snapshot_right_panel_view_model(
    bundle: HistorySnapshotBundle,
    *,
    bundle_dir: str | Path,
    selected_team_index: int | None = None,
    selected_slot_index: int | None = None,
) -> RightPanelPrototypeViewModel:
    selected = _valid_selection(
        bundle,
        selected_team_index=selected_team_index,
        selected_slot_index=selected_slot_index,
    )
    base_dir = Path(bundle_dir)
    visible_teams = _visible_teams(bundle)
    teams = tuple(
        RightPanelTeamPrototypeViewModel(
            team_index=int(team.team_index),
            slots=tuple(
                _slot_view_model(
                    slot,
                    team_index=int(team.team_index),
                    selected=selected,
                    bundle_dir=base_dir,
                )
                for slot in team.slots
            ),
        )
        for team in visible_teams
    )
    selected_slot = _snapshot_slot(bundle, selected)
    chamber_rows = _chamber_rows(bundle, bundle_dir=base_dir)
    mode = MODE_ABYSS if bundle.run_type == HISTORY_RUN_TYPE_ABYSS else MODE_DPS_DUMMY
    return RightPanelPrototypeViewModel(
        mode=mode,
        mode_tabs=MODE_TABS,
        teams=teams,
        selected_details=_selected_details(
            selected_slot,
            selected=selected,
            bundle_dir=base_dir,
            external_bonuses_enabled=bundle.external_bonuses_enabled,
        ),
        chamber_headers=CHAMBER_TABLE_HEADERS,
        chamber_rows=chamber_rows,
        total_seconds=sum(row.total_seconds for row in chamber_rows),
        gcsim_status=RightPanelGcsimStatusViewModel(
            status=_gcsim_status(bundle),
        ),
        external_bonuses_enabled=bundle.external_bonuses_enabled,
    )


def _valid_selection(
    bundle: HistorySnapshotBundle,
    *,
    selected_team_index: int | None,
    selected_slot_index: int | None,
) -> tuple[int, int] | None:
    requested = None
    if selected_team_index is not None and selected_slot_index is not None:
        requested = int(selected_team_index), int(selected_slot_index)
    if _snapshot_slot(bundle, requested) is not None:
        return requested
    return first_occupied_history_slot(bundle)


def _snapshot_slot(
    bundle: HistorySnapshotBundle,
    selected: tuple[int, int] | None,
) -> HistoryTeamSlotSnapshot | None:
    if selected is None:
        return None
    team_index, slot_index = selected
    for team in _visible_teams(bundle):
        if int(team.team_index) != team_index:
            continue
        for slot in team.slots:
            if int(slot.slot_index) == slot_index and slot.character is not None:
                return slot
    return None


def _slot_view_model(
    slot: HistoryTeamSlotSnapshot,
    *,
    team_index: int,
    selected: tuple[int, int] | None,
    bundle_dir: Path,
) -> RightPanelSlotPrototypeViewModel:
    character = slot.character
    weapon = slot.weapon
    build = slot.artifact_build
    active_sets = () if build is None else build.active_set_bonuses
    warnings = _dedupe(
        (*slot.warnings, *((build.warnings if build is not None else ())))
    )
    artifact_icon = ""
    if build is not None:
        artifact_icon = next(
            (item.icon_ref for item in build.artifact_slots if item.icon_ref),
            "",
        )
    return RightPanelSlotPrototypeViewModel(
        team_index=team_index,
        slot_index=int(slot.slot_index),
        is_empty=character is None,
        is_selected=selected == (team_index, int(slot.slot_index)),
        character_title="" if character is None else character.name,
        character_meta="" if character is None else _character_meta(character),
        portrait_label="" if character is None else _square_label(character.name, "CHAR"),
        portrait_path=(
            "" if character is None else _asset_path(bundle_dir, character.portrait_ref)
        ),
        weapon_label="" if weapon is None else weapon.name,
        weapon_square_label=(
            "WPN" if weapon is None else _square_label(weapon.name, "WPN")
        ),
        weapon_image_path=(
            "" if weapon is None else _asset_path(bundle_dir, weapon.icon_ref)
        ),
        weapon_tooltip="" if weapon is None else weapon.passive_tooltip,
        build_label="" if build is None else build.build_name,
        artifact_square_label=_artifact_badge(build),
        artifact_image_path=_asset_path(bundle_dir, artifact_icon),
        build_mini_sets=tuple(
            RightPanelBuildMiniSetViewModel(
                set_uid=item.set_uid,
                set_name=item.set_name,
                piece_count=int(item.piece_count),
                owned_count=int(item.piece_count),
                icon_path=_asset_path(bundle_dir, item.icon_ref),
            )
            for item in active_sets
        ),
        stat_badge=_artifact_stat_badge(build),
        warning_count=len(warnings),
        warning_tooltip="\n".join(warnings),
        artifact_summary=(
            None
            if build is None
            else TeamCardArtifactSummaryViewModel(
                active_sets=tuple(_set_label(item) for item in active_sets),
                crit_value=build.crit_value,
                proc_count=build.proc_count,
                missing_positions=build.missing_positions,
                warnings=build.warnings,
            )
        ),
    )


def _selected_details(
    slot: HistoryTeamSlotSnapshot | None,
    *,
    selected: tuple[int, int] | None,
    bundle_dir: Path,
    external_bonuses_enabled: bool,
) -> RightPanelSelectedDetailsViewModel:
    if slot is None or slot.character is None or selected is None:
        return RightPanelSelectedDetailsViewModel(has_selection=False)
    character = slot.character
    weapon = slot.weapon
    build = slot.artifact_build
    weapon_rows = () if weapon is None else weapon.stat_rows
    base_atk = next((row.value for row in weapon_rows if row.key == "base_atk"), "")
    secondary = next(
        (row for row in weapon_rows if row.key == "secondary_stat"),
        None,
    )
    return RightPanelSelectedDetailsViewModel(
        has_selection=True,
        team_index=selected[0],
        slot_index=selected[1],
        character_name=character.name,
        character_level=character.level,
        constellation=character.constellation,
        element=character.element,
        weapon_name="" if weapon is None else weapon.name,
        weapon_level=None if weapon is None else weapon.level,
        weapon_refinement=None if weapon is None else weapon.refinement,
        weapon_base_atk=base_atk,
        weapon_secondary_label="" if secondary is None else secondary.label,
        weapon_secondary_value="" if secondary is None else secondary.value,
        weapon_icon_path=(
            "" if weapon is None else _asset_path(bundle_dir, weapon.icon_ref)
        ),
        crit_value=None if build is None else build.crit_value,
        active_sets=(
            ()
            if build is None
            else tuple(_set_label(item) for item in build.active_set_bonuses)
        ),
        stat_rows=tuple(
            RightPanelDetailRowViewModel(
                label=row.label,
                value=row.value,
                icon_label=row.icon_label,
            )
            for row in slot.stat_rows
        ),
        bonus_sources=tuple(
            RightPanelBonusSourceDisplayItem(
                source_kind=item.source_kind,
                source_id=item.source_id,
                label=item.label,
                icon_path=_asset_path(bundle_dir, item.icon_ref),
                short_effects=item.short_effects or item.effects,
                tooltip_effects=item.tooltip_effects or item.effects,
                tooltip_title=item.tooltip_title,
                tooltip_body=item.tooltip_body,
                applied=item.applied,
                not_applied_reason=item.not_applied_reason,
                character_icons=tuple(
                    _asset_path(bundle_dir, path) for path in item.character_icon_refs
                ),
                character_tooltips=item.character_tooltips,
            )
            for item in slot.bonus_sources
        ),
        external_bonuses_enabled=external_bonuses_enabled,
        weapon_tooltip="" if weapon is None else weapon.passive_tooltip,
    )


def _chamber_rows(
    bundle: HistorySnapshotBundle,
    *,
    bundle_dir: Path,
) -> tuple[RightPanelChamberRowViewModel, ...]:
    scenario = bundle.scenario
    if scenario is not None and scenario.abyss is not None:
        rows = []
        for chamber in scenario.abyss.chambers:
            timer = chamber.timer
            t1_left = 0 if timer is None else int(timer.team1_left_seconds)
            t2_left = 0 if timer is None else int(timer.team2_left_seconds)
            t1_elapsed = _side_elapsed(chamber.side_results, 1, timer, "team1")
            t2_elapsed = _side_elapsed(chamber.side_results, 2, timer, "team2")
            factual1 = _result(bundle, "factual_dps", chamber.chamber_index, 1)
            factual2 = _result(bundle, "factual_dps", chamber.chamber_index, 2)
            sim1 = _result(bundle, "sim_dps", chamber.chamber_index, 1)
            sim2 = _result(bundle, "sim_dps", chamber.chamber_index, 2)
            side1 = _side_result(chamber.side_results, 1)
            side2 = _side_result(chamber.side_results, 2)
            rows.append(
                RightPanelChamberRowViewModel(
                    chamber_label=chamber.chamber_label or f"C{chamber.chamber_index}",
                    team1_time=_remaining_time(t1_left),
                    team1_seconds=t1_elapsed,
                    team2_time=_remaining_time(t2_left),
                    team2_seconds=t2_elapsed,
                    factual_team1=_format_factual_dps(_dps(factual1, side1)),
                    factual_team2=_format_factual_dps(_dps(factual2, side2)),
                    sim_team1=_format_sim_result(sim1),
                    sim_team2=_format_sim_result(sim2),
                    total_seconds=(
                        t1_elapsed + t2_elapsed
                        if timer is None or timer.total_elapsed_seconds is None
                        else int(timer.total_elapsed_seconds)
                    ),
                    timer_editable=True,
                    factual_team1_tooltip=_fact_tooltip(
                        factual1, side1, chamber.enemies, side=1, bundle_dir=bundle_dir
                    ),
                    factual_team2_tooltip=_fact_tooltip(
                        factual2, side2, chamber.enemies, side=2, bundle_dir=bundle_dir
                    ),
                    sim_team1_tooltip=_sim_tooltip(sim1),
                    sim_team2_tooltip=_sim_tooltip(sim2),
                )
            )
        return tuple(rows)

    dummy = None if scenario is None else scenario.dps_dummy
    factual = _first_result(bundle, "factual_dps")
    sim = _first_result(bundle, "sim_dps")
    duration = (
        0
        if dummy is None or dummy.duration_seconds is None
        else int(dummy.duration_seconds)
    )
    factual_dps = None if dummy is None else dummy.factual_dps
    if factual_dps is None and factual is not None:
        factual_dps = factual.dps
    return (
        RightPanelChamberRowViewModel(
            chamber_label="Dummy",
            team1_time=_remaining_time(duration),
            team1_seconds=duration,
            team2_time="-",
            team2_seconds=0,
            factual_team1=_format_factual_dps(factual_dps),
            factual_team2="-",
            sim_team1=_format_sim_result(sim),
            sim_team2="-",
            total_seconds=duration,
            factual_team1_tooltip=_dummy_fact_tooltip(dummy, factual),
            sim_team1_tooltip=_sim_tooltip(sim),
        ),
    )


def _fact_tooltip(
    summary: HistoryResultSummarySnapshot | None,
    side_result: HistoryAbyssSideResultSnapshot | None,
    enemies: tuple[Mapping[str, Any], ...],
    *,
    side: int,
    bundle_dir: Path,
) -> FactDpsTooltipViewModel | None:
    if summary is None and side_result is None:
        return None
    payload = {} if summary is None else summary.payload
    elapsed = int(
        (summary.elapsed_seconds if summary is not None else None)
        or (side_result.elapsed_seconds if side_result is not None else 0)
        or 0
    )
    dps = _dps(summary, side_result)
    total_hp = _optional_int(payload.get("total_hp"))
    if total_hp is None and side_result is not None:
        total_hp = side_result.total_hp
    return FactDpsTooltipViewModel(
        title=(summary.label if summary is not None else "Fact DPS") or "Fact DPS",
        formula=str(payload.get("formula") or "HP / elapsed time"),
        total_hp=total_hp,
        total_solo_hp=_optional_int(payload.get("total_solo_hp")),
        total_multi_target_hp=_optional_int(payload.get("total_multi_target_hp")),
        hp_mode=str(payload.get("hp_mode") or (side_result.target_mode if side_result else "")),
        hp_mode_label=str(payload.get("hp_mode_label") or ""),
        elapsed_seconds=elapsed,
        calculated_dps=None if dps is None else int(dps),
        hp_source_label=str(
            payload.get("hp_source_label")
            or (side_result.hp_source if side_result else "")
        ),
        unavailable_reason=str(payload.get("unavailable_reason") or ""),
        warnings=() if summary is None else summary.warnings,
        enemies=tuple(
            _enemy_tooltip(item, bundle_dir=bundle_dir)
            for item in enemies
            if _optional_int(item.get("side")) == side
        ),
    )


def _enemy_tooltip(
    item: Mapping[str, Any],
    *,
    bundle_dir: Path,
) -> FactDpsEnemyTooltipViewModel:
    return FactDpsEnemyTooltipViewModel(
        wave=_optional_int(item.get("wave")) or 0,
        primary_display_name=str(item.get("primary_display_name") or ""),
        enemy_count=_optional_int(item.get("enemy_count")) or 1,
        display_level=_optional_int(item.get("display_level")),
        matched_nanoka_display_name=_optional_text(item.get("matched_nanoka_display_name")),
        hp_used=_optional_int(item.get("hp_used")),
        hp_source=str(item.get("hp_source") or ""),
        match_method=str(item.get("match_method") or ""),
        match_confidence=str(item.get("match_confidence") or ""),
        cached_icon_path=(
            _asset_path(bundle_dir, str(item.get("cached_icon_path") or "")) or None
        ),
        selected_for_solo=bool(item.get("selected_for_solo")),
        warnings=tuple(str(value) for value in item.get("warnings") or ()),
    )


def _sim_tooltip(
    summary: HistoryResultSummarySnapshot | None,
) -> GcsimTooltipViewModel | None:
    if summary is None:
        return None
    payload = summary.payload
    return GcsimTooltipViewModel(
        title=summary.label or "GCSIM",
        status=str(payload.get("status") or "saved"),
        clear_time_seconds=summary.elapsed_seconds,
        dps_mean=summary.dps,
        total_damage_mean=summary.damage,
        scenario_total_hp=_optional_float(payload.get("scenario_total_hp")),
        target_mode=str(payload.get("target_mode") or ""),
        period_start=str(payload.get("period_start") or ""),
        floor=_optional_int(payload.get("floor")) or 0,
        config_path="",
        scenario_path="",
        rotation_hash=str(payload.get("rotation_hash") or ""),
        warnings=summary.warnings,
        issues=tuple(str(value) for value in payload.get("issues") or ()),
        stale_reasons=tuple(str(value) for value in payload.get("stale_reasons") or ()),
        notes=tuple(str(value) for value in payload.get("notes") or ()),
    )


def _dummy_fact_tooltip(dummy: Any, summary: HistoryResultSummarySnapshot | None):
    if dummy is None and summary is None:
        return None
    duration = int(
        (
            getattr(dummy, "duration_seconds", None)
            or (summary.elapsed_seconds if summary else 0)
        )
        or 0
    )
    dps = getattr(dummy, "factual_dps", None) if dummy is not None else None
    if dps is None and summary is not None:
        dps = summary.dps
    return FactDpsTooltipViewModel(
        title=(summary.label if summary else "Fact DPS") or "Fact DPS",
        formula="Damage / elapsed time",
        total_hp=getattr(dummy, "target_hp", None),
        total_solo_hp=getattr(dummy, "target_hp", None),
        total_multi_target_hp=None,
        hp_mode="dummy",
        hp_mode_label=getattr(dummy, "target_label", "") if dummy is not None else "",
        elapsed_seconds=duration,
        calculated_dps=None if dps is None else int(dps),
        hp_source_label="",
        warnings=() if summary is None else summary.warnings,
    )


def _result(bundle, result_type: str, chamber_index: int, side: int):
    return next(
        (
            item
            for item in bundle.result_summaries
            if item.result_type == result_type
            and item.chamber_index == int(chamber_index)
            and item.side == int(side)
        ),
        None,
    )


def _first_result(bundle, result_type: str):
    return next(
        (
            item
            for item in bundle.result_summaries
            if item.result_type == result_type
        ),
        None,
    )


def _side_result(results, side: int):
    return next((item for item in results if int(item.side) == int(side)), None)


def _side_elapsed(results, side: int, timer, timer_prefix: str) -> int:
    result = _side_result(results, side)
    if result is not None and result.elapsed_seconds is not None:
        return int(result.elapsed_seconds)
    value = None if timer is None else getattr(timer, f"{timer_prefix}_elapsed_seconds")
    return 0 if value is None else int(value)


def _dps(summary, side_result):
    if summary is not None and summary.dps is not None:
        return summary.dps
    return None if side_result is None else side_result.factual_dps


def _gcsim_status(bundle: HistorySnapshotBundle) -> str:
    key = (
        "app_shell.history.right_panel.gcsim_saved"
        if any(item.result_type == "sim_dps" for item in bundle.result_summaries)
        else "app_shell.history.right_panel.gcsim_not_run"
    )
    return tr(key)


def _visible_teams(bundle: HistorySnapshotBundle):
    limit = 2 if bundle.run_type == HISTORY_RUN_TYPE_ABYSS else 1
    return tuple(sorted(bundle.teams, key=lambda item: item.team_index)[:limit])


def _asset_path(bundle_dir: Path, value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text)
    return str(path if path.is_absolute() else bundle_dir / path)


def _character_meta(character) -> str:
    parts = []
    if character.level is not None:
        parts.append(f"Lv.{int(character.level)}")
    if character.constellation is not None:
        parts.append(f"C{int(character.constellation)}")
    if character.element:
        parts.append(character.element)
    return " | ".join(parts)


def _set_label(item) -> str:
    return f"{item.set_name} {int(item.piece_count)}p".strip()


def _artifact_badge(build) -> str:
    if build is None:
        return "ART"
    bonuses = build.active_set_bonuses
    if len(bonuses) >= 2:
        return f"{bonuses[0].piece_count}+{bonuses[1].piece_count}"
    if bonuses:
        return f"{bonuses[0].piece_count}p"
    return "ART"


def _artifact_stat_badge(build) -> str:
    if build is None:
        return ""
    goblet = next((item for item in build.artifact_slots if int(item.position) == 4), None)
    if goblet is not None and goblet.main_stat is not None:
        row = goblet.main_stat
        return row.icon_label or _square_label(row.label or row.key, "")
    return ""


def _square_label(value: str, fallback: str) -> str:
    chars = "".join(part[:1] for part in str(value).split() if part)
    return (chars or str(value)[:3] or fallback).upper()[:4]


def _remaining_time(seconds: int) -> str:
    minutes, remainder = divmod(max(0, int(seconds)), 60)
    return f"{minutes:02d}:{remainder:02d}"


def _format_factual_dps(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{int(round(float(value))):,}"


def _format_sim_result(summary: HistoryResultSummarySnapshot | None) -> str:
    if summary is None:
        return "not run"
    payload = summary.payload
    if bool(payload.get("stale")) or payload.get("stale_reasons"):
        return "stale"
    status = str(payload.get("status") or "saved")
    if status not in {"saved", "passed", "run_passed"}:
        return "failed"
    if summary.dps is None:
        return "failed"
    dps = _format_compact_dps(summary.dps)
    if summary.elapsed_seconds is None:
        return dps
    return f"{float(summary.elapsed_seconds):g}s / {dps}"


def _format_compact_dps(value: float | int) -> str:
    if value is None:
        return "-"
    number = float(value)
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:g}m"
    if abs(number) >= 1_000:
        return f"{number / 1_000:g}k"
    return str(int(round(number)))


def _optional_int(value: Any) -> int | None:
    try:
        return None if value is None or value == "" else int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _dedupe(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value).strip()))


__all__ = [
    "build_history_snapshot_right_panel_view_model",
    "first_occupied_history_slot",
]
