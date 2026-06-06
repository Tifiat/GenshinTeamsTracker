"""Bridge typed Abyss source data into the current GTT wave payload prototype.

This module is intentionally backend-only and provisional. Abyss source-data
rows currently provide enemy waves, per-enemy HP, display levels, confidence,
and warnings, but they do not provide GCSIM enemy type keys. Payload generation
therefore requires either an explicit source identity override mapping or an
optional GCSIM enemy type registry matcher. It does not use fuzzy/display-name
similarity as production truth.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from run_workspace.abyss.source_data import (
    AbyssChamberSideSourceData,
    AbyssEnemySourceRow,
    AbyssFloorSourceData,
)

from .enemy_type_registry import (
    GcsimEnemyNameCandidate,
    GcsimEnemyTypeRegistry,
    MATCH_METHOD_AMBIGUOUS,
    MATCH_METHOD_MANUAL_MAPPING,
    MATCH_METHOD_MISSING,
    MATCH_METHOD_SNAP_TITLE_CONTAINS_TARGET,
    MATCH_METHOD_SNAP_TITLE_FALLBACK,
)
from .snap_monster_titles import (
    SNAP_TITLE_SOURCE_KIND,
    SNAP_TITLE_STATUS_AMBIGUOUS,
    SNAP_TITLE_STATUS_MISSING,
    SnapMonsterTitleIndex,
)


GTT_WAVE_SCENARIO_SCHEMA_VERSION = 1
GTT_WAVE_SCENARIO_SPAWN_POLICY = "group_clear"
MISSING_ENEMY_TYPE_MAPPING_WARNING = "missing_enemy_type_mapping:abyss_enemy_identity_to_gcsim_type"
SOURCE_FIELDS_MISSING_WARNING = "abyss_source_data_lacks_gcsim_enemy_type"

IDENTITY_KIND_NANOKA_MONSTER_ID = "nanoka_monster_id"
IDENTITY_KIND_NANOKA_DISPLAY_NAME = "nanoka_display_name"
IDENTITY_KIND_FANDOM_PAGE_URL = "fandom_page_url"
IDENTITY_KIND_FANDOM_PAGE_TITLE = "fandom_page_title"
IDENTITY_KIND_FANDOM_DISPLAY_NAME = "fandom_display_name"

ACCEPTED_IDENTITY_KINDS = {
    IDENTITY_KIND_NANOKA_MONSTER_ID,
    IDENTITY_KIND_FANDOM_PAGE_URL,
    IDENTITY_KIND_FANDOM_PAGE_TITLE,
    IDENTITY_KIND_NANOKA_DISPLAY_NAME,
    IDENTITY_KIND_FANDOM_DISPLAY_NAME,
}


@dataclass(frozen=True, slots=True)
class AbyssEnemyIdentityCandidate:
    source_kind: str
    source_id: str
    source_name: str = ""

    def key(self) -> tuple[str, str]:
        return (self.source_kind, self.source_id)

    def to_dict(self) -> dict[str, str]:
        return {
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "source_name": self.source_name,
        }


@dataclass(frozen=True, slots=True)
class AbyssEnemyTypeMappingRecord:
    source_kind: str
    source_id: str
    gcsim_type: str
    source_name: str = ""
    notes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def key(self) -> tuple[str, str]:
        return (self.source_kind, self.source_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "gcsim_type": self.gcsim_type,
            "source_name": self.source_name,
            "notes": list(self.notes),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class AbyssEnemyTypeResolution:
    status: str
    candidates: tuple[AbyssEnemyIdentityCandidate, ...]
    gcsim_type: str = ""
    method: str = ""
    selected_identity: AbyssEnemyIdentityCandidate | None = None
    selected_record: AbyssEnemyTypeMappingRecord | None = None
    ambiguous_records: tuple[AbyssEnemyTypeMappingRecord, ...] = ()
    ambiguous_types: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.status == "resolved" and bool(self.gcsim_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "method": self.method,
            "gcsim_type": self.gcsim_type,
            "selected_identity": None
            if self.selected_identity is None
            else self.selected_identity.to_dict(),
            "selected_record": None
            if self.selected_record is None
            else self.selected_record.to_dict(),
            "ambiguous_records": [record.to_dict() for record in self.ambiguous_records],
            "ambiguous_types": list(self.ambiguous_types),
            "available_identities": [candidate.to_dict() for candidate in self.candidates],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True, init=False)
class AbyssEnemyTypeMapping:
    """Explicit Abyss enemy source identity -> GCSIM enemy type mapping."""

    records: tuple[AbyssEnemyTypeMappingRecord, ...] = ()
    mapping_name: str = "explicit_enemy_type_mapping"

    def __init__(
        self,
        records: tuple[AbyssEnemyTypeMappingRecord, ...] | list[AbyssEnemyTypeMappingRecord] = (),
        *,
        mapping_name: str = "explicit_enemy_type_mapping",
        types_by_nanoka_monster_id: Mapping[str, str] | None = None,
    ) -> None:
        normalized_records = list(records)
        if types_by_nanoka_monster_id:
            normalized_records.extend(
                AbyssEnemyTypeMappingRecord(
                    source_kind=IDENTITY_KIND_NANOKA_MONSTER_ID,
                    source_id=str(source_id).strip(),
                    gcsim_type=str(gcsim_type).strip(),
                )
                for source_id, gcsim_type in types_by_nanoka_monster_id.items()
                if str(source_id).strip() and str(gcsim_type).strip()
            )
        object.__setattr__(self, "records", tuple(normalized_records))
        object.__setattr__(self, "mapping_name", str(mapping_name or "explicit_enemy_type_mapping"))

    @property
    def types_by_nanoka_monster_id(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for record in self.records:
            if record.source_kind == IDENTITY_KIND_NANOKA_MONSTER_ID:
                result.setdefault(record.source_id, record.gcsim_type)
        return result

    def resolve_row(
        self,
        row: AbyssEnemySourceRow,
        *,
        enemy_type_registry: GcsimEnemyTypeRegistry | None = None,
        snap_title_index: SnapMonsterTitleIndex | None = None,
    ) -> AbyssEnemyTypeResolution:
        candidates = abyss_enemy_identity_candidates(row)
        records_by_key = _records_by_key(self.records)
        for candidate in _resolution_candidates(candidates):
            matches = records_by_key.get(candidate.key(), ())
            if not matches:
                continue
            if len(matches) > 1:
                return AbyssEnemyTypeResolution(
                    status="ambiguous_mapping",
                    candidates=candidates,
                    method=MATCH_METHOD_MANUAL_MAPPING,
                    selected_identity=candidate,
                    ambiguous_records=matches,
                    warnings=(f"ambiguous_mapping:{candidate.source_kind}:{candidate.source_id}",),
                )
            record = matches[0]
            return AbyssEnemyTypeResolution(
                status="resolved",
                candidates=candidates,
                gcsim_type=record.gcsim_type,
                method=MATCH_METHOD_MANUAL_MAPPING,
                selected_identity=candidate,
                selected_record=record,
                warnings=record.warnings,
            )
        if enemy_type_registry is not None:
            registry_match = enemy_type_registry.match_name_candidates(
                abyss_enemy_name_candidates(row)
            )
            if registry_match.ready and registry_match.selected_name is not None:
                return AbyssEnemyTypeResolution(
                    status="resolved",
                    candidates=candidates,
                    gcsim_type=registry_match.gcsim_type,
                    method=registry_match.method,
                    selected_identity=_identity_from_name_candidate(
                        registry_match.selected_name,
                        candidates,
                    ),
                    warnings=registry_match.warnings,
                )
            if registry_match.method == MATCH_METHOD_AMBIGUOUS:
                return AbyssEnemyTypeResolution(
                    status="ambiguous_mapping",
                    candidates=candidates,
                    method=MATCH_METHOD_AMBIGUOUS,
                    selected_identity=_identity_from_name_candidate(
                        registry_match.selected_name,
                        candidates,
                    ),
                    ambiguous_types=registry_match.ambiguous_types,
                    warnings=registry_match.warnings,
                )
            if registry_match.method == MATCH_METHOD_MISSING:
                snap_resolution = _snap_title_resolution(
                    row,
                    candidates,
                    enemy_type_registry=enemy_type_registry,
                    snap_title_index=snap_title_index,
                )
                if snap_resolution is not None:
                    return snap_resolution
                return AbyssEnemyTypeResolution(
                    status="missing_mapping",
                    candidates=candidates,
                    method=MATCH_METHOD_MISSING,
                    selected_identity=_identity_from_name_candidate(
                        registry_match.selected_name,
                        candidates,
                    ),
                    warnings=registry_match.warnings
                    or ("missing_mapping_for_available_identities",),
                )
        return AbyssEnemyTypeResolution(
            status="missing_mapping",
            candidates=candidates,
            method=MATCH_METHOD_MISSING,
            warnings=("missing_mapping_for_available_identities",),
        )

    def gcsim_type_for_row(
        self,
        row: AbyssEnemySourceRow,
        *,
        enemy_type_registry: GcsimEnemyTypeRegistry | None = None,
        snap_title_index: SnapMonsterTitleIndex | None = None,
    ) -> str | None:
        resolution = self.resolve_row(
            row,
            enemy_type_registry=enemy_type_registry,
            snap_title_index=snap_title_index,
        )
        return resolution.gcsim_type if resolution.ready else None


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
    ambiguous_type_mapping_rows: tuple[str, ...] = ()
    type_mapping_details: tuple[dict[str, Any], ...] = ()
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
            and not self.ambiguous_type_mapping_rows
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
            "ambiguous_type_mapping_rows": list(self.ambiguous_type_mapping_rows),
            "type_mapping_details": list(self.type_mapping_details),
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
    enemy_type_registry: GcsimEnemyTypeRegistry | None = None,
    snap_title_index: SnapMonsterTitleIndex | None = None,
    fact_dps_multi_target_enabled: bool = True,
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
        enemy_type_registry=enemy_type_registry,
        snap_title_index=snap_title_index,
        fact_dps_multi_target_enabled=fact_dps_multi_target_enabled,
    )


def build_abyss_wave_scenario_payload(
    data: AbyssFloorSourceData,
    *,
    chamber: int,
    side: int,
    enemy_type_mapping: AbyssEnemyTypeMapping | None = None,
    enemy_type_registry: GcsimEnemyTypeRegistry | None = None,
    snap_title_index: SnapMonsterTitleIndex | None = None,
    fact_dps_multi_target_enabled: bool = True,
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
        enemy_type_registry=enemy_type_registry,
        snap_title_index=snap_title_index,
        fact_dps_multi_target_enabled=fact_dps_multi_target_enabled,
    )
    if not audit.ready or (enemy_type_mapping is None and enemy_type_registry is None):
        return AbyssWaveScenarioBuildResult(audit=audit)

    resolver = enemy_type_mapping or AbyssEnemyTypeMapping()
    waves: list[dict[str, Any]] = []
    for wave in selected_side.waves:
        targets: list[dict[str, Any]] = []
        for row, count in _target_rows_for_wave(
            wave,
            fact_dps_multi_target_enabled=fact_dps_multi_target_enabled,
        ):
            for _ in range(count):
                resolution = resolver.resolve_row(
                    row,
                    enemy_type_registry=enemy_type_registry,
                    snap_title_index=snap_title_index,
                )
                if not resolution.ready:
                    continue
                targets.append(
                    {
                        "level": int(row.display_level or 0),
                        "type": resolution.gcsim_type,
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
    name = str(raw.get("mapping_name") or Path(path).name).strip()
    records: list[AbyssEnemyTypeMappingRecord] = []
    if "records" in raw:
        records_raw = raw.get("records")
        if not isinstance(records_raw, list):
            raise ValueError("records must be a JSON list")
        records.extend(_mapping_record_from_json(item) for item in records_raw)
    if "enemy_types_by_nanoka_monster_id" in raw or not records:
        mapping_raw = raw.get("enemy_types_by_nanoka_monster_id", raw)
        if not isinstance(mapping_raw, Mapping):
            raise ValueError("enemy_types_by_nanoka_monster_id must be a JSON object")
        for key, value in mapping_raw.items():
            if key in {"mapping_name", "records"}:
                continue
            source_id = str(key).strip()
            gcsim_type = str(value).strip()
            if source_id and gcsim_type:
                records.append(
                    AbyssEnemyTypeMappingRecord(
                        source_kind=IDENTITY_KIND_NANOKA_MONSTER_ID,
                        source_id=source_id,
                        gcsim_type=gcsim_type,
                    )
                )
    return AbyssEnemyTypeMapping(
        records=tuple(records),
        mapping_name=name or "explicit_enemy_type_mapping",
    )


def abyss_enemy_identity_candidates(
    row: AbyssEnemySourceRow,
) -> tuple[AbyssEnemyIdentityCandidate, ...]:
    candidates: list[AbyssEnemyIdentityCandidate] = []
    _append_identity_candidate(
        candidates,
        IDENTITY_KIND_NANOKA_MONSTER_ID,
        row.nanoka_monster_id,
        row.matched_nanoka_display_name or row.primary_display_name,
    )
    _append_identity_candidate(
        candidates,
        IDENTITY_KIND_NANOKA_DISPLAY_NAME,
        row.matched_nanoka_display_name,
        row.matched_nanoka_display_name,
    )
    _append_identity_candidate(
        candidates,
        IDENTITY_KIND_FANDOM_PAGE_URL,
        row.fandom_enemy_page_url,
        row.primary_display_name,
    )
    _append_identity_candidate(
        candidates,
        IDENTITY_KIND_FANDOM_PAGE_TITLE,
        _fandom_page_title(row.fandom_enemy_page_url),
        row.primary_display_name,
    )
    _append_identity_candidate(
        candidates,
        IDENTITY_KIND_FANDOM_DISPLAY_NAME,
        row.primary_display_name,
        row.primary_display_name,
    )
    return tuple(candidates)


def abyss_enemy_name_candidates(
    row: AbyssEnemySourceRow,
) -> tuple[GcsimEnemyNameCandidate, ...]:
    identity_candidates = abyss_enemy_identity_candidates(row)
    result: list[GcsimEnemyNameCandidate] = []
    for candidate in identity_candidates:
        if candidate.source_kind not in {
            IDENTITY_KIND_NANOKA_DISPLAY_NAME,
            IDENTITY_KIND_FANDOM_PAGE_TITLE,
            IDENTITY_KIND_FANDOM_DISPLAY_NAME,
        }:
            continue
        result.append(
            GcsimEnemyNameCandidate(
                source_kind=candidate.source_kind,
                source_name=candidate.source_id,
            )
        )
    return tuple(result)


def _resolution_candidates(
    candidates: tuple[AbyssEnemyIdentityCandidate, ...],
) -> tuple[AbyssEnemyIdentityCandidate, ...]:
    priority = {
        IDENTITY_KIND_NANOKA_MONSTER_ID: 0,
        IDENTITY_KIND_FANDOM_PAGE_URL: 1,
        IDENTITY_KIND_FANDOM_PAGE_TITLE: 2,
        IDENTITY_KIND_NANOKA_DISPLAY_NAME: 3,
        IDENTITY_KIND_FANDOM_DISPLAY_NAME: 4,
    }
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: priority.get(candidate.source_kind, len(priority)),
        )
    )


def _append_identity_candidate(
    candidates: list[AbyssEnemyIdentityCandidate],
    source_kind: str,
    source_id: str | None,
    source_name: str | None,
) -> None:
    normalized_source_id = str(source_id or "").strip()
    if not normalized_source_id:
        return
    candidate = AbyssEnemyIdentityCandidate(
        source_kind=source_kind,
        source_id=normalized_source_id,
        source_name=str(source_name or "").strip(),
    )
    if candidate.key() not in {existing.key() for existing in candidates}:
        candidates.append(candidate)


def _fandom_page_title(url: str | None) -> str | None:
    if not url:
        return None
    path = urlparse(str(url)).path.rstrip("/")
    if not path:
        return None
    title = unquote(path.rsplit("/", 1)[-1]).replace("_", " ").strip()
    return title or None


def _mapping_record_from_json(raw: Any) -> AbyssEnemyTypeMappingRecord:
    if not isinstance(raw, Mapping):
        raise ValueError("mapping records must be JSON objects")
    source_kind = str(raw.get("source_kind") or "").strip()
    source_id = str(raw.get("source_id") or "").strip()
    gcsim_type = str(raw.get("gcsim_type") or "").strip()
    if not source_kind:
        raise ValueError("mapping record source_kind is required")
    if source_kind not in ACCEPTED_IDENTITY_KINDS:
        raise ValueError(f"unsupported mapping record source_kind: {source_kind}")
    if not source_id:
        raise ValueError("mapping record source_id is required")
    if not gcsim_type:
        raise ValueError("mapping record gcsim_type is required")
    return AbyssEnemyTypeMappingRecord(
        source_kind=source_kind,
        source_id=source_id,
        gcsim_type=gcsim_type,
        source_name=str(raw.get("source_name") or "").strip(),
        notes=_tuple_of_strings(raw.get("notes")),
        warnings=_tuple_of_strings(raw.get("warnings")),
    )


def _records_by_key(
    records: tuple[AbyssEnemyTypeMappingRecord, ...],
) -> dict[tuple[str, str], tuple[AbyssEnemyTypeMappingRecord, ...]]:
    grouped: dict[tuple[str, str], list[AbyssEnemyTypeMappingRecord]] = {}
    for record in records:
        if not record.source_kind or not record.source_id or not record.gcsim_type:
            continue
        grouped.setdefault(record.key(), []).append(record)
    return {key: tuple(values) for key, values in grouped.items()}


def _tuple_of_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return (str(value),)


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
    enemy_type_registry: GcsimEnemyTypeRegistry | None,
    snap_title_index: SnapMonsterTitleIndex | None,
    fact_dps_multi_target_enabled: bool,
) -> AbyssWaveScenarioAudit:
    missing_hp: list[str] = []
    missing_level: list[str] = []
    invalid_hp: list[str] = []
    invalid_level: list[str] = []
    missing_type_mapping: list[str] = []
    ambiguous_type_mapping: list[str] = []
    type_mapping_details: list[dict[str, Any]] = []
    warnings: list[str] = [SOURCE_FIELDS_MISSING_WARNING]
    target_count = 0
    for wave in selected_side.waves:
        for row, count in _target_rows_for_wave(
            wave,
            fact_dps_multi_target_enabled=fact_dps_multi_target_enabled,
        ):
            target_count += count
            label = _row_label(row)
            resolver = enemy_type_mapping or (
                AbyssEnemyTypeMapping() if enemy_type_registry is not None else None
            )
            resolution = None if resolver is None else resolver.resolve_row(
                row,
                enemy_type_registry=enemy_type_registry,
                snap_title_index=snap_title_index,
            )
            if row.nanoka_hp is None:
                missing_hp.append(label)
            elif row.nanoka_hp <= 0:
                invalid_hp.append(label)
            if row.display_level is None:
                missing_level.append(label)
            elif row.display_level < 1 or row.display_level > 100:
                invalid_level.append(label)
            if count > 0:
                if resolution is None:
                    missing_type_mapping.append(label)
                    type_mapping_details.append(
                        _type_mapping_detail(label, row, None)
                    )
                elif resolution.status == "missing_mapping":
                    missing_type_mapping.append(label)
                    type_mapping_details.append(
                        _type_mapping_detail(label, row, resolution)
                    )
                elif resolution.status == "ambiguous_mapping":
                    ambiguous_type_mapping.append(label)
                    type_mapping_details.append(
                        _type_mapping_detail(label, row, resolution)
                    )
                else:
                    type_mapping_details.append(
                        _type_mapping_detail(label, row, resolution)
                    )

    if not selected_side.waves:
        warnings.append("side_has_no_waves")
    if target_count <= 0:
        warnings.append("side_has_no_targets")
    if enemy_type_mapping is None and enemy_type_registry is None:
        warnings.append(MISSING_ENEMY_TYPE_MAPPING_WARNING)
    mapping_name = "" if enemy_type_mapping is None else enemy_type_mapping.mapping_name
    if enemy_type_registry is not None:
        mapping_name = mapping_name or "gcsim_enemy_type_registry"

    return AbyssWaveScenarioAudit(
        floor=data.floor,
        period_start=data.period.start_date,
        chamber=selected_side.chamber,
        side=selected_side.side,
        side_name=selected_side.side_name,
        wave_count=len(selected_side.waves),
        source_enemy_row_count=sum(len(wave.enemies) for wave in selected_side.waves),
        generated_target_count=target_count if mapping_name else 0,
        missing_hp_rows=tuple(missing_hp),
        missing_level_rows=tuple(missing_level),
        invalid_hp_rows=tuple(invalid_hp),
        invalid_level_rows=tuple(invalid_level),
        missing_type_mapping_rows=tuple(missing_type_mapping),
        ambiguous_type_mapping_rows=tuple(ambiguous_type_mapping),
        type_mapping_details=tuple(type_mapping_details),
        enemy_type_mapping_name=mapping_name,
        warnings=tuple(warnings),
    )


def _normalized_enemy_count(row: AbyssEnemySourceRow) -> int:
    return max(0, int(row.enemy_count))


def _target_rows_for_wave(
    wave: Any,
    *,
    fact_dps_multi_target_enabled: bool,
) -> tuple[tuple[AbyssEnemySourceRow, int], ...]:
    if fact_dps_multi_target_enabled:
        return tuple((row, _normalized_enemy_count(row)) for row in wave.enemies)
    selected_name = str(wave.selected_solo_enemy_name or "").strip()
    if not selected_name:
        return ()
    for row in wave.enemies:
        if row.primary_display_name == selected_name:
            return ((row, 1),)
    return ()


def _snap_title_resolution(
    row: AbyssEnemySourceRow,
    candidates: tuple[AbyssEnemyIdentityCandidate, ...],
    *,
    enemy_type_registry: GcsimEnemyTypeRegistry,
    snap_title_index: SnapMonsterTitleIndex | None,
) -> AbyssEnemyTypeResolution | None:
    if snap_title_index is None:
        return None
    lookup = snap_title_index.title_candidates_for_names(abyss_enemy_name_candidates(row))
    if lookup.status == SNAP_TITLE_STATUS_MISSING:
        return AbyssEnemyTypeResolution(
            status="missing_mapping",
            candidates=candidates,
            method=MATCH_METHOD_MISSING,
            warnings=("gcsim_enemy_type_match_missing",) + lookup.warnings,
        )
    if lookup.status == SNAP_TITLE_STATUS_AMBIGUOUS:
        return AbyssEnemyTypeResolution(
            status="ambiguous_mapping",
            candidates=candidates,
            method=MATCH_METHOD_SNAP_TITLE_FALLBACK,
            selected_identity=_snap_title_identity(lookup.source_name),
            ambiguous_types=tuple(
                sorted({candidate.normalized_title for candidate in lookup.candidates})
            ),
            warnings=lookup.warnings,
        )

    title_candidates = tuple(
        candidate.to_name_candidate() for candidate in lookup.candidates
    )
    registry_match = enemy_type_registry.match_name_candidates(title_candidates)
    selected_identity = _identity_from_name_candidate(
        registry_match.selected_name,
        candidates,
    )
    if registry_match.ready and registry_match.selected_name is not None:
        return AbyssEnemyTypeResolution(
            status="resolved",
            candidates=candidates,
            gcsim_type=registry_match.gcsim_type,
            method=MATCH_METHOD_SNAP_TITLE_FALLBACK,
            selected_identity=selected_identity,
            warnings=lookup.warnings + registry_match.warnings,
        )
    if registry_match.method == MATCH_METHOD_AMBIGUOUS:
        return AbyssEnemyTypeResolution(
            status="ambiguous_mapping",
            candidates=candidates,
            method=MATCH_METHOD_SNAP_TITLE_FALLBACK,
            selected_identity=selected_identity,
            ambiguous_types=registry_match.ambiguous_types,
            warnings=lookup.warnings + registry_match.warnings,
        )
    contains_resolution = _snap_title_contains_target_resolution(
        lookup,
        candidates,
        enemy_type_registry=enemy_type_registry,
        selected_identity=selected_identity,
    )
    if contains_resolution is not None:
        return contains_resolution
    missing_title = (
        lookup.candidates[0].normalized_title if lookup.candidates else "unknown"
    )
    return AbyssEnemyTypeResolution(
        status="missing_mapping",
        candidates=candidates,
        method=MATCH_METHOD_SNAP_TITLE_FALLBACK,
        selected_identity=selected_identity or _snap_title_identity(lookup.source_name),
        warnings=lookup.warnings
        + registry_match.warnings
        + (f"snap_title_registry_match_missing:{missing_title}",),
    )


def _snap_title_contains_target_resolution(
    lookup: Any,
    candidates: tuple[AbyssEnemyIdentityCandidate, ...],
    *,
    enemy_type_registry: GcsimEnemyTypeRegistry,
    selected_identity: AbyssEnemyIdentityCandidate | None,
) -> AbyssEnemyTypeResolution | None:
    if not lookup.candidates:
        return None
    snap_title = lookup.candidates[0].normalized_title
    if not snap_title:
        return None
    matches = tuple(
        sorted(
            target_type
            for target_type in enemy_type_registry.target_types
            if snap_title in target_type
        )
    )
    if not matches:
        return None
    identity = selected_identity or _snap_title_identity(lookup.candidates[0].title)
    if len(matches) > 1:
        return AbyssEnemyTypeResolution(
            status="ambiguous_mapping",
            candidates=candidates,
            method=MATCH_METHOD_SNAP_TITLE_CONTAINS_TARGET,
            selected_identity=identity,
            ambiguous_types=matches,
            warnings=lookup.warnings
            + (f"snap_title_contains_target_ambiguous:{snap_title}",),
        )
    return AbyssEnemyTypeResolution(
        status="resolved",
        candidates=candidates,
        gcsim_type=matches[0],
        method=MATCH_METHOD_SNAP_TITLE_CONTAINS_TARGET,
        selected_identity=identity,
        warnings=lookup.warnings
        + (f"snap_title_contains_target:{snap_title}->{matches[0]}",),
    )


def _type_mapping_detail(
    label: str,
    row: AbyssEnemySourceRow,
    resolution: AbyssEnemyTypeResolution | None,
) -> dict[str, Any]:
    if resolution is None:
        candidates = abyss_enemy_identity_candidates(row)
        return {
            "row": label,
            "status": "missing_mapping",
            "hp_source": row.hp_source,
            "gcsim_type": "",
            "selected_identity": None,
            "available_identities": [candidate.to_dict() for candidate in candidates],
            "ambiguous_records": [],
            "warnings": [MISSING_ENEMY_TYPE_MAPPING_WARNING],
        }
    data = resolution.to_dict()
    data.update(
        {
            "row": label,
            "hp_source": row.hp_source,
        }
    )
    return data


def _identity_from_name_candidate(
    name_candidate: GcsimEnemyNameCandidate | None,
    identity_candidates: tuple[AbyssEnemyIdentityCandidate, ...],
) -> AbyssEnemyIdentityCandidate | None:
    if name_candidate is None:
        return None
    for candidate in identity_candidates:
        if (
            candidate.source_kind == name_candidate.source_kind
            and candidate.source_id == name_candidate.source_name
        ):
            return candidate
    return AbyssEnemyIdentityCandidate(
        source_kind=name_candidate.source_kind,
        source_id=name_candidate.source_name,
        source_name=name_candidate.source_name,
    )


def _snap_title_identity(source_name: str) -> AbyssEnemyIdentityCandidate:
    return AbyssEnemyIdentityCandidate(
        source_kind=SNAP_TITLE_SOURCE_KIND,
        source_id=str(source_name or ""),
        source_name=str(source_name or ""),
    )


def _row_label(row: AbyssEnemySourceRow) -> str:
    return (
        f"floor={row.floor}:chamber={row.chamber}:side={row.side}:"
        f"wave={row.wave}:enemy={row.primary_display_name or row.nanoka_monster_id or 'unknown'}"
    )
