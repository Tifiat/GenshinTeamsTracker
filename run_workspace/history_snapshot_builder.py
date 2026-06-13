"""Build immutable History Snapshot Bundles from supplied live run data.

This module is intentionally backend-only glue between typed `RunSessionState`,
the right-panel view model, and the existing History Snapshot Bundle v1 schema.
It must not read Qt widgets, account/artifact DBs, generated app data, caches,
real asset files, or network state. Missing optional data stays empty and is
reported through warnings where the caller needs a follow-up source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from run_workspace.history_snapshot import (
    HISTORY_RUN_TYPE_ABYSS,
    HISTORY_RUN_TYPE_DPS_DUMMY,
    HistoryAbyssChamberSnapshot,
    HistoryAbyssScenarioSnapshot,
    HistoryAbyssSideResultSnapshot,
    HistoryAbyssTimerSnapshot,
    HistoryAccountProfileSnapshot,
    HistoryArtifactBuildSnapshot,
    HistoryArtifactSlotSnapshot,
    HistoryAssetRefSnapshot,
    HistoryBonusSourceSnapshot,
    HistoryCharacterSnapshot,
    HistoryDpsDummyScenarioSnapshot,
    HistoryPreviewRefSnapshot,
    HistoryResultSummarySnapshot,
    HistoryScenarioSnapshot,
    HistorySetBonusSnapshot,
    HistorySnapshotBundle,
    HistoryStatRowSnapshot,
    HistoryTeamSlotSnapshot,
    HistoryTeamSnapshot,
    HistoryWeaponSnapshot,
    normalize_history_run_type,
)
from run_workspace.models import calculate_abyss_chamber_result
from run_workspace.right_panel_prototype_view_model import (
    MODE_ABYSS,
    MODE_DPS_DUMMY,
    FactDpsTooltipViewModel,
    GcsimTooltipViewModel,
    RightPanelBonusSourceDisplayItem,
    RightPanelChamberRowViewModel,
    RightPanelDetailRowViewModel,
    RightPanelGcsimChamberResult,
    RightPanelPrototypeViewModel,
    RightPanelSelectedDetailsViewModel,
    RightPanelSlotPrototypeViewModel,
)
from run_workspace.session import RunSessionController, RunSessionState
from run_workspace.team_builder import (
    TeamBuilderSlotState,
    TeamBuilderState,
    TeamBuilderTeamState,
)


WARNING_VIEW_MODEL_MODE_MISMATCH = "history_builder_view_model_mode_mismatch"
WARNING_RIGHT_PANEL_SLOT_MISSING = "history_builder_right_panel_slot_missing"
WARNING_RIGHT_PANEL_CHAMBER_ROW_MISSING = "history_builder_chamber_row_missing"
WARNING_DPS_DUMMY_FACTUAL_INPUTS_NOT_IMPLEMENTED = (
    "dps_dummy_factual_inputs_not_implemented"
)

RESULT_TYPE_FACTUAL_DPS = "factual_dps"
RESULT_TYPE_SIM_DPS = "sim_dps"

SOURCE_RUN_SESSION_STATE = "run_session_state"
SOURCE_RIGHT_PANEL_VIEW_MODEL = "right_panel_view_model"
SOURCE_RUN_SESSION_GCSIM_RESULT = "run_session_gcsim_result"


@dataclass(frozen=True, slots=True)
class HistorySnapshotBuildContext:
    bundle_id: str
    created_at: str
    source: str
    content_language: str
    account: HistoryAccountProfileSnapshot | Mapping[str, Any] | None = None
    abyss_period_start: str = ""
    abyss_period_end: str = ""
    abyss_season_label: str = ""
    abyss_floor: int | None = None
    abyss_target_mode: str = ""
    asset_refs: tuple[HistoryAssetRefSnapshot, ...] = ()
    preview_refs: tuple[HistoryPreviewRefSnapshot, ...] = ()
    warnings: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)


def build_history_snapshot_bundle(
    session: RunSessionState | RunSessionController,
    right_panel_model: RightPanelPrototypeViewModel,
    context: HistorySnapshotBuildContext,
) -> HistorySnapshotBundle:
    """Build a History Snapshot Bundle from explicit typed inputs only."""

    session_state = _session_state(session)
    run_type = normalize_history_run_type(session_state.active_mode)
    warnings: list[str] = [*_text_tuple(context.warnings)]
    provenance = dict(context.provenance)
    if right_panel_model.mode != session_state.active_mode:
        warnings.append(WARNING_VIEW_MODEL_MODE_MISMATCH)
        provenance["session_mode"] = session_state.active_mode
        provenance["right_panel_mode"] = right_panel_model.mode

    asset_collector = _AssetCollector(context.asset_refs)
    team_state = session_state.team_state
    teams = _build_teams(
        team_state,
        right_panel_model,
        asset_collector=asset_collector,
        bundle_warnings=warnings,
    )

    if run_type == HISTORY_RUN_TYPE_DPS_DUMMY:
        scenario = HistoryScenarioSnapshot(
            run_type=run_type,
            dps_dummy=_build_dps_dummy_scenario(),
            warnings=(WARNING_DPS_DUMMY_FACTUAL_INPUTS_NOT_IMPLEMENTED,),
            provenance={"source": SOURCE_RUN_SESSION_STATE},
        )
        result_summaries: tuple[HistoryResultSummarySnapshot, ...] = ()
        warnings.append(WARNING_DPS_DUMMY_FACTUAL_INPUTS_NOT_IMPLEMENTED)
    else:
        scenario, result_summaries = _build_abyss_scenario_and_results(
            session_state,
            right_panel_model,
            context=context,
            asset_collector=asset_collector,
            bundle_warnings=warnings,
        )

    return HistorySnapshotBundle(
        bundle_id=context.bundle_id,
        created_at=context.created_at,
        run_type=run_type,
        source=context.source,
        content_language=context.content_language,
        account=_account_snapshot(context.account),
        teams=teams,
        scenario=scenario,
        result_summaries=result_summaries,
        asset_refs=asset_collector.refs(),
        preview_refs=tuple(context.preview_refs),
        warnings=tuple(_dedupe_texts(warnings)),
        provenance=provenance,
    )


def _session_state(session: RunSessionState | RunSessionController) -> RunSessionState:
    if isinstance(session, RunSessionState):
        return session
    state = getattr(session, "state", None)
    if isinstance(state, RunSessionState):
        return state
    raise TypeError("session must be RunSessionState or RunSessionController")


def _build_teams(
    team_state: TeamBuilderState,
    right_panel_model: RightPanelPrototypeViewModel,
    *,
    asset_collector: "_AssetCollector",
    bundle_warnings: list[str],
) -> tuple[HistoryTeamSnapshot, ...]:
    right_slots = _right_panel_slots_by_key(right_panel_model)
    teams: list[HistoryTeamSnapshot] = []
    for team_index, team in enumerate(team_state.teams):
        team_warnings = list(team.validation_warnings())
        slots: list[HistoryTeamSlotSnapshot] = []
        for slot in team.slots:
            right_slot = right_slots.get((team_index, slot.slot_index))
            if right_slot is None and not slot.is_empty:
                bundle_warnings.append(WARNING_RIGHT_PANEL_SLOT_MISSING)
            slots.append(
                _build_team_slot_snapshot(
                    slot,
                    team_index=team_index,
                    right_slot=right_slot,
                    selected_details=right_panel_model.selected_details,
                    asset_collector=asset_collector,
                )
            )
        teams.append(
            HistoryTeamSnapshot(
                team_index=team_index,
                label=f"Team {team_index + 1}",
                slots=tuple(slots),
                warnings=tuple(_dedupe_texts(team_warnings)),
                provenance={"source": SOURCE_RUN_SESSION_STATE},
            )
        )
    return tuple(teams)


def _build_team_slot_snapshot(
    slot: TeamBuilderSlotState,
    *,
    team_index: int,
    right_slot: RightPanelSlotPrototypeViewModel | None,
    selected_details: RightPanelSelectedDetailsViewModel,
    asset_collector: "_AssetCollector",
) -> HistoryTeamSlotSnapshot:
    details = _details_dict(slot.character_details_data)
    is_selected = _is_selected_details_for_slot(
        selected_details,
        team_index=team_index,
        slot_index=slot.slot_index,
    )
    slot_asset_refs: list[HistoryAssetRefSnapshot] = []
    warnings = _slot_warnings(slot, details, right_slot)
    if right_slot is None and not slot.is_empty:
        warnings.append(WARNING_RIGHT_PANEL_SLOT_MISSING)

    character = _build_character_snapshot(
        slot,
        details,
        right_slot=right_slot,
        selected_details=selected_details if is_selected else None,
        asset_collector=asset_collector,
        slot_asset_refs=slot_asset_refs,
    )
    weapon = _build_weapon_snapshot(
        slot,
        details,
        right_slot=right_slot,
        selected_details=selected_details if is_selected else None,
        asset_collector=asset_collector,
        slot_asset_refs=slot_asset_refs,
    )
    artifact_build = _build_artifact_build_snapshot(
        slot,
        details,
        right_slot=right_slot,
        selected_details=selected_details if is_selected else None,
        asset_collector=asset_collector,
        slot_asset_refs=slot_asset_refs,
    )
    stat_rows = (
        tuple(_stat_row_from_detail(row) for row in selected_details.stat_rows)
        if is_selected
        else ()
    )
    bonus_sources = (
        tuple(
            _bonus_source_snapshot(
                item,
                asset_collector=asset_collector,
                slot_asset_refs=slot_asset_refs,
            )
            for item in selected_details.bonus_sources
        )
        if is_selected
        else ()
    )

    provenance = {"source": SOURCE_RUN_SESSION_STATE}
    source_notes = _mapping(details.get("source_notes"))
    if source_notes:
        provenance["source_notes"] = dict(source_notes)

    return HistoryTeamSlotSnapshot(
        slot_index=slot.slot_index,
        character=character,
        weapon=weapon,
        artifact_build=artifact_build,
        stat_rows=stat_rows,
        bonus_sources=bonus_sources,
        asset_refs=tuple(_dedupe_asset_refs(slot_asset_refs)),
        warnings=tuple(_dedupe_texts(warnings)),
        provenance=provenance,
    )


def _build_character_snapshot(
    slot: TeamBuilderSlotState,
    details: Mapping[str, Any],
    *,
    right_slot: RightPanelSlotPrototypeViewModel | None,
    selected_details: RightPanelSelectedDetailsViewModel | None,
    asset_collector: "_AssetCollector",
    slot_asset_refs: list[HistoryAssetRefSnapshot],
) -> HistoryCharacterSnapshot | None:
    data = _mapping(details.get("account_character"))
    if not data and slot.character is not None:
        data = slot.character.to_dict()
    has_display_fallback = right_slot is not None and not right_slot.is_empty
    if not data and not has_display_fallback and selected_details is None:
        return None

    name = (
        _text(_first_present(data, "name", "character_name"))
        or _text(getattr(right_slot, "character_title", ""))
        or _text(getattr(selected_details, "character_name", ""))
    )
    character_id = _text(
        _first_present(data, "id", "character_id", "avatar_id", "hoyolab_entry_id")
    )
    portrait_ref = (
        _text(getattr(right_slot, "portrait_path", ""))
        or _text(_first_present(data, "portrait_path", "icon_path", "local_icon_path"))
    )
    side_icon_ref = _text(_first_present(data, "side_icon_path", "side_icon_ref"))
    if portrait_ref:
        ref = asset_collector.add(
            portrait_ref,
            role="character_portrait",
            label=name,
            provenance={"team_slot_source": SOURCE_RIGHT_PANEL_VIEW_MODEL},
        )
        slot_asset_refs.append(ref)
    if side_icon_ref:
        ref = asset_collector.add(
            side_icon_ref,
            role="character_side_icon",
            label=name,
            provenance={"team_slot_source": SOURCE_RUN_SESSION_STATE},
        )
        slot_asset_refs.append(ref)

    provenance = {}
    source = _text(data.get("source"))
    if source:
        provenance["source"] = source
    if character_id:
        provenance["debug_live_character_id"] = character_id

    return HistoryCharacterSnapshot(
        character_id=character_id,
        name=name,
        level=_optional_int(_first_present(data, "level", "character_level"))
        if selected_details is None
        else _coalesce_optional_int(
            _first_present(data, "level", "character_level"),
            selected_details.character_level,
        ),
        element=_text(_first_present(data, "element"))
        or _text(getattr(selected_details, "element", "")),
        rarity=_optional_int(data.get("rarity")),
        constellation=_coalesce_optional_int(
            _first_present(data, "constellation", "actived_constellation_num"),
            getattr(selected_details, "constellation", None),
        ),
        portrait_ref=portrait_ref,
        side_icon_ref=side_icon_ref,
        provenance=provenance,
    )


def _build_weapon_snapshot(
    slot: TeamBuilderSlotState,
    details: Mapping[str, Any],
    *,
    right_slot: RightPanelSlotPrototypeViewModel | None,
    selected_details: RightPanelSelectedDetailsViewModel | None,
    asset_collector: "_AssetCollector",
    slot_asset_refs: list[HistoryAssetRefSnapshot],
) -> HistoryWeaponSnapshot | None:
    data = _mapping(details.get("account_weapon"))
    if not data and slot.weapon is not None:
        data = slot.weapon.to_dict()
    has_display_fallback = right_slot is not None and bool(right_slot.weapon_label)
    selected_has_weapon = selected_details is not None and any(
        (
            selected_details.weapon_name,
            selected_details.weapon_level is not None,
            selected_details.weapon_refinement is not None,
            selected_details.weapon_icon_path,
            selected_details.weapon_base_atk,
            selected_details.weapon_secondary_label,
            selected_details.weapon_secondary_value,
            selected_details.weapon_tooltip,
        )
    )
    if not data and not has_display_fallback and not selected_has_weapon:
        return None

    name = (
        _text(_first_present(data, "name", "weapon_name"))
        or _text(getattr(right_slot, "weapon_label", ""))
        or _text(getattr(selected_details, "weapon_name", ""))
    )
    icon_ref = (
        _text(getattr(right_slot, "weapon_image_path", ""))
        or _text(getattr(selected_details, "weapon_icon_path", ""))
        or _text(_first_present(data, "icon_path", "local_icon_path", "weapon_icon_path"))
    )
    if icon_ref:
        ref = asset_collector.add(
            icon_ref,
            role="weapon_icon",
            label=name,
            provenance={"team_slot_source": SOURCE_RIGHT_PANEL_VIEW_MODEL},
        )
        slot_asset_refs.append(ref)

    stat_rows = _weapon_stat_rows(data, selected_details)
    weapon_tooltip = (
        _text(getattr(selected_details, "weapon_tooltip", ""))
        or _text(getattr(right_slot, "weapon_tooltip", ""))
    )
    passive_effects = (weapon_tooltip,) if weapon_tooltip else ()
    fingerprint = _text(
        _first_present(data, "weapon_fingerprint", "variant_key", "observed_stack_key")
    )
    provenance = {}
    source = _text(data.get("source"))
    if source:
        provenance["source"] = source
    if fingerprint:
        provenance["debug_live_weapon_fingerprint"] = fingerprint

    return HistoryWeaponSnapshot(
        weapon_id=_text(_first_present(data, "id", "weapon_id")),
        name=name,
        level=_coalesce_optional_int(
            _first_present(data, "level", "weapon_level"),
            getattr(selected_details, "weapon_level", None),
        ),
        promote_level=_optional_int(
            _first_present(data, "promote_level", "ascension", "ascension_phase")
        ),
        rarity=_optional_int(data.get("rarity")),
        refinement=_coalesce_optional_int(
            _first_present(data, "refinement", "affix_level"),
            getattr(selected_details, "weapon_refinement", None),
        ),
        weapon_type=_text(
            _first_present(data, "weapon_type", "weapon_type_name", "type_name", "type")
        ),
        weapon_fingerprint=fingerprint,
        icon_ref=icon_ref,
        passive_effects=passive_effects,
        stat_rows=stat_rows,
        provenance=provenance,
    )


def _weapon_stat_rows(
    data: Mapping[str, Any],
    selected_details: RightPanelSelectedDetailsViewModel | None,
) -> tuple[HistoryStatRowSnapshot, ...]:
    rows: list[HistoryStatRowSnapshot] = []
    if selected_details is not None:
        if _text(selected_details.weapon_base_atk):
            rows.append(
                HistoryStatRowSnapshot(
                    label="Base ATK",
                    value=_text(selected_details.weapon_base_atk),
                    key="base_atk",
                    source=SOURCE_RIGHT_PANEL_VIEW_MODEL,
                )
            )
        if _text(selected_details.weapon_secondary_label) or _text(
            selected_details.weapon_secondary_value
        ):
            rows.append(
                HistoryStatRowSnapshot(
                    label=_text(selected_details.weapon_secondary_label),
                    value=_text(selected_details.weapon_secondary_value),
                    key="secondary_stat",
                    source=SOURCE_RIGHT_PANEL_VIEW_MODEL,
                )
            )
    if not rows:
        base_atk = _text(_first_present(data, "base_atk", "base_atk_raw"))
        if base_atk:
            rows.append(
                HistoryStatRowSnapshot(
                    label="Base ATK",
                    value=base_atk,
                    key="base_atk",
                    source=SOURCE_RUN_SESSION_STATE,
                )
            )
    return tuple(rows)


def _build_artifact_build_snapshot(
    slot: TeamBuilderSlotState,
    details: Mapping[str, Any],
    *,
    right_slot: RightPanelSlotPrototypeViewModel | None,
    selected_details: RightPanelSelectedDetailsViewModel | None,
    asset_collector: "_AssetCollector",
    slot_asset_refs: list[HistoryAssetRefSnapshot],
) -> HistoryArtifactBuildSnapshot | None:
    selected_build = _mapping(details.get("selected_build"))
    if not selected_build and slot.artifact_build is not None:
        selected_build = slot.artifact_build.to_dict()
    summary = _artifact_summary(details)
    artifact_summary_vm = None if right_slot is None else right_slot.artifact_summary
    has_display_fallback = right_slot is not None and bool(right_slot.build_label)
    if (
        not selected_build
        and not summary
        and artifact_summary_vm is None
        and not has_display_fallback
    ):
        return None

    effects_by_set = _artifact_set_effects_by_key(details)
    artifact_slots = _artifact_slots_from_summary(summary, asset_collector, slot_asset_refs)
    active_set_bonuses = _active_set_bonuses_from_supplied_data(
        summary,
        right_slot=right_slot,
        effects_by_set=effects_by_set,
        asset_collector=asset_collector,
        slot_asset_refs=slot_asset_refs,
    )
    stat_rows = _artifact_stat_rows(summary, selected_details)
    source = _text(
        _first_present(selected_build, "source", "identity_source", "build_source")
    )
    build_name = (
        _text(_first_present(selected_build, "build_name", "name"))
        or _text(getattr(right_slot, "build_label", ""))
    )
    build_id = _text(_first_present(selected_build, "build_id", "id"))
    warnings = _artifact_build_warnings(details, summary, artifact_summary_vm)
    missing_positions = _artifact_missing_positions(summary, artifact_summary_vm)
    if right_slot is not None and _text(right_slot.artifact_image_path):
        ref = asset_collector.add(
            right_slot.artifact_image_path,
            role="artifact_build_icon",
            label=build_name,
            provenance={"team_slot_source": SOURCE_RIGHT_PANEL_VIEW_MODEL},
        )
        slot_asset_refs.append(ref)

    provenance = {}
    note = _text(selected_build.get("provenance_note"))
    if note:
        provenance["provenance_note"] = note
    if build_id:
        provenance["debug_live_build_id"] = build_id

    return HistoryArtifactBuildSnapshot(
        source=source,
        build_id=build_id,
        build_name=build_name,
        artifact_slots=artifact_slots,
        active_set_bonuses=active_set_bonuses,
        stat_rows=stat_rows,
        crit_value=_coalesce_optional_float(
            _first_present(summary, "crit_value"),
            getattr(artifact_summary_vm, "crit_value", None),
            getattr(selected_details, "crit_value", None),
        ),
        proc_count=_coalesce_optional_int(
            _first_present(summary, "proc_count"),
            getattr(artifact_summary_vm, "proc_count", None),
        ),
        missing_positions=missing_positions,
        warnings=tuple(_dedupe_texts(warnings)),
        provenance=provenance,
    )


def _artifact_slots_from_summary(
    summary: Mapping[str, Any],
    asset_collector: "_AssetCollector",
    slot_asset_refs: list[HistoryAssetRefSnapshot],
) -> tuple[HistoryArtifactSlotSnapshot, ...]:
    raw_slots = summary.get("slots") or summary.get("artifact_slots")
    slots: list[HistoryArtifactSlotSnapshot] = []
    if isinstance(raw_slots, list):
        for raw_slot in raw_slots:
            item = _mapping(raw_slot)
            if not item:
                continue
            snapshot = _artifact_slot_from_mapping(item)
            if snapshot is None:
                continue
            if snapshot.icon_ref:
                ref = asset_collector.add(
                    snapshot.icon_ref,
                    role="artifact_icon",
                    label=snapshot.piece_name,
                    provenance={"position": snapshot.position},
                )
                slot_asset_refs.append(ref)
            slots.append(snapshot)

    if not slots:
        artifact_ids = _mapping(summary.get("artifact_ids_by_pos"))
        for raw_position, raw_artifact_id in sorted(
            artifact_ids.items(),
            key=lambda item: _optional_int(item[0]) or 0,
        ):
            position = _optional_int(raw_position)
            if position is None:
                continue
            artifact_id = _text(raw_artifact_id)
            if not artifact_id:
                continue
            slots.append(
                HistoryArtifactSlotSnapshot(
                    position=position,
                    artifact_id=artifact_id,
                    provenance={"source": "artifact_ids_by_pos"},
                )
            )
    return tuple(sorted(slots, key=lambda item: item.position))


def _artifact_slot_from_mapping(
    item: Mapping[str, Any],
) -> HistoryArtifactSlotSnapshot | None:
    position = _optional_int(_first_present(item, "position", "pos", "slot_position"))
    if position is None:
        return None
    main_stat = _main_stat_from_artifact_slot(item)
    substats = tuple(
        _stat_row_from_mapping(raw, source=SOURCE_RUN_SESSION_STATE)
        for raw in _mapping_list(item.get("substats"))
    )
    icon_ref = _text(_first_present(item, "icon_ref", "icon_path", "set_icon_path"))
    return HistoryArtifactSlotSnapshot(
        position=position,
        artifact_id=_text(_first_present(item, "artifact_id", "id")),
        set_uid=_text(item.get("set_uid")),
        set_name=_text(item.get("set_name")),
        piece_name=_text(_first_present(item, "piece_name", "name")),
        rarity=_optional_int(item.get("rarity")),
        level=_optional_int(item.get("level")),
        main_stat=main_stat,
        substats=substats,
        icon_ref=icon_ref,
        provenance={"source": SOURCE_RUN_SESSION_STATE},
    )


def _main_stat_from_artifact_slot(
    item: Mapping[str, Any],
) -> HistoryStatRowSnapshot | None:
    raw = item.get("main_stat")
    if isinstance(raw, Mapping):
        return _stat_row_from_mapping(raw, source=SOURCE_RUN_SESSION_STATE)
    label = _text(
        _first_present(item, "main_property_name", "main_stat_name", "property_name")
    )
    value = _text(
        _first_present(item, "main_property_value", "main_stat_value", "value")
    )
    key = _text(
        _first_present(item, "main_property_type", "main_stat_key", "property_type")
    )
    if not (label or value or key):
        return None
    return HistoryStatRowSnapshot(
        label=label or key,
        value=value,
        key=key,
        source=SOURCE_RUN_SESSION_STATE,
    )


def _active_set_bonuses_from_supplied_data(
    summary: Mapping[str, Any],
    *,
    right_slot: RightPanelSlotPrototypeViewModel | None,
    effects_by_set: Mapping[tuple[str, int], tuple[str, ...]],
    asset_collector: "_AssetCollector",
    slot_asset_refs: list[HistoryAssetRefSnapshot],
) -> tuple[HistorySetBonusSnapshot, ...]:
    bonuses: list[HistorySetBonusSnapshot] = []
    seen: set[tuple[str, str, int]] = set()

    supplied_mini_sets = getattr(right_slot, "build_mini_sets", ()) if right_slot else ()
    for item in supplied_mini_sets:
        key = (item.set_uid, item.set_name, int(item.piece_count))
        if key in seen:
            continue
        seen.add(key)
        effects = effects_by_set.get((item.set_uid, int(item.piece_count)), ())
        if item.icon_path:
            ref = asset_collector.add(
                item.icon_path,
                role="artifact_set_icon",
                label=item.set_name,
                provenance={"set_uid": item.set_uid},
            )
            slot_asset_refs.append(ref)
        bonuses.append(
            HistorySetBonusSnapshot(
                set_uid=item.set_uid,
                set_name=item.set_name,
                piece_count=int(item.piece_count),
                icon_ref=item.icon_path,
                effects=effects,
                source=SOURCE_RIGHT_PANEL_VIEW_MODEL,
                provenance={"owned_count": item.owned_count},
            )
        )

    for raw in _mapping_list(summary.get("active_set_bonuses") or summary.get("set_bonuses")):
        piece_count = _optional_int(_first_present(raw, "piece_count", "count")) or 0
        if piece_count <= 0:
            continue
        set_uid = _text(raw.get("set_uid"))
        set_name = _text(raw.get("set_name")) or set_uid
        key = (set_uid, set_name, piece_count)
        if key in seen:
            continue
        seen.add(key)
        icon_ref = _text(_first_present(raw, "icon_ref", "icon_path", "set_icon_path"))
        effects = _effects_from_mapping(raw)
        if not effects:
            effects = effects_by_set.get((set_uid, piece_count), ())
        if icon_ref:
            ref = asset_collector.add(
                icon_ref,
                role="artifact_set_icon",
                label=set_name,
                provenance={"set_uid": set_uid},
            )
            slot_asset_refs.append(ref)
        bonuses.append(
            HistorySetBonusSnapshot(
                set_uid=set_uid,
                set_name=set_name,
                piece_count=piece_count,
                icon_ref=icon_ref,
                effects=effects,
                source=SOURCE_RUN_SESSION_STATE,
            )
        )
    return tuple(bonuses)


def _artifact_set_effects_by_key(
    details: Mapping[str, Any],
) -> dict[tuple[str, int], tuple[str, ...]]:
    grouped: dict[tuple[str, int], list[str]] = {}
    for raw in details.get("artifact_set_display_stat_effects") or ():
        item = _mapping(raw)
        if not item:
            continue
        set_uid = _text(item.get("set_uid"))
        pieces_required = _optional_int(
            _first_present(item, "pieces_required", "piece_count", "count")
        )
        if not set_uid or pieces_required is None:
            continue
        label = _effect_label(item)
        if label:
            grouped.setdefault((set_uid, int(pieces_required)), []).append(label)
    return {key: tuple(_dedupe_texts(values)) for key, values in grouped.items()}


def _artifact_stat_rows(
    summary: Mapping[str, Any],
    selected_details: RightPanelSelectedDetailsViewModel | None,
) -> tuple[HistoryStatRowSnapshot, ...]:
    rows: list[HistoryStatRowSnapshot] = []
    stat_totals = summary.get("stat_totals")
    if isinstance(stat_totals, Mapping):
        for key, value in sorted(stat_totals.items()):
            rows.append(
                HistoryStatRowSnapshot(
                    label=_text(key),
                    value=_text(value),
                    key=_text(key),
                    source=SOURCE_RUN_SESSION_STATE,
                )
            )
    for raw in _mapping_list(stat_totals or summary.get("total_stats")):
        row = _stat_row_from_mapping(raw, source=SOURCE_RUN_SESSION_STATE)
        if row.label or row.value:
            rows.append(row)
    if not rows and selected_details is not None:
        rows.extend(_stat_row_from_detail(row) for row in selected_details.stat_rows)
    return tuple(rows)


def _artifact_missing_positions(
    summary: Mapping[str, Any],
    artifact_summary_vm: Any | None,
) -> tuple[int, ...]:
    values = summary.get("missing_positions")
    if values is None and artifact_summary_vm is not None:
        values = artifact_summary_vm.missing_positions
    result = [
        value
        for value in (_optional_int(item) for item in values or ())
        if value is not None
    ]
    return tuple(sorted(dict.fromkeys(result)))


def _artifact_build_warnings(
    details: Mapping[str, Any],
    summary: Mapping[str, Any],
    artifact_summary_vm: Any | None,
) -> list[str]:
    stat_snapshot = _mapping(details.get("stat_snapshot"))
    artifact = _mapping(stat_snapshot.get("artifact"))
    warnings: list[str] = []
    warnings.extend(_text_tuple(artifact.get("warnings")))
    warnings.extend(_text_tuple(summary.get("warnings")))
    if artifact_summary_vm is not None:
        warnings.extend(_text_tuple(artifact_summary_vm.warnings))
    return warnings


def _slot_warnings(
    slot: TeamBuilderSlotState,
    details: Mapping[str, Any],
    right_slot: RightPanelSlotPrototypeViewModel | None,
) -> list[str]:
    warnings: list[str] = []
    warnings.extend(_text_tuple(slot.warnings))
    warnings.extend(_text_tuple(details.get("warnings")))
    if right_slot is not None and right_slot.warning_count > 0:
        warnings.extend(
            row.strip()
            for row in right_slot.warning_tooltip.splitlines()
            if row.strip()
        )
    return warnings


def _bonus_source_snapshot(
    item: RightPanelBonusSourceDisplayItem,
    *,
    asset_collector: "_AssetCollector",
    slot_asset_refs: list[HistoryAssetRefSnapshot],
) -> HistoryBonusSourceSnapshot:
    if item.icon_path:
        ref = asset_collector.add(
            item.icon_path,
            role="bonus_source_icon",
            label=item.label,
            provenance={"source_kind": item.source_kind},
        )
        slot_asset_refs.append(ref)
    for index, path in enumerate(item.character_icons):
        if not path:
            continue
        ref = asset_collector.add(
            path,
            role="bonus_member_icon",
            label=item.character_tooltips[index]
            if index < len(item.character_tooltips)
            else item.label,
            provenance={"source_kind": item.source_kind},
        )
        slot_asset_refs.append(ref)
    effects = tuple(
        _dedupe_texts([*item.short_effects, *item.tooltip_effects])
    )
    provenance = {}
    if item.tooltip_title:
        provenance["tooltip_title"] = item.tooltip_title
    if item.tooltip_body:
        provenance["tooltip_body"] = item.tooltip_body
    return HistoryBonusSourceSnapshot(
        source_kind=item.source_kind,
        source_id=item.source_id,
        label=item.label,
        icon_ref=item.icon_path,
        effects=effects,
        applied=bool(item.applied),
        not_applied_reason=item.not_applied_reason,
        provenance=provenance,
    )


def _build_abyss_scenario_and_results(
    session_state: RunSessionState,
    right_panel_model: RightPanelPrototypeViewModel,
    *,
    context: HistorySnapshotBuildContext,
    asset_collector: "_AssetCollector",
    bundle_warnings: list[str],
) -> tuple[HistoryScenarioSnapshot, tuple[HistoryResultSummarySnapshot, ...]]:
    rows_by_index = {
        index: row
        for index, row in enumerate(right_panel_model.chamber_rows, start=1)
    }
    sim_summaries = _sim_result_summaries_from_session(session_state.abyss.gcsim_chamber_results)
    sim_keys = {
        _result_summary_key(summary)
        for summary in sim_summaries
    }
    row_sim_summaries = _sim_result_summaries_from_rows(
        right_panel_model.chamber_rows,
        existing_keys=sim_keys,
    )
    result_summaries: list[HistoryResultSummarySnapshot] = [
        *sim_summaries,
        *row_sim_summaries,
    ]
    sim_refs = {
        key: _sim_result_ref(
            chamber_index=summary.chamber_index or 0,
            side=summary.side or 0,
            team_index=summary.team_index or 0,
        )
        for summary in result_summaries
        if summary.result_type == RESULT_TYPE_SIM_DPS
        for key in (_result_summary_key(summary),)
    }

    chambers: list[HistoryAbyssChamberSnapshot] = []
    for chamber_index, timer_state in enumerate(
        session_state.abyss.timer_states,
        start=1,
    ):
        result = calculate_abyss_chamber_result(
            timer_state,
            chamber_index=chamber_index,
        )
        row = rows_by_index.get(chamber_index)
        if row is None:
            bundle_warnings.append(WARNING_RIGHT_PANEL_CHAMBER_ROW_MISSING)
        factual_summaries = _factual_result_summaries_from_row(
            row,
            chamber_index=chamber_index,
        )
        result_summaries.extend(factual_summaries)
        side_results = _abyss_side_results(
            row,
            result=result,
            sim_refs=sim_refs,
        )
        enemies = _abyss_enemies_from_row(
            row,
            chamber_index=chamber_index,
            asset_collector=asset_collector,
        )
        chambers.append(
            HistoryAbyssChamberSnapshot(
                chamber_index=chamber_index,
                chamber_label="" if row is None else row.chamber_label,
                timer=HistoryAbyssTimerSnapshot(
                    team1_left_seconds=timer_state.team1_left_seconds,
                    team2_left_seconds=timer_state.team2_left_seconds,
                    start_seconds=timer_state.start_seconds,
                    normalized_team1_left_seconds=(
                        result.normalized_timer_state.team1_left_seconds
                    ),
                    normalized_team2_left_seconds=(
                        result.normalized_timer_state.team2_left_seconds
                    ),
                    team1_elapsed_seconds=result.team1_elapsed_seconds,
                    team2_elapsed_seconds=result.team2_elapsed_seconds,
                    total_elapsed_seconds=result.total_elapsed_seconds,
                    warnings=result.warnings,
                ),
                side_results=side_results,
                enemies=enemies,
                warnings=tuple(_dedupe_texts(result.warnings)),
                provenance={"source": SOURCE_RUN_SESSION_STATE},
            )
        )

    abyss_metadata = _abyss_metadata_from_context_results_and_rows(
        context,
        session_state.abyss.gcsim_chamber_results,
        right_panel_model.chamber_rows,
    )
    abyss = HistoryAbyssScenarioSnapshot(
        chambers=tuple(chambers),
        period_start=abyss_metadata["period_start"],
        period_end=abyss_metadata["period_end"],
        season_label=abyss_metadata["season_label"],
        floor=abyss_metadata["floor"],
        target_mode=abyss_metadata["target_mode"],
        total_elapsed_seconds=sum(
            chamber.timer.total_elapsed_seconds or 0
            for chamber in chambers
            if chamber.timer is not None
        ),
        warnings=tuple(_dedupe_texts(bundle_warnings)),
        provenance={"source": SOURCE_RUN_SESSION_STATE},
    )
    scenario = HistoryScenarioSnapshot(
        run_type=HISTORY_RUN_TYPE_ABYSS,
        abyss=abyss,
        warnings=tuple(_dedupe_texts(bundle_warnings)),
        provenance={"source": SOURCE_RUN_SESSION_STATE},
    )
    return scenario, tuple(result_summaries)


def _abyss_side_results(
    row: RightPanelChamberRowViewModel | None,
    *,
    result: Any,
    sim_refs: Mapping[tuple[int | None, int | None, int | None], str],
) -> tuple[HistoryAbyssSideResultSnapshot, ...]:
    side_results: list[HistoryAbyssSideResultSnapshot] = []
    for side, team_index, elapsed in (
        (1, 0, result.team1_elapsed_seconds),
        (2, 1, result.team2_elapsed_seconds),
    ):
        tooltip = _factual_tooltip_for_side(row, side)
        key = (team_index, result.chamber_index, side)
        side_results.append(
            HistoryAbyssSideResultSnapshot(
                side=side,
                team_index=team_index,
                elapsed_seconds=_coalesce_optional_int(
                    getattr(tooltip, "elapsed_seconds", None),
                    elapsed,
                ),
                total_hp=None if tooltip is None else tooltip.total_hp,
                factual_dps=None if tooltip is None else tooltip.calculated_dps,
                hp_source="" if tooltip is None else tooltip.hp_source_label,
                target_mode="" if tooltip is None else tooltip.hp_mode,
                sim_result_ref=sim_refs.get(key, ""),
                warnings=()
                if tooltip is None
                else tuple(
                    _dedupe_texts(
                        [*tooltip.warnings, tooltip.unavailable_reason]
                    )
                ),
                provenance={"source": SOURCE_RIGHT_PANEL_VIEW_MODEL}
                if tooltip is not None
                else {"source": SOURCE_RUN_SESSION_STATE},
            )
        )
    return tuple(side_results)


def _abyss_enemies_from_row(
    row: RightPanelChamberRowViewModel | None,
    *,
    chamber_index: int,
    asset_collector: "_AssetCollector",
) -> tuple[Mapping[str, Any], ...]:
    enemies: list[Mapping[str, Any]] = []
    for side, tooltip in (
        (1, _factual_tooltip_for_side(row, 1)),
        (2, _factual_tooltip_for_side(row, 2)),
    ):
        if tooltip is None:
            continue
        for enemy in tooltip.enemies:
            payload = enemy.to_dict()
            payload["side"] = side
            payload["chamber_index"] = chamber_index
            if enemy.cached_icon_path:
                asset_collector.add(
                    enemy.cached_icon_path,
                    role="enemy_icon",
                    label=enemy.primary_display_name,
                    provenance={"chamber_index": chamber_index, "side": side},
                )
            enemies.append(payload)
    return tuple(enemies)


def _factual_result_summaries_from_row(
    row: RightPanelChamberRowViewModel | None,
    *,
    chamber_index: int,
) -> tuple[HistoryResultSummarySnapshot, ...]:
    if row is None:
        return ()
    summaries: list[HistoryResultSummarySnapshot] = []
    for side, team_index, tooltip in (
        (1, 0, row.factual_team1_tooltip),
        (2, 1, row.factual_team2_tooltip),
    ):
        if tooltip is None or tooltip.calculated_dps is None:
            continue
        summaries.append(
            HistoryResultSummarySnapshot(
                result_type=RESULT_TYPE_FACTUAL_DPS,
                label=tooltip.title,
                team_index=team_index,
                chamber_index=chamber_index,
                side=side,
                dps=float(tooltip.calculated_dps),
                elapsed_seconds=float(tooltip.elapsed_seconds),
                source=SOURCE_RIGHT_PANEL_VIEW_MODEL,
                payload={
                    "formula": tooltip.formula,
                    "hp_mode": tooltip.hp_mode,
                    "hp_mode_label": tooltip.hp_mode_label,
                    "hp_source_label": tooltip.hp_source_label,
                    "total_hp": tooltip.total_hp,
                    "total_solo_hp": tooltip.total_solo_hp,
                    "total_multi_target_hp": tooltip.total_multi_target_hp,
                    "unavailable_reason": tooltip.unavailable_reason,
                    "enemies": [enemy.to_dict() for enemy in tooltip.enemies],
                },
                warnings=tuple(
                    _dedupe_texts([*tooltip.warnings, tooltip.unavailable_reason])
                ),
                provenance={"source": SOURCE_RIGHT_PANEL_VIEW_MODEL},
            )
        )
    return tuple(summaries)


def _sim_result_summaries_from_session(
    results: tuple[RightPanelGcsimChamberResult, ...],
) -> tuple[HistoryResultSummarySnapshot, ...]:
    return tuple(_sim_summary_from_session_result(result) for result in results)


def _sim_summary_from_session_result(
    result: RightPanelGcsimChamberResult,
) -> HistoryResultSummarySnapshot:
    ref = _sim_result_ref(
        chamber_index=result.chamber,
        side=result.side,
        team_index=result.team_index,
    )
    return HistoryResultSummarySnapshot(
        result_type=RESULT_TYPE_SIM_DPS,
        label=f"GCSIM C{int(result.chamber)} side {int(result.side)}",
        team_index=int(result.team_index),
        chamber_index=int(result.chamber),
        side=int(result.side),
        dps=result.dps_mean,
        damage=result.total_damage_mean,
        elapsed_seconds=result.clear_time_seconds,
        source=SOURCE_RUN_SESSION_GCSIM_RESULT,
        payload={
            "sim_result_ref": ref,
            "status": result.status,
            "error_category": result.error_category,
            "scenario_total_hp": result.scenario_total_hp,
            "target_mode": result.target_mode,
            "period_start": result.period_start,
            "floor": result.floor,
            "config_path": result.config_path,
            "scenario_path": result.scenario_path,
            "mode": result.mode,
            "rotation_hash": result.rotation_hash,
            "stale": result.stale,
            "issues": list(result.issues),
        },
        warnings=result.warnings,
        provenance={"source": SOURCE_RUN_SESSION_STATE},
    )


def _sim_result_summaries_from_rows(
    rows: tuple[RightPanelChamberRowViewModel, ...],
    *,
    existing_keys: set[tuple[int | None, int | None, int | None]],
) -> tuple[HistoryResultSummarySnapshot, ...]:
    summaries: list[HistoryResultSummarySnapshot] = []
    for chamber_index, row in enumerate(rows, start=1):
        for side, team_index, tooltip in (
            (1, 0, row.sim_team1_tooltip),
            (2, 1, row.sim_team2_tooltip),
        ):
            key = (team_index, chamber_index, side)
            if key in existing_keys or not _sim_tooltip_has_payload(tooltip):
                continue
            summaries.append(
                _sim_summary_from_tooltip(
                    tooltip,
                    chamber_index=chamber_index,
                    side=side,
                    team_index=team_index,
                )
            )
    return tuple(summaries)


def _sim_summary_from_tooltip(
    tooltip: GcsimTooltipViewModel,
    *,
    chamber_index: int,
    side: int,
    team_index: int,
) -> HistoryResultSummarySnapshot:
    ref = _sim_result_ref(
        chamber_index=chamber_index,
        side=side,
        team_index=team_index,
    )
    return HistoryResultSummarySnapshot(
        result_type=RESULT_TYPE_SIM_DPS,
        label=tooltip.title,
        team_index=team_index,
        chamber_index=chamber_index,
        side=side,
        dps=tooltip.dps_mean,
        damage=tooltip.total_damage_mean,
        elapsed_seconds=tooltip.clear_time_seconds,
        source=SOURCE_RIGHT_PANEL_VIEW_MODEL,
        payload={
            "sim_result_ref": ref,
            "status": tooltip.status,
            "scenario_total_hp": tooltip.scenario_total_hp,
            "target_mode": tooltip.target_mode,
            "period_start": tooltip.period_start,
            "floor": tooltip.floor,
            "config_path": tooltip.config_path,
            "scenario_path": tooltip.scenario_path,
            "rotation_hash": tooltip.rotation_hash,
            "issues": list(tooltip.issues),
            "stale_reasons": list(tooltip.stale_reasons),
            "notes": list(tooltip.notes),
        },
        warnings=tuple(_dedupe_texts([*tooltip.warnings, *tooltip.stale_reasons])),
        provenance={"source": SOURCE_RIGHT_PANEL_VIEW_MODEL},
    )


def _build_dps_dummy_scenario() -> HistoryDpsDummyScenarioSnapshot:
    return HistoryDpsDummyScenarioSnapshot(
        result_status="pending_factual_inputs",
        warnings=(WARNING_DPS_DUMMY_FACTUAL_INPUTS_NOT_IMPLEMENTED,),
        provenance={
            "source": SOURCE_RUN_SESSION_STATE,
            "note": "DPS Dummy target/damage inputs are not modeled yet.",
        },
    )


def _abyss_metadata_from_context_results_and_rows(
    context: HistorySnapshotBuildContext,
    results: tuple[RightPanelGcsimChamberResult, ...],
    rows: tuple[RightPanelChamberRowViewModel, ...],
) -> dict[str, Any]:
    metadata = {
        "period_start": _text(context.abyss_period_start),
        "period_end": _text(context.abyss_period_end),
        "season_label": _text(context.abyss_season_label),
        "floor": _optional_int(context.abyss_floor),
        "target_mode": _text(context.abyss_target_mode),
    }
    fallback = _abyss_metadata_from_results_and_rows(results, rows)
    for key, value in fallback.items():
        if metadata.get(key) in ("", None):
            metadata[key] = value
    return metadata


def _abyss_metadata_from_results_and_rows(
    results: tuple[RightPanelGcsimChamberResult, ...],
    rows: tuple[RightPanelChamberRowViewModel, ...],
) -> dict[str, Any]:
    metadata = {
        "period_start": "",
        "period_end": "",
        "season_label": "",
        "floor": None,
        "target_mode": "",
    }
    for result in results:
        if result.period_start and not metadata["period_start"]:
            metadata["period_start"] = result.period_start
        if result.floor and metadata["floor"] is None:
            metadata["floor"] = int(result.floor)
        if result.target_mode and not metadata["target_mode"]:
            metadata["target_mode"] = result.target_mode
        if (
            metadata["period_start"]
            and metadata["floor"] is not None
            and metadata["target_mode"]
        ):
            return metadata

    for row in rows:
        for tooltip in (row.sim_team1_tooltip, row.sim_team2_tooltip):
            if tooltip is None:
                continue
            if tooltip.period_start and not metadata["period_start"]:
                metadata["period_start"] = tooltip.period_start
            if tooltip.floor and metadata["floor"] is None:
                metadata["floor"] = int(tooltip.floor)
            if tooltip.target_mode and not metadata["target_mode"]:
                metadata["target_mode"] = tooltip.target_mode
        for tooltip in (row.factual_team1_tooltip, row.factual_team2_tooltip):
            if tooltip is not None and tooltip.hp_mode and not metadata["target_mode"]:
                metadata["target_mode"] = tooltip.hp_mode
    return metadata


def _factual_tooltip_for_side(
    row: RightPanelChamberRowViewModel | None,
    side: int,
) -> FactDpsTooltipViewModel | None:
    if row is None:
        return None
    return row.factual_team1_tooltip if int(side) == 1 else row.factual_team2_tooltip


def _sim_tooltip_has_payload(tooltip: GcsimTooltipViewModel | None) -> bool:
    if tooltip is None:
        return False
    if tooltip.status and tooltip.status != "not run":
        return True
    return any(
        value is not None and value != ""
        for value in (
            tooltip.clear_time_seconds,
            tooltip.dps_mean,
            tooltip.total_damage_mean,
            tooltip.scenario_total_hp,
            tooltip.config_path,
            tooltip.scenario_path,
            tooltip.rotation_hash,
        )
    ) or bool(tooltip.warnings or tooltip.issues or tooltip.stale_reasons)


def _result_summary_key(
    summary: HistoryResultSummarySnapshot,
) -> tuple[int | None, int | None, int | None]:
    return (summary.team_index, summary.chamber_index, summary.side)


def _sim_result_ref(*, chamber_index: int, side: int, team_index: int) -> str:
    if not (chamber_index and side):
        return ""
    return f"sim:{int(chamber_index)}:{int(side)}:{int(team_index)}"


def _right_panel_slots_by_key(
    model: RightPanelPrototypeViewModel,
) -> dict[tuple[int, int], RightPanelSlotPrototypeViewModel]:
    return {
        (int(team.team_index), int(slot.slot_index)): slot
        for team in model.teams
        for slot in team.slots
    }


def _account_snapshot(
    value: HistoryAccountProfileSnapshot | Mapping[str, Any] | None,
) -> HistoryAccountProfileSnapshot | None:
    if value is None:
        return None
    if isinstance(value, HistoryAccountProfileSnapshot):
        return value
    data = _mapping(value)
    return HistoryAccountProfileSnapshot(
        account_uid=_text(_first_present(data, "account_uid", "uid")),
        nickname=_text(_first_present(data, "nickname", "name")),
        server=_text(data.get("server")),
        profile_name=_text(data.get("profile_name")),
        source=_text(data.get("source")),
        provenance=dict(_mapping(data.get("provenance"))),
    )


def _is_selected_details_for_slot(
    selected_details: RightPanelSelectedDetailsViewModel,
    *,
    team_index: int,
    slot_index: int,
) -> bool:
    return (
        bool(selected_details.has_selection)
        and selected_details.team_index == team_index
        and selected_details.slot_index == slot_index
    )


def _artifact_summary(details: Mapping[str, Any]) -> dict[str, Any]:
    stat_snapshot = _mapping(details.get("stat_snapshot"))
    artifact = _mapping(stat_snapshot.get("artifact"))
    return _mapping(artifact.get("summary"))


def _details_dict(value: Any | None) -> dict[str, Any]:
    if value is None:
        return {}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
        return dict(data) if isinstance(data, Mapping) else {}
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _stat_row_from_detail(row: RightPanelDetailRowViewModel) -> HistoryStatRowSnapshot:
    return HistoryStatRowSnapshot(
        label=row.label,
        value=row.value,
        key=_text(row.icon_label),
        icon_label=row.icon_label,
        source=SOURCE_RIGHT_PANEL_VIEW_MODEL,
    )


def _stat_row_from_mapping(
    raw: Mapping[str, Any],
    *,
    source: str,
) -> HistoryStatRowSnapshot:
    item = _mapping(raw)
    label = _text(
        _first_present(
            item,
            "label",
            "property_name",
            "main_property_name",
            "name",
            "stat_key",
            "key",
        )
    )
    value = _text(
        _first_present(
            item,
            "value",
            "selected",
            "display_value",
            "raw_value",
            "main_property_value",
        )
    )
    key = _text(
        _first_present(item, "key", "stat_key", "property_type", "main_property_type")
    )
    return HistoryStatRowSnapshot(
        label=label,
        value=value,
        key=key,
        icon_label=_text(item.get("icon_label")),
        unit=_text(item.get("unit")),
        source=_text(item.get("source")) or source,
        provenance=dict(_mapping(item.get("provenance"))),
    )


def _effects_from_mapping(raw: Mapping[str, Any]) -> tuple[str, ...]:
    effects: list[str] = []
    raw_effects = raw.get("effects") or raw.get("effect_rows") or ()
    if isinstance(raw_effects, str):
        raw_effects = (raw_effects,)
    for value in raw_effects:
        text = _text(value)
        if text:
            effects.append(text)
    for key in ("effect", "description", "label"):
        text = _text(raw.get(key))
        if text:
            effects.append(text)
    return tuple(_dedupe_texts(effects))


def _effect_label(item: Mapping[str, Any]) -> str:
    text = _text(
        _first_present(
            item,
            "label",
            "display_label",
            "short_label",
            "description",
        )
    )
    if text:
        return text
    property_name = _text(item.get("property_name"))
    value = _text(item.get("value"))
    if property_name and value:
        return f"{property_name} {value}"
    return property_name or value


def _first_present(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _text_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(text for text in (_text(item) for item in value) if text)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coalesce_optional_int(*values: Any) -> int | None:
    for value in values:
        result = _optional_int(value)
        if result is not None:
            return result
    return None


def _coalesce_optional_float(*values: Any) -> float | None:
    for value in values:
        result = _optional_float(value)
        if result is not None:
            return result
    return None


def _dedupe_texts(values: list[str] | tuple[str, ...]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return result


def _dedupe_asset_refs(
    values: list[HistoryAssetRefSnapshot],
) -> list[HistoryAssetRefSnapshot]:
    seen: set[tuple[str, str]] = set()
    result: list[HistoryAssetRefSnapshot] = []
    for value in values:
        key = (value.path, value.role)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


class _AssetCollector:
    def __init__(self, initial: tuple[HistoryAssetRefSnapshot, ...] = ()) -> None:
        self._refs: list[HistoryAssetRefSnapshot] = []
        self._seen: set[tuple[str, str]] = set()
        for ref in initial:
            self._add_ref(ref)

    def add(
        self,
        path: str,
        *,
        role: str,
        label: str = "",
        provenance: Mapping[str, Any] | None = None,
    ) -> HistoryAssetRefSnapshot:
        ref = HistoryAssetRefSnapshot(
            path=_text(path),
            role=role,
            label=_text(label),
            provenance=dict(provenance or {}),
        )
        self._add_ref(ref)
        return ref

    def refs(self) -> tuple[HistoryAssetRefSnapshot, ...]:
        return tuple(self._refs)

    def _add_ref(self, ref: HistoryAssetRefSnapshot) -> None:
        if not ref.path:
            return
        key = (ref.path, ref.role)
        if key in self._seen:
            return
        self._seen.add(key)
        self._refs.append(ref)


__all__ = [
    "RESULT_TYPE_FACTUAL_DPS",
    "RESULT_TYPE_SIM_DPS",
    "WARNING_DPS_DUMMY_FACTUAL_INPUTS_NOT_IMPLEMENTED",
    "WARNING_RIGHT_PANEL_CHAMBER_ROW_MISSING",
    "WARNING_RIGHT_PANEL_SLOT_MISSING",
    "WARNING_VIEW_MODEL_MODE_MISMATCH",
    "HistorySnapshotBuildContext",
    "build_history_snapshot_bundle",
]
