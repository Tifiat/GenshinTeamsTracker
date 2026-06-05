"""Explicit GCSIM key mapping records and reports.

This module is a backend-only boundary for future config generation. It does
not infer GCSIM keys from localized display names or normalized names. Until a
reliable committed production mapping source exists, callers should provide
explicit curated/test/dev seed records and treat missing records as not ready.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from run_workspace.gcsim.config_readiness import GcsimMappingRef


ENTITY_CHARACTER = "character"
ENTITY_WEAPON = "weapon"
ENTITY_ARTIFACT_SET = "artifact_set"
ENTITY_TYPES = (ENTITY_CHARACTER, ENTITY_WEAPON, ENTITY_ARTIFACT_SET)

STATUS_READY = "ready"
STATUS_MISSING = "missing"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_UNSUPPORTED_TRAVELER = "unsupported_traveler"
STATUS_DISPLAY_NAME_ONLY_REJECTED = "display_name_only_rejected"
STATUSES = (
    STATUS_READY,
    STATUS_MISSING,
    STATUS_AMBIGUOUS,
    STATUS_UNSUPPORTED_TRAVELER,
    STATUS_DISPLAY_NAME_ONLY_REJECTED,
)

SCHEMA_VERSION = 1
SEED_KIND = "gcsim_key_mapping_seed_v1"

SOURCE_KIND_CURATED = "curated"
SOURCE_KIND_CURATED_TEST_FIXTURE = "curated_test_fixture"
SOURCE_KIND_DEV_FIXTURE = "dev_fixture"
SOURCE_KIND_TEST_FIXTURE = "test_fixture"

DISPLAY_NAME_SOURCE_KINDS = {
    "display_name",
    "localized_display_name",
    "name",
    "normalized_name",
    "normalized_name_guess",
    "guessed_normalized_name",
    "auto_normalized_name",
}

WARNING_DISPLAY_NAME_SOURCE_REJECTED = "display_name_source_rejected"
WARNING_TRAVELER_DEFERRED = "traveler_variant_selection_deferred"
WARNING_MAPPING_KEY_MISSING = "gcsim_key_missing"
WARNING_PROJECT_ID_MISSING = "project_id_missing"
WARNING_SOURCE_KIND_MISSING = "source_kind_missing"
WARNING_SOURCE_NAME_MISSING = "source_name_missing"
WARNING_UNKNOWN_ENTITY_TYPE = "unknown_entity_type"
WARNING_AMBIGUOUS_MAPPING = "ambiguous_gcsim_mapping"
WARNING_PRODUCTION_MAPPING_DATA_MISSING = "production_mapping_data_missing"

TRAVELER_PROJECT_CHARACTER_IDS = {"10000007"}


@dataclass(frozen=True, slots=True)
class GcsimKeyMappingRecord:
    entity_type: str
    project_id: str = ""
    canonical_name: str = ""
    gcsim_key: str = ""
    source_kind: str = ""
    source_name: str = ""
    status: str = STATUS_MISSING
    warnings: tuple[str, ...] = ()
    candidates: tuple[str, ...] = ()

    def normalized(self) -> "GcsimKeyMappingRecord":
        return normalize_key_mapping_record(self)

    @property
    def ready(self) -> bool:
        return self.status == STATUS_READY

    def to_mapping_ref(self) -> GcsimMappingRef:
        return key_mapping_record_to_ref(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "project_id": self.project_id,
            "canonical_name": self.canonical_name,
            "gcsim_key": self.gcsim_key,
            "source_kind": self.source_kind,
            "source_name": self.source_name,
            "status": self.status,
            "warnings": list(self.warnings),
            "candidates": list(self.candidates),
        }


@dataclass(frozen=True, slots=True)
class GcsimKeyMappingReport:
    records: tuple[GcsimKeyMappingRecord, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return len(self.records)

    @property
    def counts_by_entity_status(self) -> dict[str, dict[str, int]]:
        counts: dict[str, Counter[str]] = defaultdict(Counter)
        for record in self.records:
            counts[record.entity_type][record.status] += 1
        return {
            entity_type: dict(sorted(status_counts.items()))
            for entity_type, status_counts in sorted(counts.items())
        }

    @property
    def missing_records(self) -> tuple[GcsimKeyMappingRecord, ...]:
        return tuple(
            record
            for record in self.records
            if record.status in {
                STATUS_MISSING,
                STATUS_DISPLAY_NAME_ONLY_REJECTED,
                STATUS_UNSUPPORTED_TRAVELER,
            }
        )

    @property
    def ambiguous_records(self) -> tuple[GcsimKeyMappingRecord, ...]:
        return tuple(
            record for record in self.records if record.status == STATUS_AMBIGUOUS
        )

    @property
    def ready_records(self) -> tuple[GcsimKeyMappingRecord, ...]:
        return tuple(record for record in self.records if record.ready)

    def mapping_ref_for(self, entity_type: str, project_id: str) -> GcsimMappingRef:
        entity_type = _text(entity_type)
        project_id = _text(project_id)
        matches = tuple(
            record
            for record in self.records
            if record.entity_type == entity_type and record.project_id == project_id
        )
        if len(matches) == 1:
            return matches[0].to_mapping_ref()
        if len(matches) > 1:
            return GcsimMappingRef(
                source=f"{SOURCE_KIND_CURATED}:duplicate_seed_records",
                ambiguous=True,
            )
        return GcsimMappingRef()

    def to_dict(self) -> dict[str, Any]:
        warning_counts = Counter(
            warning
            for record in self.records
            for warning in record.warnings
        )
        warning_counts.update(self.warnings)
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "gcsim_key_mapping_report",
            "total": self.total,
            "counts_by_entity_status": self.counts_by_entity_status,
            "warnings": dict(sorted(warning_counts.items())),
            "missing": [record.to_dict() for record in self.missing_records],
            "ambiguous": [record.to_dict() for record in self.ambiguous_records],
        }


def make_key_mapping_record(
    *,
    entity_type: str,
    project_id: str = "",
    canonical_name: str = "",
    gcsim_key: str = "",
    source_kind: str = "",
    source_name: str = "",
    status: str = STATUS_READY,
    warnings: Iterable[str] = (),
    candidates: Iterable[str] = (),
) -> GcsimKeyMappingRecord:
    return normalize_key_mapping_record(
        GcsimKeyMappingRecord(
            entity_type=_text(entity_type),
            project_id=_text(project_id),
            canonical_name=_text(canonical_name),
            gcsim_key=_text(gcsim_key),
            source_kind=_text(source_kind),
            source_name=_text(source_name),
            status=_text(status) or STATUS_MISSING,
            warnings=_dedupe_tuple(warnings),
            candidates=_dedupe_tuple(candidates),
        )
    )


def normalize_key_mapping_record(
    record: GcsimKeyMappingRecord | Mapping[str, Any],
) -> GcsimKeyMappingRecord:
    if not isinstance(record, GcsimKeyMappingRecord):
        record = _record_from_mapping(record)

    entity_type = _text(record.entity_type)
    project_id = _text(record.project_id)
    canonical_name = _text(record.canonical_name)
    gcsim_key = _text(record.gcsim_key)
    source_kind = _text(record.source_kind)
    source_name = _text(record.source_name)
    status = _text(record.status) or STATUS_MISSING
    warnings = list(record.warnings)
    candidates = _dedupe_tuple(record.candidates)

    if entity_type not in ENTITY_TYPES:
        status = STATUS_MISSING
        gcsim_key = ""
        warnings.append(WARNING_UNKNOWN_ENTITY_TYPE)

    if not project_id:
        status = STATUS_MISSING
        gcsim_key = ""
        warnings.append(WARNING_PROJECT_ID_MISSING)

    if _is_traveler_record(entity_type, project_id, canonical_name):
        status = STATUS_UNSUPPORTED_TRAVELER
        gcsim_key = ""
        candidates = ()
        warnings.append(WARNING_TRAVELER_DEFERRED)

    if _source_is_display_name_only(source_kind):
        status = STATUS_DISPLAY_NAME_ONLY_REJECTED
        gcsim_key = ""
        warnings.append(WARNING_DISPLAY_NAME_SOURCE_REJECTED)

    if status == STATUS_AMBIGUOUS:
        gcsim_key = ""
        warnings.append(WARNING_AMBIGUOUS_MAPPING)

    if not gcsim_key and status == STATUS_READY:
        status = STATUS_MISSING
        warnings.append(WARNING_MAPPING_KEY_MISSING)

    if status not in STATUSES:
        status = STATUS_MISSING

    if status == STATUS_READY and not source_kind:
        warnings.append(WARNING_SOURCE_KIND_MISSING)
    if status == STATUS_READY and not source_name:
        warnings.append(WARNING_SOURCE_NAME_MISSING)

    return GcsimKeyMappingRecord(
        entity_type=entity_type,
        project_id=project_id,
        canonical_name=canonical_name,
        gcsim_key=gcsim_key if status == STATUS_READY else "",
        source_kind=source_kind,
        source_name=source_name,
        status=status,
        warnings=_dedupe_tuple(warnings),
        candidates=candidates,
    )


def build_key_mapping_report(
    records: Iterable[GcsimKeyMappingRecord | Mapping[str, Any]],
    *,
    production_mapping_source_present: bool = False,
) -> GcsimKeyMappingReport:
    normalized = tuple(normalize_key_mapping_record(record) for record in records)
    warnings: list[str] = []
    if not production_mapping_source_present:
        warnings.append(WARNING_PRODUCTION_MAPPING_DATA_MISSING)
    return GcsimKeyMappingReport(
        records=normalized,
        warnings=_dedupe_tuple(warnings),
    )


def key_mapping_record_to_ref(
    record: GcsimKeyMappingRecord | Mapping[str, Any],
) -> GcsimMappingRef:
    normalized = normalize_key_mapping_record(record)
    source = _mapping_ref_source(normalized)
    if normalized.status == STATUS_READY:
        return GcsimMappingRef(gcsim_key=normalized.gcsim_key, source=source)
    if normalized.status == STATUS_AMBIGUOUS:
        return GcsimMappingRef(source=source, ambiguous=True)
    return GcsimMappingRef(source=source)


def mapping_refs_by_identity(
    records: Iterable[GcsimKeyMappingRecord | Mapping[str, Any]],
) -> dict[tuple[str, str], GcsimMappingRef]:
    refs: dict[tuple[str, str], GcsimMappingRef] = {}
    for record in (normalize_key_mapping_record(item) for item in records):
        key = (record.entity_type, record.project_id)
        if key in refs:
            refs[key] = GcsimMappingRef(
                source=f"{SOURCE_KIND_CURATED}:duplicate_seed_records",
                ambiguous=True,
            )
        else:
            refs[key] = record.to_mapping_ref()
    return refs


def mapping_records_from_payload(
    payload: Mapping[str, Any],
    *,
    fallback_source_name: str = "",
) -> tuple[GcsimKeyMappingRecord, ...]:
    schema_version = _optional_int(payload.get("schema_version")) or SCHEMA_VERSION
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported GCSIM key mapping schema_version: {schema_version}")

    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("GCSIM key mapping payload requires records list")

    default_source_kind = _text(payload.get("source_kind"))
    default_source_name = _text(payload.get("source_name")) or _text(fallback_source_name)
    return tuple(
        make_key_mapping_record(
            entity_type=_text(item.get("entity_type")),
            project_id=_text(
                _first_present(item, "project_id", "set_uid", "character_id", "weapon_id")
            ),
            canonical_name=_text(
                _first_present(item, "canonical_name", "project_name", "name")
            ),
            gcsim_key=_text(item.get("gcsim_key")),
            source_kind=_text(item.get("source_kind")) or default_source_kind,
            source_name=_text(item.get("source_name")) or default_source_name,
            status=_text(item.get("status")) or STATUS_READY,
            warnings=_text_tuple(item.get("warnings")),
            candidates=_text_tuple(item.get("candidates")),
        )
        for item in records
        if isinstance(item, Mapping)
    )


def load_mapping_records_from_json(path: str | Path) -> tuple[GcsimKeyMappingRecord, ...]:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("GCSIM key mapping JSON root must be an object")
    return mapping_records_from_payload(payload, fallback_source_name=path.name)


def _record_from_mapping(mapping: Mapping[str, Any]) -> GcsimKeyMappingRecord:
    return GcsimKeyMappingRecord(
        entity_type=_text(mapping.get("entity_type")),
        project_id=_text(
            _first_present(mapping, "project_id", "set_uid", "character_id", "weapon_id")
        ),
        canonical_name=_text(
            _first_present(mapping, "canonical_name", "project_name", "name")
        ),
        gcsim_key=_text(mapping.get("gcsim_key")),
        source_kind=_text(mapping.get("source_kind")),
        source_name=_text(mapping.get("source_name")),
        status=_text(mapping.get("status")) or STATUS_MISSING,
        warnings=_text_tuple(mapping.get("warnings")),
        candidates=_text_tuple(mapping.get("candidates")),
    )


def _mapping_ref_source(record: GcsimKeyMappingRecord) -> str:
    source_kind = record.source_kind or record.status
    if record.source_name:
        return f"{source_kind}:{record.source_name}"
    return source_kind


def _source_is_display_name_only(source_kind: str) -> bool:
    return source_kind.casefold() in DISPLAY_NAME_SOURCE_KINDS


def _is_traveler_record(entity_type: str, project_id: str, canonical_name: str) -> bool:
    return (
        entity_type == ENTITY_CHARACTER
        and (
            project_id in TRAVELER_PROJECT_CHARACTER_IDS
            or canonical_name.casefold() == "traveler"
        )
    )


def _first_present(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return None


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (_text(value),) if _text(value) else ()
    if isinstance(value, Iterable):
        return tuple(_text(item) for item in value if _text(item))
    return (_text(value),) if _text(value) else ()


def _dedupe_tuple(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return tuple(result)
