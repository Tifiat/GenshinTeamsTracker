"""Bridge typed Abyss source data into the current GTT wave payload prototype.

This module is intentionally backend-only and provisional. Abyss source-data
rows currently provide enemy waves, per-enemy HP, display levels, confidence,
and warnings, but they do not provide GCSIM enemy type keys. Payload generation
therefore requires an explicit source-id -> GCSIM enemy type mapping. It does
not infer GCSIM types from localized display names.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from run_workspace.abyss.source_data import (
    AbyssChamberSideSourceData,
    AbyssEnemySourceRow,
    AbyssFloorSourceData,
)


GTT_WAVE_SCENARIO_SCHEMA_VERSION = 1
GTT_WAVE_SCENARIO_SPAWN_POLICY = "group_clear"
MISSING_ENEMY_TYPE_MAPPING_WARNING = "missing_enemy_type_mapping:nanoka_monster_id_to_gcsim_type"
SOURCE_FIELDS_MISSING_WARNING = "abyss_source_data_lacks_gcsim_enemy_type"


@dataclass(frozen=True, slots=True)
class AbyssEnemyTypeMapping:
    """Explicit source-id -> GCSIM enemy type mapping for scenario payloads."""

    types_by_nanoka_monster_id: Mapping[str, str]
    mapping_name: str = "explicit_enemy_type_mapping"

    def gcsim_type_for_row(self, row: AbyssEnemySourceRow) -> str | None:
        source_id = (row.nanoka_monster_id or "").strip()
        if not source_id:
            return None
        value = self.types_by_nanoka_monster_id.get(source_id)
        if value is None:
            return None
        value = str(value).strip()
        return value or None


@dataclass(frozen=True, slots=True)
class AbyssWaveScenarioAudit:
    floor: int
    period_start: str
    chamber: int
    side: int
    side_name: str = ""
    wave_count: int = 0
    source_enemy_row_count: int = 0
    generated_target_count: int = 0
    missing_hp_rows: tuple[str, ...] = ()
    missing_level_rows: tuple[str, ...] = ()
    invalid_hp_rows: tuple[str, ...] = ()
    invalid_level_rows: tuple[str, ...] = ()
    missing_type_mapping_rows: tuple[str, ...] = ()
    enemy_type_mapping_name: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return (
            not self.missing_hp_rows
            and not self.missing_level_rows
            and not self.invalid_hp_rows
            and not self.invalid_level_rows
            and not self.missing_type_mapping_rows
            and not self.warnings_blocking
        )

    @property
    def warnings_blocking(self) -> tuple[str, ...]:
        return tuple(
            warning
            for warning in self.warnings
            if warning.startswith("missing_enemy_type_mapping:")
            or warning.startswith("side_not_found:")
            or warning == "side_has_no_waves"
            or warning == "side_has_no_targets"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "floor": self.floor,
            "period_start": self.period_start,
            "chamber": self.chamber,
            "side": self.side,
            "side_name": self.side_name,
            "wave_count": self.wave_count,
            "source_enemy_row_count": self.source_enemy_row_count,
            "generated_target_count": self.generated_target_count,
            "missing_hp_rows": list(self.missing_hp_rows),
            "missing_level_rows": list(self.missing_level_rows),
            "invalid_hp_rows": list(self.invalid_hp_rows),
            "invalid_level_rows": list(self.invalid_level_rows),
            "missing_type_mapping_rows": list(self.missing_type_mapping_rows),
            "enemy_type_mapping_name": self.enemy_type_mapping_name,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class AbyssWaveScenarioBuildResult:
    audit: AbyssWaveScenarioAudit
    payload: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        return self.payload is not None and self.audit.ready

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "audit": self.audit.to_dict(),
            "payload": self.payload,
        }


def audit_abyss_wave_scenario(
    data: AbyssFloorSourceData,
    *,
    chamber: int,
    side: int,
    enemy_type_mapping: AbyssEnemyTypeMapping | None = None,
) -> AbyssWaveScenarioAudit:
    selected_side = _select_side(data, chamber=chamber, side=side)
    if selected_side is None:
        return AbyssWaveScenarioAudit(
            floor=data.floor,
            period_start=data.period.start_date,
            chamber=chamber,
            side=side,
            warnings=(f"side_not_found:chamber={chamber}:side={side}",),
        )
    return _audit_selected_side(
        data,
        selected_side,
        enemy_type_mapping=enemy_type_mapping,
    )


def build_abyss_wave_scenario_payload(
    data: AbyssFloorSourceData,
    *,
    chamber: int,
    side: int,
    enemy_type_mapping: AbyssEnemyTypeMapping | None = None,
) -> AbyssWaveScenarioBuildResult:
    selected_side = _select_side(data, chamber=chamber, side=side)
    if selected_side is None:
        audit = AbyssWaveScenarioAudit(
            floor=data.floor,
            period_start=data.period.start_date,
            chamber=chamber,
            side=side,
            warnings=(f"side_not_found:chamber={chamber}:side={side}",),
        )
        return AbyssWaveScenarioBuildResult(audit=audit)

    audit = _audit_selected_side(
        data,
        selected_side,
        enemy_type_mapping=enemy_type_mapping,
    )
    if not audit.ready or enemy_type_mapping is None:
        return AbyssWaveScenarioBuildResult(audit=audit)

    waves: list[dict[str, Any]] = []
    for wave in selected_side.waves:
        targets: list[dict[str, Any]] = []
        for row in wave.enemies:
            for _ in range(_normalized_enemy_count(row)):
                gcsim_type = enemy_type_mapping.gcsim_type_for_row(row)
                if not gcsim_type:
                    continue
                targets.append(
                    {
                        "level": int(row.display_level or 0),
                        "type": gcsim_type,
                        "hp": float(row.nanoka_hp or 0),
                    }
                )
        waves.append({"targets": targets})

    return AbyssWaveScenarioBuildResult(
        audit=audit,
        payload={
            "schema_version": GTT_WAVE_SCENARIO_SCHEMA_VERSION,
            "spawn_policy": GTT_WAVE_SCENARIO_SPAWN_POLICY,
            "waves": waves,
        },
    )


def write_abyss_wave_scenario_payload(payload: dict[str, Any], path: str | Path) -> Path:
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target_path


def load_enemy_type_mapping_from_json(path: str | Path) -> AbyssEnemyTypeMapping:
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(raw, Mapping):
        raise ValueError("enemy type mapping must be a JSON object")
    mapping_raw = raw.get("enemy_types_by_nanoka_monster_id", raw)
    if not isinstance(mapping_raw, Mapping):
        raise ValueError("enemy_types_by_nanoka_monster_id must be a JSON object")
    mapping: dict[str, str] = {}
    for key, value in mapping_raw.items():
        source_id = str(key).strip()
        gcsim_type = str(value).strip()
        if source_id and gcsim_type:
            mapping[source_id] = gcsim_type
    name = str(raw.get("mapping_name") or Path(path).name).strip()
    return AbyssEnemyTypeMapping(
        types_by_nanoka_monster_id=mapping,
        mapping_name=name or "explicit_enemy_type_mapping",
    )


def _select_side(
    data: AbyssFloorSourceData,
    *,
    chamber: int,
    side: int,
) -> AbyssChamberSideSourceData | None:
    try:
        return data.side_summary(chamber, side)
    except ValueError:
        return None


def _audit_selected_side(
    data: AbyssFloorSourceData,
    selected_side: AbyssChamberSideSourceData,
    *,
    enemy_type_mapping: AbyssEnemyTypeMapping | None,
) -> AbyssWaveScenarioAudit:
    missing_hp: list[str] = []
    missing_level: list[str] = []
    invalid_hp: list[str] = []
    invalid_level: list[str] = []
    missing_type_mapping: list[str] = []
    warnings: list[str] = [SOURCE_FIELDS_MISSING_WARNING]
    target_count = 0
    for wave in selected_side.waves:
        for row in wave.enemies:
            count = _normalized_enemy_count(row)
            target_count += count
            label = _row_label(row)
            if row.nanoka_hp is None:
                missing_hp.append(label)
            elif row.nanoka_hp <= 0:
                invalid_hp.append(label)
            if row.display_level is None:
                missing_level.append(label)
            elif row.display_level < 1 or row.display_level > 100:
                invalid_level.append(label)
            if count > 0 and (
                enemy_type_mapping is None
                or enemy_type_mapping.gcsim_type_for_row(row) is None
            ):
                missing_type_mapping.append(label)

    if not selected_side.waves:
        warnings.append("side_has_no_waves")
    if target_count <= 0:
        warnings.append("side_has_no_targets")
    if enemy_type_mapping is None:
        warnings.append(MISSING_ENEMY_TYPE_MAPPING_WARNING)

    return AbyssWaveScenarioAudit(
        floor=data.floor,
        period_start=data.period.start_date,
        chamber=selected_side.chamber,
        side=selected_side.side,
        side_name=selected_side.side_name,
        wave_count=len(selected_side.waves),
        source_enemy_row_count=sum(len(wave.enemies) for wave in selected_side.waves),
        generated_target_count=target_count if enemy_type_mapping is not None else 0,
        missing_hp_rows=tuple(missing_hp),
        missing_level_rows=tuple(missing_level),
        invalid_hp_rows=tuple(invalid_hp),
        invalid_level_rows=tuple(invalid_level),
        missing_type_mapping_rows=tuple(missing_type_mapping),
        enemy_type_mapping_name="" if enemy_type_mapping is None else enemy_type_mapping.mapping_name,
        warnings=tuple(warnings),
    )


def _normalized_enemy_count(row: AbyssEnemySourceRow) -> int:
    return max(0, int(row.enemy_count))


def _row_label(row: AbyssEnemySourceRow) -> str:
    return (
        f"floor={row.floor}:chamber={row.chamber}:side={row.side}:"
        f"wave={row.wave}:enemy={row.primary_display_name or row.nanoka_monster_id or 'unknown'}"
    )
