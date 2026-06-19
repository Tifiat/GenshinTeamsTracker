"""Read-only visual catalog for the AppShell History Browser."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from run_workspace.abyss.source_data import AbyssFloorSourceData
from run_workspace.abyss.source_data_cache import list_cached_abyss_floor_source_data
from run_workspace.abyss.source_data_runtime import read_cached_hoyolab_abyss_period
from run_workspace.history_snapshot import (
    HISTORY_RUN_TYPE_ABYSS,
    HISTORY_RUN_TYPE_DPS_DUMMY,
    HISTORY_UNKNOWN_ABYSS_PERIOD,
    HistoryAbyssChamberSnapshot,
    HistorySnapshotBundle,
    HistorySnapshotBundleReadError,
    HistorySnapshotBundleStore,
)


HISTORY_MODE_ABYSS = HISTORY_RUN_TYPE_ABYSS
HISTORY_MODE_DPS_DUMMY = HISTORY_RUN_TYPE_DPS_DUMMY
HISTORY_MODE_PVP = "pvp"
HISTORY_MODES = (HISTORY_MODE_ABYSS, HISTORY_MODE_DPS_DUMMY, HISTORY_MODE_PVP)


@dataclass(frozen=True, slots=True)
class HistorySlotVisual:
    slot_index: int
    character_name: str = ""
    portrait_path: str = ""
    character_level: int | None = None
    constellation: int | None = None
    weapon_name: str = ""
    weapon_icon_path: str = ""
    weapon_refinement: int | None = None
    build_label: str = ""
    set_labels: tuple[str, ...] = ()
    set_icon_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoryTeamVisual:
    team_index: int
    slots: tuple[HistorySlotVisual, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoryChamberVisual:
    chamber_index: int
    side_times: tuple[int | None, int | None] = (None, None)
    factual_dps: tuple[int | None, int | None] = (None, None)
    sim_dps: tuple[int | None, int | None] = (None, None)


@dataclass(frozen=True, slots=True)
class HistoryRunVisual:
    bundle_id: str
    run_type: str
    created_at: str
    bundle_path: Path
    period_start: str = ""
    period_end: str = ""
    floor: int | None = None
    teams: tuple[HistoryTeamVisual, ...] = ()
    chambers: tuple[HistoryChamberVisual, ...] = ()
    target_label: str = ""
    target_setup: str = ""
    duration_seconds: float | None = None
    factual_dps: float | None = None
    sim_dps: float | None = None
    warnings_count: int = 0


@dataclass(frozen=True, slots=True)
class HistoryEnemyVisual:
    name: str
    icon_path: str = ""
    level: int | None = None
    count: int = 1
    wave: int = 1
    hp: int | None = None


@dataclass(frozen=True, slots=True)
class HistorySideVisual:
    chamber: int
    side: int
    total_hp: int | None = None
    enemies: tuple[HistoryEnemyVisual, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoryPeriodVisual:
    period_start: str
    period_end: str = ""
    floor: int | None = None
    runs: tuple[HistoryRunVisual, ...] = ()
    sides: tuple[HistorySideVisual, ...] = ()
    from_cache: bool = False


@dataclass(frozen=True, slots=True)
class HistoryBrowserCatalog:
    periods: tuple[HistoryPeriodVisual, ...] = ()
    dps_dummy_runs: tuple[HistoryRunVisual, ...] = ()
    current_period_start: str = ""
    errors: tuple[HistorySnapshotBundleReadError, ...] = ()


def load_history_browser_catalog(
    snapshot_root: str | Path,
    *,
    abyss_cache_dir: str | Path | None = None,
    current_period_path: str | Path | None = None,
) -> HistoryBrowserCatalog:
    """Merge immutable snapshots with the read-only Abyss cache catalog."""

    listing = HistorySnapshotBundleStore(snapshot_root).list_bundle_records()
    abyss_runs: dict[str, list[HistoryRunVisual]] = {}
    snapshot_bundles: dict[str, list[tuple[HistorySnapshotBundle, Path]]] = {}
    dps_runs: list[HistoryRunVisual] = []
    for record in listing.records:
        visual = _run_visual(record.bundle, record.path)
        if visual.run_type == HISTORY_RUN_TYPE_ABYSS:
            key = visual.period_start or HISTORY_UNKNOWN_ABYSS_PERIOD
            abyss_runs.setdefault(key, []).append(visual)
            snapshot_bundles.setdefault(key, []).append((record.bundle, record.path))
        elif visual.run_type == HISTORY_RUN_TYPE_DPS_DUMMY:
            dps_runs.append(visual)

    cached = {
        record.period_start: record
        for record in list_cached_abyss_floor_source_data(
            floor=12,
            cache_dir=abyss_cache_dir,
        )
    }
    keys = sorted(
        (set(cached) | set(abyss_runs)) - {HISTORY_UNKNOWN_ABYSS_PERIOD},
        reverse=True,
    )
    if HISTORY_UNKNOWN_ABYSS_PERIOD in abyss_runs:
        keys.append(HISTORY_UNKNOWN_ABYSS_PERIOD)

    periods: list[HistoryPeriodVisual] = []
    for key in keys:
        runs = tuple(
            sorted(
                abyss_runs.get(key, ()),
                key=lambda item: (item.created_at, item.bundle_id),
                reverse=True,
            )
        )
        cache_record = cached.get(key)
        if cache_record is not None:
            sides = _cache_sides(cache_record.data)
            period_end = cache_record.period_end or ""
            floor = cache_record.floor
        else:
            latest = sorted(
                snapshot_bundles.get(key, ()),
                key=lambda item: item[0].created_at,
                reverse=True,
            )
            sides = _snapshot_sides(*latest[0]) if latest else ()
            period_end = runs[0].period_end if runs else ""
            floor = runs[0].floor if runs else None
        periods.append(
            HistoryPeriodVisual(
                period_start=key,
                period_end=period_end,
                floor=floor,
                runs=runs,
                sides=sides,
                from_cache=cache_record is not None,
            )
        )

    current = read_cached_hoyolab_abyss_period(current_period_path)
    return HistoryBrowserCatalog(
        periods=tuple(periods),
        dps_dummy_runs=tuple(
            sorted(
                dps_runs,
                key=lambda item: (item.created_at, item.bundle_id),
                reverse=True,
            )
        ),
        current_period_start="" if current is None else current.start_date,
        errors=listing.errors,
    )


def _run_visual(bundle: HistorySnapshotBundle, path: Path) -> HistoryRunVisual:
    scenario = bundle.scenario
    abyss = None if scenario is None else scenario.abyss
    dummy = None if scenario is None else scenario.dps_dummy
    sim_values = [
        item.dps
        for item in bundle.result_summaries
        if item.result_type == "sim_dps" and item.dps is not None
    ]
    return HistoryRunVisual(
        bundle_id=bundle.bundle_id,
        run_type=bundle.run_type,
        created_at=bundle.created_at,
        bundle_path=path,
        period_start="" if abyss is None else abyss.period_start,
        period_end="" if abyss is None else abyss.period_end,
        floor=None if abyss is None else abyss.floor,
        teams=tuple(_team_visual(team, path.parent) for team in bundle.teams),
        chambers=()
        if abyss is None
        else tuple(_chamber_visual(item, bundle) for item in abyss.chambers),
        target_label="" if dummy is None else dummy.target_label,
        target_setup="" if dummy is None else dummy.result_status,
        duration_seconds=None if dummy is None else dummy.duration_seconds,
        factual_dps=None if dummy is None else dummy.factual_dps,
        sim_dps=sim_values[0] if sim_values else None,
        warnings_count=len(_bundle_warnings(bundle)),
    )


def _team_visual(team: Any, bundle_dir: Path) -> HistoryTeamVisual:
    slots: list[HistorySlotVisual] = []
    for slot in team.slots:
        character = slot.character
        weapon = slot.weapon
        build = slot.artifact_build
        bonuses = () if build is None else build.active_set_bonuses
        slots.append(
            HistorySlotVisual(
                slot_index=slot.slot_index,
                character_name="" if character is None else character.name,
                portrait_path=_bundle_asset_path(
                    bundle_dir,
                    "" if character is None else character.portrait_ref,
                ),
                character_level=None if character is None else character.level,
                constellation=None if character is None else character.constellation,
                weapon_name="" if weapon is None else weapon.name,
                weapon_icon_path=_bundle_asset_path(
                    bundle_dir,
                    "" if weapon is None else weapon.icon_ref,
                ),
                weapon_refinement=None if weapon is None else weapon.refinement,
                build_label="" if build is None else build.build_name,
                set_labels=tuple(
                    f"{item.set_name} {item.piece_count}pc" for item in bonuses
                ),
                set_icon_paths=tuple(
                    _bundle_asset_path(bundle_dir, item.icon_ref) for item in bonuses
                ),
            )
        )
    return HistoryTeamVisual(team_index=team.team_index, slots=tuple(slots))


def _chamber_visual(
    chamber: HistoryAbyssChamberSnapshot,
    bundle: HistorySnapshotBundle,
) -> HistoryChamberVisual:
    results = {int(item.side): item for item in chamber.side_results}
    sim_refs = {
        str(item.payload.get("sim_result_ref") or ""): item.dps
        for item in bundle.result_summaries
        if item.result_type == "sim_dps"
    }
    return HistoryChamberVisual(
        chamber_index=chamber.chamber_index,
        side_times=tuple(
            None
            if side not in results
            else results[side].elapsed_seconds
            for side in (1, 2)
        ),
        factual_dps=tuple(
            None if side not in results else results[side].factual_dps
            for side in (1, 2)
        ),
        sim_dps=tuple(
            None
            if side not in results
            else _optional_int(sim_refs.get(results[side].sim_result_ref))
            for side in (1, 2)
        ),
    )


def _cache_sides(data: AbyssFloorSourceData) -> tuple[HistorySideVisual, ...]:
    result: list[HistorySideVisual] = []
    for side in sorted(data.side_summaries, key=lambda item: (item.chamber, item.side)):
        enemies = tuple(
            HistoryEnemyVisual(
                name=row.primary_display_name,
                icon_path=row.cached_icon_path or "",
                level=row.display_level,
                count=max(1, int(row.enemy_count or 1)),
                wave=max(1, int(row.wave or 1)),
                hp=row.nanoka_hp,
            )
            for wave in side.waves
            for row in wave.enemies
        )
        total_hp = side.multi_target_hp
        if total_hp is None:
            values = [
                item.hp * item.count
                for item in enemies
                if item.hp is not None
            ]
            total_hp = sum(values) if values else None
        result.append(
            HistorySideVisual(
                chamber=side.chamber,
                side=side.side,
                total_hp=total_hp,
                enemies=enemies,
            )
        )
    return tuple(result)


def _snapshot_sides(
    bundle: HistorySnapshotBundle,
    path: Path,
) -> tuple[HistorySideVisual, ...]:
    abyss = None if bundle.scenario is None else bundle.scenario.abyss
    if abyss is None:
        return ()
    result: list[HistorySideVisual] = []
    for chamber in abyss.chambers:
        for side_number in (1, 2):
            enemies = tuple(
                _snapshot_enemy(item, path.parent)
                for item in chamber.enemies
                if _optional_int(item.get("side")) == side_number
            )
            side_result = next(
                (item for item in chamber.side_results if item.side == side_number),
                None,
            )
            total_hp = None if side_result is None else side_result.total_hp
            if total_hp is None:
                values = [
                    item.hp * item.count
                    for item in enemies
                    if item.hp is not None
                ]
                total_hp = sum(values) if values else None
            result.append(
                HistorySideVisual(
                    chamber=chamber.chamber_index,
                    side=side_number,
                    total_hp=total_hp,
                    enemies=enemies,
                )
            )
    return tuple(result)


def _snapshot_enemy(item: Mapping[str, Any], bundle_dir: Path) -> HistoryEnemyVisual:
    return HistoryEnemyVisual(
        name=str(
            item.get("primary_display_name")
            or item.get("matched_nanoka_display_name")
            or item.get("name")
            or ""
        ),
        icon_path=_bundle_asset_path(
            bundle_dir,
            str(item.get("cached_icon_path") or item.get("icon_ref") or ""),
        ),
        level=_optional_int(item.get("display_level") or item.get("level")),
        count=max(1, _optional_int(item.get("enemy_count")) or 1),
        wave=max(1, _optional_int(item.get("wave")) or 1),
        hp=_optional_int(item.get("hp_used") or item.get("nanoka_hp")),
    )


def _bundle_asset_path(bundle_dir: Path, value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text)
    if path.is_absolute():
        return ""
    try:
        resolved = (bundle_dir / path).resolve()
        resolved.relative_to(bundle_dir.resolve())
    except (OSError, ValueError):
        return ""
    return str(resolved) if resolved.is_file() else ""


def _bundle_warnings(bundle: HistorySnapshotBundle) -> set[str]:
    warnings = set(bundle.warnings)
    if bundle.scenario is not None:
        warnings.update(bundle.scenario.warnings)
        if bundle.scenario.abyss is not None:
            warnings.update(bundle.scenario.abyss.warnings)
            for chamber in bundle.scenario.abyss.chambers:
                warnings.update(chamber.warnings)
                for side in chamber.side_results:
                    warnings.update(side.warnings)
        if bundle.scenario.dps_dummy is not None:
            warnings.update(bundle.scenario.dps_dummy.warnings)
    for team in bundle.teams:
        warnings.update(team.warnings)
        for slot in team.slots:
            warnings.update(slot.warnings)
            if slot.artifact_build is not None:
                warnings.update(slot.artifact_build.warnings)
    for result in bundle.result_summaries:
        warnings.update(result.warnings)
    return {item for item in warnings if item}


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "HISTORY_MODE_ABYSS",
    "HISTORY_MODE_DPS_DUMMY",
    "HISTORY_MODE_PVP",
    "HISTORY_MODES",
    "HistoryBrowserCatalog",
    "HistoryChamberVisual",
    "HistoryEnemyVisual",
    "HistoryPeriodVisual",
    "HistoryRunVisual",
    "HistorySideVisual",
    "HistorySlotVisual",
    "HistoryTeamVisual",
    "load_history_browser_catalog",
]
