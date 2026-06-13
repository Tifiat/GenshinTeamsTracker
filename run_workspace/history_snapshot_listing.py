"""Minimal read-model for immutable History Snapshot Bundles.

This is the first browsing layer over saved snapshot JSON. It intentionally
does not render export images, query live account data, or build full snapshot
detail payloads; UI callers get compact immutable summaries only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from run_workspace.history_snapshot import (
    HISTORY_RUN_TYPE_ABYSS,
    HISTORY_RUN_TYPE_DPS_DUMMY,
    HISTORY_SNAPSHOT_GROUP_DPS_DUMMY,
    HISTORY_UNKNOWN_ABYSS_PERIOD,
    HistoryAbyssChamberSnapshot,
    HistorySnapshotBundle,
    HistorySnapshotBundleReadError,
    HistorySnapshotBundleRecord,
    HistorySnapshotBundleStore,
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
class HistoryRunGroupSummary:
    run_type: str
    group_key: str
    group_label: str
    period_start: str = ""
    period_end: str = ""
    season_label: str = ""
    floor: int | None = None
    runs: tuple[HistoryRunSummary, ...] = ()


@dataclass(frozen=True, slots=True)
class HistorySnapshotSummaryListing:
    groups: tuple[HistoryRunGroupSummary, ...] = ()
    errors: tuple[HistorySnapshotBundleReadError, ...] = ()

    @property
    def run_count(self) -> int:
        return sum(len(group.runs) for group in self.groups)


def load_history_snapshot_summary_listing(root: str | Path) -> HistorySnapshotSummaryListing:
    store = HistorySnapshotBundleStore(root)
    listing = store.list_bundle_records()
    summaries = [_summary_from_record(store, record) for record in listing.records]
    return HistorySnapshotSummaryListing(
        groups=_group_summaries(summaries),
        errors=listing.errors,
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
    label = chamber.chamber_label or (
        f"{floor}-{chamber.chamber_index}" if floor else f"C{chamber.chamber_index}"
    )
    return f"{label} {_side_summary(chamber, 1)} | {_side_summary(chamber, 2)}"


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


def _abyss_group_label(summary: HistoryRunSummary, key: str) -> str:
    label = summary.period_start or key
    if summary.season_label:
        label = f"{label} | {summary.season_label}"
    if summary.floor is not None:
        label = f"{label} | F{int(summary.floor)}"
    return label


__all__ = [
    "HistoryRunGroupSummary",
    "HistoryRunSummary",
    "HistorySnapshotSummaryListing",
    "load_history_snapshot_summary_listing",
]
