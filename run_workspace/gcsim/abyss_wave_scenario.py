"""Bridge typed Abyss source data into the current GTT wave payload prototype.

This module is intentionally backend-only and provisional. Abyss source-data
rows currently provide enemy waves, per-enemy HP, display levels, confidence,
and warnings, but they do not provide source-derived GCSIM spawn positions,
target radius, or resistance values. Payload generation therefore requires an
explicit fixture policy for those fields, and the audit result records that the
fixture fields are not product-correct Abyss data.
"""

from __future__ import annotations

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
FIXTURE_FIELDS_WARNING = "fixture_fields_used:radius_pos_resist_not_source_derived"
SOURCE_FIELDS_MISSING_WARNING = "abyss_source_data_lacks_radius_pos_resist"
MISSING_FIXTURE_POLICY_WARNING = "missing_fixture_policy:radius_pos_resist"


@dataclass(frozen=True, slots=True)
class ProvisionalTargetFixturePolicy:
    """Explicit non-source policy for current schema-v1 target fixture fields."""

    radius: float
    resist: float
    positions: tuple[tuple[float, float], ...]
    policy_name: str = "provisional_fixture"
    reuse_positions: bool = False

    def validate_for_max_wave_targets(self, max_wave_targets: int) -> tuple[str, ...]:
        warnings: list[str] = []
        if self.radius <= 0:
            warnings.append("fixture_policy_invalid:radius_must_be_positive")
        if not self.positions:
            warnings.append("fixture_policy_invalid:positions_required")
        for index, pos in enumerate(self.positions):
            if len(pos) != 2:
                warnings.append(f"fixture_policy_invalid:positions[{index}]_must_have_two_values")
                continue
            for coord_index, coord in enumerate(pos):
                if isinstance(coord, bool) or not isinstance(coord, (int, float)):
                    warnings.append(
                        "fixture_policy_invalid:"
                        f"positions[{index}][{coord_index}]_must_be_number"
                    )
        if (
            max_wave_targets > len(self.positions)
            and self.positions
            and not self.reuse_positions
        ):
            warnings.append(
                "fixture_policy_invalid:"
                f"positions_count={len(self.positions)}_less_than_max_wave_targets={max_wave_targets}"
            )
        if max_wave_targets > len(self.positions) and self.positions and self.reuse_positions:
            warnings.append("fixture_policy_reuses_positions")
        return tuple(warnings)

    def position_for_target(self, target_index: int) -> tuple[float, float]:
        if self.reuse_positions:
            position = self.positions[target_index % len(self.positions)]
        else:
            position = self.positions[target_index]
        return (float(position[0]), float(position[1]))


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
    fixture_fields_used: bool = False
    fixture_policy_name: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return (
            not self.missing_hp_rows
            and not self.missing_level_rows
            and not self.invalid_hp_rows
            and not self.invalid_level_rows
            and not self.warnings_blocking
        )

    @property
    def warnings_blocking(self) -> tuple[str, ...]:
        return tuple(
            warning
            for warning in self.warnings
            if warning.startswith("missing_fixture_policy:")
            or warning.startswith("fixture_policy_invalid:")
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
            "fixture_fields_used": self.fixture_fields_used,
            "fixture_policy_name": self.fixture_policy_name,
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
    fixture_policy: ProvisionalTargetFixturePolicy | None = None,
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
        fixture_policy=fixture_policy,
    )


def build_abyss_wave_scenario_payload(
    data: AbyssFloorSourceData,
    *,
    chamber: int,
    side: int,
    fixture_policy: ProvisionalTargetFixturePolicy | None = None,
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
        fixture_policy=fixture_policy,
    )
    if not audit.ready or fixture_policy is None:
        return AbyssWaveScenarioBuildResult(audit=audit)

    waves: list[dict[str, Any]] = []
    for wave in selected_side.waves:
        targets: list[dict[str, Any]] = []
        for row in wave.enemies:
            for _ in range(_normalized_enemy_count(row)):
                pos = fixture_policy.position_for_target(len(targets))
                targets.append(
                    {
                        "level": int(row.display_level or 0),
                        "hp": float(row.nanoka_hp or 0),
                        "radius": float(fixture_policy.radius),
                        "pos": [pos[0], pos[1]],
                        "resist": float(fixture_policy.resist),
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
    fixture_policy: ProvisionalTargetFixturePolicy | None,
) -> AbyssWaveScenarioAudit:
    missing_hp: list[str] = []
    missing_level: list[str] = []
    invalid_hp: list[str] = []
    invalid_level: list[str] = []
    warnings: list[str] = [SOURCE_FIELDS_MISSING_WARNING]
    target_count = 0
    max_wave_targets = 0
    for wave in selected_side.waves:
        wave_target_count = 0
        for row in wave.enemies:
            count = _normalized_enemy_count(row)
            wave_target_count += count
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
        max_wave_targets = max(max_wave_targets, wave_target_count)

    if not selected_side.waves:
        warnings.append("side_has_no_waves")
    if target_count <= 0:
        warnings.append("side_has_no_targets")
    if fixture_policy is None:
        warnings.append(MISSING_FIXTURE_POLICY_WARNING)
    else:
        warnings.append(FIXTURE_FIELDS_WARNING)
        warnings.extend(fixture_policy.validate_for_max_wave_targets(max_wave_targets))

    return AbyssWaveScenarioAudit(
        floor=data.floor,
        period_start=data.period.start_date,
        chamber=selected_side.chamber,
        side=selected_side.side,
        side_name=selected_side.side_name,
        wave_count=len(selected_side.waves),
        source_enemy_row_count=sum(len(wave.enemies) for wave in selected_side.waves),
        generated_target_count=target_count if fixture_policy is not None else 0,
        missing_hp_rows=tuple(missing_hp),
        missing_level_rows=tuple(missing_level),
        invalid_hp_rows=tuple(invalid_hp),
        invalid_level_rows=tuple(invalid_level),
        fixture_fields_used=fixture_policy is not None,
        fixture_policy_name="" if fixture_policy is None else fixture_policy.policy_name,
        warnings=tuple(warnings),
    )


def _normalized_enemy_count(row: AbyssEnemySourceRow) -> int:
    return max(0, int(row.enemy_count))


def _row_label(row: AbyssEnemySourceRow) -> str:
    return (
        f"floor={row.floor}:chamber={row.chamber}:side={row.side}:"
        f"wave={row.wave}:enemy={row.primary_display_name or row.nanoka_monster_id or 'unknown'}"
    )
