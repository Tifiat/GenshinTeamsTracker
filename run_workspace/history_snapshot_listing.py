"""Minimal read-model for immutable History Snapshot Bundles.

This is the first browsing layer over saved snapshot JSON. It intentionally
does not render export images, query live account data, or build full snapshot
detail payloads; UI callers get compact immutable summaries only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from run_workspace.history_snapshot import (
    HISTORY_RUN_TYPE_ABYSS,
    HISTORY_RUN_TYPE_DPS_DUMMY,
    HISTORY_SNAPSHOT_GROUP_DPS_DUMMY,
    HISTORY_UNKNOWN_ABYSS_PERIOD,
    HistoryAbyssChamberSnapshot,
    HistoryAbyssSideResultSnapshot,
    HistorySnapshotBundle,
    HistorySnapshotBundleError,
    HistorySnapshotBundleReadError,
    HistorySnapshotBundleRecord,
    HistorySnapshotBundleStore,
    HistoryTeamSlotSnapshot,
)


@dataclass(frozen=True, slots=True)
class HistoryRunSummary:
    bundle_id: str
    run_type: str
    created_at: str
    source: str
    content_language: str
    bundle_path: Path
    group_key: str
    period_start: str = ""
    period_end: str = ""
    season_label: str = ""
    floor: int | None = None
    team_character_names: tuple[tuple[str, ...], ...] = ()
    team_summary: str = ""
    chamber_summaries: tuple[str, ...] = ()
    warnings_count: int = 0


@dataclass(frozen=True, slots=True)
class HistoryAbyssPeriodSummary:
    period_start: str = ""
    period_end: str = ""
    season_label: str = ""
    floor: int | None = None
    saved_run_count: int = 0
    chamber_labels: tuple[str, ...] = ()
    chamber_enemy_hp_summaries: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoryRunGroupSummary:
    run_type: str
    group_key: str
    group_label: str
    period_start: str = ""
    period_end: str = ""
    season_label: str = ""
    floor: int | None = None
    abyss_period_summary: HistoryAbyssPeriodSummary | None = None
    runs: tuple[HistoryRunSummary, ...] = ()


@dataclass(frozen=True, slots=True)
class HistorySnapshotSummaryListing:
    groups: tuple[HistoryRunGroupSummary, ...] = ()
    errors: tuple[HistorySnapshotBundleReadError, ...] = ()

    @property
    def run_count(self) -> int:
        return sum(len(group.runs) for group in self.groups)


@dataclass(frozen=True, slots=True)
class HistorySnapshotSetDetails:
    set_name: str
    piece_count: int = 0
    icon_ref: str = ""


@dataclass(frozen=True, slots=True)
class HistorySnapshotSlotDetails:
    slot_index: int
    character_name: str = ""
    weapon_name: str = ""
    weapon_icon_ref: str = ""
    artifact_build_label: str = ""
    artifact_sets: tuple[HistorySnapshotSetDetails, ...] = ()
    artifact_icon_refs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HistorySnapshotTeamDetails:
    team_index: int
    label: str = ""
    character_names: tuple[str, ...] = ()
    slots: tuple[HistorySnapshotSlotDetails, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HistorySnapshotChamberDetails:
    chamber_index: int
    label: str = ""
    timing_summary: str = ""
    factual_dps_summaries: tuple[str, ...] = ()
    sim_dps_summaries: tuple[str, ...] = ()
    enemy_hp_summaries: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HistorySnapshotDetailsPayload:
    bundle_id: str
    run_type: str
    created_at: str
    source: str
    content_language: str
    bundle_path: Path | None = None
    period_start: str = ""
    period_end: str = ""
    season_label: str = ""
    floor: int | None = None
    teams: tuple[HistorySnapshotTeamDetails, ...] = ()
    chamber_details: tuple[HistorySnapshotChamberDetails, ...] = ()
    factual_dps_summaries: tuple[str, ...] = ()
    sim_dps_summaries: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    provenance_notes: tuple[str, ...] = ()


def load_history_snapshot_summary_listing(root: str | Path) -> HistorySnapshotSummaryListing:
    store = HistorySnapshotBundleStore(root)
    listing = store.list_bundle_records()
    summaries = [_summary_from_record(store, record) for record in listing.records]
    return HistorySnapshotSummaryListing(
        groups=_group_summaries(summaries),
        errors=listing.errors,
    )


def load_history_snapshot_details_payload(
    root: str | Path,
    bundle_id: str,
) -> HistorySnapshotDetailsPayload | None:
    store = HistorySnapshotBundleStore(root)
    try:
        bundle = store.read_bundle(bundle_id)
    except HistorySnapshotBundleError:
        return None
    return history_snapshot_details_payload_from_bundle(bundle)


def history_snapshot_details_payload_from_bundle(
    bundle: HistorySnapshotBundle,
    *,
    bundle_path: str | Path | None = None,
) -> HistorySnapshotDetailsPayload:
    scenario = bundle.scenario
    abyss = None if scenario is None else scenario.abyss
    return HistorySnapshotDetailsPayload(
        bundle_id=bundle.bundle_id,
        run_type=bundle.run_type,
        created_at=bundle.created_at,
        source=bundle.source,
        content_language=bundle.content_language,
        bundle_path=None if bundle_path is None else Path(bundle_path),
        period_start="" if abyss is None else abyss.period_start,
        period_end="" if abyss is None else abyss.period_end,
        season_label="" if abyss is None else abyss.season_label,
        floor=None if abyss is None else abyss.floor,
        teams=tuple(_team_details(team) for team in bundle.teams),
        chamber_details=()
        if abyss is None
        else tuple(
            _chamber_details(chamber, floor=abyss.floor, bundle=bundle)
            for chamber in abyss.chambers
        ),
        factual_dps_summaries=_result_summaries(bundle, result_type="factual_dps"),
        sim_dps_summaries=_result_summaries(bundle, result_type="sim_dps"),
        warnings=tuple(_bundle_warnings(bundle)),
        provenance_notes=_provenance_notes(bundle.provenance),
    )


def _summary_from_record(
    store: HistorySnapshotBundleStore,
    record: HistorySnapshotBundleRecord,
) -> HistoryRunSummary:
    bundle = record.bundle
    scenario = bundle.scenario
    abyss = None if scenario is None else scenario.abyss
    relative_dir = store.bundle_relative_dir_for(bundle)
    parts = relative_dir.parts
    if bundle.run_type == HISTORY_RUN_TYPE_ABYSS:
        group_key = parts[1] if len(parts) >= 3 else HISTORY_UNKNOWN_ABYSS_PERIOD
    else:
        group_key = HISTORY_SNAPSHOT_GROUP_DPS_DUMMY

    team_names = _team_character_names(bundle)
    return HistoryRunSummary(
        bundle_id=bundle.bundle_id,
        run_type=bundle.run_type,
        created_at=bundle.created_at,
        source=bundle.source,
        content_language=bundle.content_language,
        bundle_path=record.path,
        group_key=group_key,
        period_start="" if abyss is None else abyss.period_start,
        period_end="" if abyss is None else abyss.period_end,
        season_label="" if abyss is None else abyss.season_label,
        floor=None if abyss is None else abyss.floor,
        team_character_names=team_names,
        team_summary=_team_summary(team_names),
        chamber_summaries=()
        if abyss is None
        else tuple(_chamber_summary(chamber, floor=abyss.floor) for chamber in abyss.chambers),
        warnings_count=_warnings_count(bundle),
    )


def _group_summaries(
    summaries: Iterable[HistoryRunSummary],
) -> tuple[HistoryRunGroupSummary, ...]:
    abyss_groups: dict[str, list[HistoryRunSummary]] = {}
    dps_runs: list[HistoryRunSummary] = []
    for summary in summaries:
        if summary.run_type == HISTORY_RUN_TYPE_ABYSS:
            abyss_groups.setdefault(summary.group_key, []).append(summary)
        elif summary.run_type == HISTORY_RUN_TYPE_DPS_DUMMY:
            dps_runs.append(summary)

    groups: list[HistoryRunGroupSummary] = []
    group_keys = sorted(
        (key for key in abyss_groups if key != HISTORY_UNKNOWN_ABYSS_PERIOD),
        reverse=True,
    )
    if HISTORY_UNKNOWN_ABYSS_PERIOD in abyss_groups:
        group_keys.append(HISTORY_UNKNOWN_ABYSS_PERIOD)

    for key in group_keys:
        runs = tuple(
            sorted(
                abyss_groups[key],
                key=lambda item: (item.created_at, item.bundle_id),
                reverse=True,
            )
        )
        first = runs[0]
        groups.append(
            HistoryRunGroupSummary(
                run_type=HISTORY_RUN_TYPE_ABYSS,
                group_key=key,
                group_label=_abyss_group_label(first, key),
                period_start=first.period_start,
                period_end=first.period_end,
                season_label=first.season_label,
                floor=first.floor,
                abyss_period_summary=_abyss_period_summary(runs),
                runs=runs,
            )
        )
    if dps_runs:
        groups.append(
            HistoryRunGroupSummary(
                run_type=HISTORY_RUN_TYPE_DPS_DUMMY,
                group_key=HISTORY_SNAPSHOT_GROUP_DPS_DUMMY,
                group_label=HISTORY_SNAPSHOT_GROUP_DPS_DUMMY,
                runs=tuple(
                    sorted(
                        dps_runs,
                        key=lambda item: (item.created_at, item.bundle_id),
                        reverse=True,
                    )
                ),
            )
        )
    return tuple(groups)


def _abyss_period_summary(
    runs: tuple[HistoryRunSummary, ...],
) -> HistoryAbyssPeriodSummary:
    if not runs:
        return HistoryAbyssPeriodSummary()
    first = runs[0]
    chamber_labels: list[str] = []
    enemy_lines: list[str] = []
    seen_lines: set[str] = set()
    for summary in runs:
        try:
            bundle = history_snapshot_details_payload_from_bundle_path(summary.bundle_path)
        except HistorySnapshotBundleError:
            continue
        for chamber in bundle.chamber_details:
            if chamber.label and chamber.label not in chamber_labels:
                chamber_labels.append(chamber.label)
            for line in chamber.enemy_hp_summaries:
                if line and line not in seen_lines:
                    seen_lines.add(line)
                    enemy_lines.append(line)
    return HistoryAbyssPeriodSummary(
        period_start=first.period_start,
        period_end=first.period_end,
        season_label=first.season_label,
        floor=first.floor,
        saved_run_count=len(runs),
        chamber_labels=tuple(chamber_labels),
        chamber_enemy_hp_summaries=tuple(enemy_lines),
    )


def history_snapshot_details_payload_from_bundle_path(
    path: str | Path,
) -> HistorySnapshotDetailsPayload:
    from run_workspace.history_snapshot import history_snapshot_bundle_from_json_text

    snapshot_path = Path(path)
    try:
        bundle = history_snapshot_bundle_from_json_text(
            snapshot_path.read_text(encoding="utf-8")
        )
    except OSError as exc:
        raise HistorySnapshotBundleError(
            f"History snapshot bundle not found or unreadable: {snapshot_path}"
        ) from exc
    return history_snapshot_details_payload_from_bundle(
        bundle,
        bundle_path=snapshot_path,
    )


def _team_details(team) -> HistorySnapshotTeamDetails:
    slots = tuple(_slot_details(slot) for slot in team.slots)
    names = tuple(slot.character_name for slot in slots if slot.character_name)
    return HistorySnapshotTeamDetails(
        team_index=team.team_index,
        label=team.label,
        character_names=names,
        slots=slots,
        warnings=team.warnings,
    )


def _slot_details(slot: HistoryTeamSlotSnapshot) -> HistorySnapshotSlotDetails:
    artifact_build = slot.artifact_build
    artifact_sets = ()
    artifact_icon_refs: tuple[str, ...] = ()
    if artifact_build is not None:
        artifact_sets = tuple(
            HistorySnapshotSetDetails(
                set_name=bonus.set_name,
                piece_count=bonus.piece_count,
                icon_ref=bonus.icon_ref,
            )
            for bonus in artifact_build.active_set_bonuses
        )
        artifact_icon_refs = tuple(
            ref
            for ref in (
                slot.icon_ref
                for slot in artifact_build.artifact_slots
                if slot.icon_ref
            )
        )
    return HistorySnapshotSlotDetails(
        slot_index=slot.slot_index,
        character_name="" if slot.character is None else slot.character.name,
        weapon_name="" if slot.weapon is None else slot.weapon.name,
        weapon_icon_ref="" if slot.weapon is None else slot.weapon.icon_ref,
        artifact_build_label="" if artifact_build is None else artifact_build.build_name,
        artifact_sets=artifact_sets,
        artifact_icon_refs=artifact_icon_refs,
        warnings=slot.warnings,
    )


def _chamber_details(
    chamber: HistoryAbyssChamberSnapshot,
    *,
    floor: int | None,
    bundle: HistorySnapshotBundle,
) -> HistorySnapshotChamberDetails:
    label = _chamber_label(chamber, floor=floor)
    factual = _chamber_result_summaries(
        chamber.side_results,
        result_type="Fact",
        value_getter=lambda item: item.factual_dps,
    )
    sim_by_ref = {
        summary.payload.get("sim_result_ref"): summary
        for summary in bundle.result_summaries
        if summary.result_type == "sim_dps" and summary.payload.get("sim_result_ref")
    }
    sim = tuple(
        _side_result_line(
            side_result,
            result_type="Sim",
            dps=sim_by_ref.get(side_result.sim_result_ref).dps
            if side_result.sim_result_ref in sim_by_ref
            else None,
        )
        for side_result in chamber.side_results
        if side_result.sim_result_ref
    )
    return HistorySnapshotChamberDetails(
        chamber_index=chamber.chamber_index,
        label=label,
        timing_summary=_timing_summary(chamber),
        factual_dps_summaries=factual,
        sim_dps_summaries=tuple(item for item in sim if item),
        enemy_hp_summaries=_enemy_hp_summaries(chamber, label=label),
        warnings=chamber.warnings,
    )


def _chamber_result_summaries(
    side_results: tuple[HistoryAbyssSideResultSnapshot, ...],
    *,
    result_type: str,
    value_getter,
) -> tuple[str, ...]:
    return tuple(
        line
        for line in (
            _side_result_line(item, result_type=result_type, dps=value_getter(item))
            for item in side_results
        )
        if line
    )


def _side_result_line(
    side_result: HistoryAbyssSideResultSnapshot,
    *,
    result_type: str,
    dps: float | int | None,
) -> str:
    if dps is None:
        return ""
    elapsed = (
        ""
        if side_result.elapsed_seconds is None
        else f", {int(side_result.elapsed_seconds)}s"
    )
    return f"S{int(side_result.side)} {result_type}: {_compact_number(float(dps))}{elapsed}"


def _timing_summary(chamber: HistoryAbyssChamberSnapshot) -> str:
    timer = chamber.timer
    if timer is None:
        return ""
    parts = []
    if timer.team1_elapsed_seconds is not None:
        parts.append(f"T1 {int(timer.team1_elapsed_seconds)}s")
    if timer.team2_elapsed_seconds is not None:
        parts.append(f"T2 {int(timer.team2_elapsed_seconds)}s")
    if timer.total_elapsed_seconds is not None:
        parts.append(f"Total {int(timer.total_elapsed_seconds)}s")
    return " | ".join(parts)


def _enemy_hp_summaries(
    chamber: HistoryAbyssChamberSnapshot,
    *,
    label: str,
) -> tuple[str, ...]:
    lines: list[str] = []
    for side in (1, 2):
        enemies = tuple(
            enemy for enemy in chamber.enemies if _optional_int(enemy.get("side")) == side
        )
        side_result = next(
            (item for item in chamber.side_results if int(item.side) == side),
            None,
        )
        enemy_text = _enemy_names_summary(enemies)
        hp = None if side_result is None else side_result.total_hp
        if hp is None:
            hp = _enemy_hp_total(enemies)
        hp_text = "" if hp is None else f" HP {_compact_number(float(hp))}"
        if enemy_text or hp_text:
            lines.append(f"{label} S{side}: {enemy_text or '-'}{hp_text}")
    return tuple(lines)


def _enemy_names_summary(enemies: tuple[Mapping[str, object], ...]) -> str:
    names: list[str] = []
    for enemy in enemies:
        name = _text(
            enemy.get("primary_display_name")
            or enemy.get("matched_nanoka_display_name")
            or enemy.get("name")
        )
        if not name:
            continue
        count = _optional_int(enemy.get("enemy_count"))
        suffix = f" x{count}" if count and count > 1 else ""
        item = f"{name}{suffix}"
        if item not in names:
            names.append(item)
    return ", ".join(names)


def _enemy_hp_total(enemies: tuple[Mapping[str, object], ...]) -> int | None:
    total = 0
    found = False
    for enemy in enemies:
        hp = _optional_int(enemy.get("hp_used"))
        if hp is None:
            continue
        found = True
        total += hp
    return total if found else None


def _result_summaries(
    bundle: HistorySnapshotBundle,
    *,
    result_type: str,
) -> tuple[str, ...]:
    lines: list[str] = []
    for summary in bundle.result_summaries:
        if summary.result_type != result_type:
            continue
        label = summary.label or result_type
        values: list[str] = []
        if summary.chamber_index is not None:
            values.append(f"C{int(summary.chamber_index)}")
        if summary.side is not None:
            values.append(f"S{int(summary.side)}")
        if summary.dps is not None:
            values.append(f"DPS {_compact_number(float(summary.dps))}")
        if summary.elapsed_seconds is not None:
            values.append(f"{float(summary.elapsed_seconds):.1f}s".replace(".0s", "s"))
        if summary.damage is not None:
            values.append(f"DMG {_compact_number(float(summary.damage))}")
        lines.append(f"{label}: {', '.join(values)}" if values else label)
    return tuple(lines)


def _bundle_warnings(bundle: HistorySnapshotBundle) -> list[str]:
    warnings: list[str] = [*bundle.warnings]
    if bundle.scenario is not None:
        warnings.extend(bundle.scenario.warnings)
        if bundle.scenario.abyss is not None:
            warnings.extend(bundle.scenario.abyss.warnings)
            for chamber in bundle.scenario.abyss.chambers:
                warnings.extend(chamber.warnings)
                for result in chamber.side_results:
                    warnings.extend(result.warnings)
        if bundle.scenario.dps_dummy is not None:
            warnings.extend(bundle.scenario.dps_dummy.warnings)
    for team in bundle.teams:
        warnings.extend(team.warnings)
        for slot in team.slots:
            warnings.extend(slot.warnings)
            if slot.artifact_build is not None:
                warnings.extend(slot.artifact_build.warnings)
    for summary in bundle.result_summaries:
        warnings.extend(summary.warnings)
    return _dedupe(warnings)


def _provenance_notes(provenance: Mapping[str, object]) -> tuple[str, ...]:
    notes: list[str] = []
    for key, value in sorted(provenance.items()):
        if value in ("", None, (), []):
            continue
        notes.append(f"{key}: {value}")
    return tuple(notes)


def _team_character_names(
    bundle: HistorySnapshotBundle,
) -> tuple[tuple[str, ...], ...]:
    teams: list[tuple[str, ...]] = []
    for team in bundle.teams:
        names: list[str] = []
        for slot in team.slots:
            name = "" if slot.character is None else slot.character.name
            names.append(name or "-")
        teams.append(tuple(names))
    return tuple(teams)


def _team_summary(team_names: tuple[tuple[str, ...], ...]) -> str:
    team_labels: list[str] = []
    for index, names in enumerate(team_names, start=1):
        compact_names = " / ".join(names) if names else "-"
        team_labels.append(f"T{index}: {compact_names}")
    return " | ".join(team_labels)


def _chamber_summary(chamber: HistoryAbyssChamberSnapshot, *, floor: int | None) -> str:
    label = _chamber_label(chamber, floor=floor)
    return f"{label} {_side_summary(chamber, 1)} | {_side_summary(chamber, 2)}"


def _chamber_label(chamber: HistoryAbyssChamberSnapshot, *, floor: int | None) -> str:
    return chamber.chamber_label or (
        f"{floor}-{chamber.chamber_index}" if floor else f"C{chamber.chamber_index}"
    )


def _side_summary(chamber: HistoryAbyssChamberSnapshot, side: int) -> str:
    result = next(
        (item for item in chamber.side_results if int(item.side) == int(side)),
        None,
    )
    seconds = None if result is None else result.elapsed_seconds
    if seconds is None and chamber.timer is not None:
        seconds = (
            chamber.timer.team1_elapsed_seconds
            if int(side) == 1
            else chamber.timer.team2_elapsed_seconds
        )
    time_text = "-" if seconds is None else f"{int(seconds)}s"
    dps = None if result is None else result.factual_dps
    dps_text = "-" if dps is None else _compact_number(float(dps))
    return f"{time_text}/{dps_text}"


def _warnings_count(bundle: HistorySnapshotBundle) -> int:
    warnings: list[str] = [*bundle.warnings]
    if bundle.scenario is not None:
        warnings.extend(bundle.scenario.warnings)
        if bundle.scenario.abyss is not None:
            warnings.extend(bundle.scenario.abyss.warnings)
            for chamber in bundle.scenario.abyss.chambers:
                warnings.extend(chamber.warnings)
                for result in chamber.side_results:
                    warnings.extend(result.warnings)
        if bundle.scenario.dps_dummy is not None:
            warnings.extend(bundle.scenario.dps_dummy.warnings)
    for team in bundle.teams:
        warnings.extend(team.warnings)
        for slot in team.slots:
            warnings.extend(slot.warnings)
            if slot.artifact_build is not None:
                warnings.extend(slot.artifact_build.warnings)
    for summary in bundle.result_summaries:
        warnings.extend(summary.warnings)
    return len({warning for warning in warnings if warning})


def _compact_number(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}m".replace(".0m", "m")
    if abs(value) >= 1_000:
        return f"{value / 1_000:.0f}k"
    return f"{value:.0f}"


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return result


def _abyss_group_label(summary: HistoryRunSummary, key: str) -> str:
    label = summary.period_start or key
    if summary.season_label:
        label = f"{label} | {summary.season_label}"
    if summary.floor is not None:
        label = f"{label} | F{int(summary.floor)}"
    return label


__all__ = [
    "HistoryAbyssPeriodSummary",
    "HistorySnapshotChamberDetails",
    "HistorySnapshotDetailsPayload",
    "HistorySnapshotSetDetails",
    "HistoryRunGroupSummary",
    "HistoryRunSummary",
    "HistorySnapshotSlotDetails",
    "HistorySnapshotSummaryListing",
    "HistorySnapshotTeamDetails",
    "history_snapshot_details_payload_from_bundle",
    "history_snapshot_details_payload_from_bundle_path",
    "load_history_snapshot_details_payload",
    "load_history_snapshot_summary_listing",
]
