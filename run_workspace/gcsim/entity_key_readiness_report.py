"""Backend/dev report for project entity names against GCSIM shortcut keys.

This module parses local prepared GCSIM source files and reports exact
normalized key candidates for characters, weapons, and artifact sets. Exact
name candidates are useful readiness evidence, but they are not committed
curated production mappings unless supplied through an explicit seed record.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hoyolab_export.artifact_set_catalog import SEED_CATALOG_PATH
from hoyolab_export.character_stats_catalog import (
    CHARACTER_BASE_STATS_CACHE_PATH,
    read_character_base_stats_cache,
)
from hoyolab_export.paths import PROJECT_ROOT
from hoyolab_export.weapon_stats_catalog import (
    WEAPON_STATS_CACHE_PATH,
    read_weapon_stats_cache,
)
from run_workspace.gcsim.key_mapping import (
    DEFAULT_GCSIM_KEY_MAPPING_SEED_PATH,
    ENTITY_ARTIFACT_SET,
    ENTITY_CHARACTER,
    ENTITY_TYPES,
    ENTITY_WEAPON,
    STATUS_AMBIGUOUS as SEED_STATUS_AMBIGUOUS,
    STATUS_READY as SEED_STATUS_READY,
    STATUS_UNSUPPORTED_TRAVELER as SEED_STATUS_UNSUPPORTED_TRAVELER,
    TRAVELER_PROJECT_CHARACTER_IDS,
    WARNING_PRODUCTION_MAPPING_DATA_MISSING,
    WARNING_TRAVELER_DEFERRED,
    GcsimKeyMappingRecord,
    GcsimKeyMappingReport,
    build_key_mapping_report,
    load_default_mapping_seed_records,
    load_mapping_records_from_json,
)


STATUS_READY = "ready"
STATUS_MISSING = "missing"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_UNSUPPORTED_TRAVELER = "unsupported_traveler"

METHOD_EXPLICIT_SEED = "explicit_seed"
METHOD_EXACT_NORMALIZED_NAME = "exact_normalized_name"
METHOD_CONTIGUOUS_NAME_SPAN = "contiguous_name_span"
METHOD_MISSING = "missing"
METHOD_AMBIGUOUS = "ambiguous"
METHOD_UNSUPPORTED_TRAVELER = "unsupported_traveler"

WARNING_AUTO_EXACT_NOT_CURATED = "auto_exact_candidate_not_curated_mapping"
WARNING_CONTIGUOUS_NAME_SPAN_NOT_CURATED = (
    "contiguous_name_span_candidate_not_curated_mapping"
)
WARNING_SINGLE_TOKEN_CONTIGUOUS_SPAN = "single_token_contiguous_span_lower_confidence"
WARNING_SHORTER_CONTIGUOUS_SPAN_CANDIDATES_IGNORED = (
    "shorter_contiguous_span_candidates_ignored"
)
WARNING_DEV_SEED_NOT_PRODUCTION = "default_seed_is_curated_dev_seed_only"
WARNING_CHARACTER_IDENTITY_IS_HOYOWIKI_ENTRY_PAGE_ID = (
    "character_identity_is_hoyowiki_entry_page_id"
)
WARNING_WEAPON_IDENTITY_IS_HOYOWIKI_ENTRY_PAGE_ID = (
    "weapon_identity_is_hoyowiki_entry_page_id"
)
WARNING_PROJECT_ID_MISSING = "project_id_missing"
WARNING_DISPLAY_NAME_MISSING = "display_name_missing"
WARNING_GCSIM_REGISTRY_KEY_MISSING = "gcsim_registry_key_missing"
WARNING_DUPLICATE_SEED_RECORDS = "duplicate_seed_records"
WARNING_EXPLICIT_SEED_NOT_READY = "explicit_seed_not_ready"

KIND = "gcsim_entity_key_readiness_report"
SCHEMA_VERSION = 1

DEFAULT_GCSIM_SOURCE_ROOT = (
    PROJECT_ROOT / "data" / "gcsim" / "sources" / "expanded" / "v2.42.2"
)
DEFAULT_CHARACTER_SHORTCUT_SOURCE = (
    DEFAULT_GCSIM_SOURCE_ROOT / "pkg" / "shortcut" / "characters.go"
)
DEFAULT_WEAPON_SHORTCUT_SOURCE = (
    DEFAULT_GCSIM_SOURCE_ROOT / "pkg" / "shortcut" / "weapons.go"
)
DEFAULT_ARTIFACT_SET_SHORTCUT_SOURCE = (
    DEFAULT_GCSIM_SOURCE_ROOT / "pkg" / "shortcut" / "artifacts.go"
)

_GO_MAP_KEY_RE = re.compile(r'(?m)^\s*"([^"\n]+)"\s*:')
_POSSESSIVE_RE = re.compile(r"([a-z0-9])['\u2019]s\b")
_MIN_CONTIGUOUS_SPAN_KEY_LENGTH = 4


@dataclass(frozen=True, slots=True)
class GcsimEntityRegistry:
    character_keys: tuple[str, ...] = ()
    weapon_keys: tuple[str, ...] = ()
    artifact_set_keys: tuple[str, ...] = ()
    source_paths: Mapping[str, str] | None = None

    def keys_for(self, entity_type: str) -> tuple[str, ...]:
        if entity_type == ENTITY_CHARACTER:
            return self.character_keys
        if entity_type == ENTITY_WEAPON:
            return self.weapon_keys
        if entity_type == ENTITY_ARTIFACT_SET:
            return self.artifact_set_keys
        return ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "counts": {
                ENTITY_CHARACTER: len(self.character_keys),
                ENTITY_WEAPON: len(self.weapon_keys),
                ENTITY_ARTIFACT_SET: len(self.artifact_set_keys),
            },
            "source_paths": dict(self.source_paths or {}),
        }


@dataclass(frozen=True, slots=True)
class ProjectEntity:
    entity_type: str
    project_id: str
    display_name: str
    source_name: str = ""
    normalized_name: str = ""
    warnings: tuple[str, ...] = ()

    def normalized(self) -> "ProjectEntity":
        return ProjectEntity(
            entity_type=_text(self.entity_type),
            project_id=_text(self.project_id),
            display_name=_text(self.display_name),
            source_name=_text(self.source_name),
            normalized_name=normalize_gcsim_key_candidate(
                self.normalized_name or self.display_name
            ),
            warnings=_dedupe_tuple(self.warnings),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "project_id": self.project_id,
            "display_name": self.display_name,
            "source_name": self.source_name,
            "normalized_name": self.normalized_name,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class EntityKeyAuditEntry:
    entity_type: str
    project_id: str
    display_name: str
    normalized_candidate: str
    status: str
    method: str
    gcsim_key: str = ""
    candidates: tuple[str, ...] = ()
    source_name: str = ""
    seed_source_kind: str = ""
    seed_source_name: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.status == STATUS_READY

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "project_id": self.project_id,
            "display_name": self.display_name,
            "normalized_candidate": self.normalized_candidate,
            "status": self.status,
            "method": self.method,
            "gcsim_key": self.gcsim_key,
            "candidates": list(self.candidates),
            "source_name": self.source_name,
            "seed_source_kind": self.seed_source_kind,
            "seed_source_name": self.seed_source_name,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class EntityKeyCoverageReport:
    entries: tuple[EntityKeyAuditEntry, ...]
    registry: GcsimEntityRegistry
    seed_report: GcsimKeyMappingReport | None = None
    source_notes: Mapping[str, str] | None = None
    warnings: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return len(self.entries)

    @property
    def counts_by_entity_status(self) -> dict[str, dict[str, int]]:
        result: dict[str, dict[str, int]] = {}
        for entity_type in ENTITY_TYPES:
            entries = [entry for entry in self.entries if entry.entity_type == entity_type]
            counts = Counter(entry.status for entry in entries)
            result[entity_type] = {
                "total": len(entries),
                STATUS_READY: counts.get(STATUS_READY, 0),
                STATUS_MISSING: counts.get(STATUS_MISSING, 0),
                STATUS_AMBIGUOUS: counts.get(STATUS_AMBIGUOUS, 0),
                STATUS_UNSUPPORTED_TRAVELER: counts.get(
                    STATUS_UNSUPPORTED_TRAVELER, 0
                ),
            }
        return result

    @property
    def method_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(entry.method for entry in self.entries).items()))

    @property
    def missing_entries(self) -> tuple[EntityKeyAuditEntry, ...]:
        return tuple(entry for entry in self.entries if entry.status == STATUS_MISSING)

    @property
    def ambiguous_entries(self) -> tuple[EntityKeyAuditEntry, ...]:
        return tuple(entry for entry in self.entries if entry.status == STATUS_AMBIGUOUS)

    @property
    def unsupported_entries(self) -> tuple[EntityKeyAuditEntry, ...]:
        return tuple(
            entry for entry in self.entries if entry.status == STATUS_UNSUPPORTED_TRAVELER
        )

    def to_dict(self) -> dict[str, Any]:
        warnings = Counter(self.warnings)
        for entry in self.entries:
            warnings.update(entry.warnings)
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "total": self.total,
            "counts_by_entity_status": self.counts_by_entity_status,
            "method_counts": self.method_counts,
            "warnings": dict(sorted(warnings.items())),
            "source_notes": dict(self.source_notes or {}),
            "registry": self.registry.to_dict(),
            "missing": [entry.to_dict() for entry in self.missing_entries],
            "ambiguous": [entry.to_dict() for entry in self.ambiguous_entries],
            "unsupported": [entry.to_dict() for entry in self.unsupported_entries],
            "entries": [entry.to_dict() for entry in self.entries],
        }


def parse_gcsim_shortcut_keys_from_go_source(source_text: str) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys(_GO_MAP_KEY_RE.findall(source_text))))


def load_gcsim_shortcut_keys(path: str | Path) -> tuple[str, ...]:
    return parse_gcsim_shortcut_keys_from_go_source(
        Path(path).read_text(encoding="utf-8")
    )


def load_gcsim_entity_registry(
    *,
    character_source_path: str | Path = DEFAULT_CHARACTER_SHORTCUT_SOURCE,
    weapon_source_path: str | Path = DEFAULT_WEAPON_SHORTCUT_SOURCE,
    artifact_set_source_path: str | Path = DEFAULT_ARTIFACT_SET_SHORTCUT_SOURCE,
) -> GcsimEntityRegistry:
    character_source = Path(character_source_path)
    weapon_source = Path(weapon_source_path)
    artifact_set_source = Path(artifact_set_source_path)
    return GcsimEntityRegistry(
        character_keys=load_gcsim_shortcut_keys(character_source),
        weapon_keys=load_gcsim_shortcut_keys(weapon_source),
        artifact_set_keys=load_gcsim_shortcut_keys(artifact_set_source),
        source_paths={
            ENTITY_CHARACTER: project_relative_path(character_source),
            ENTITY_WEAPON: project_relative_path(weapon_source),
            ENTITY_ARTIFACT_SET: project_relative_path(artifact_set_source),
        },
    )


def build_gcsim_registry_index(
    registry: GcsimEntityRegistry,
) -> dict[str, dict[str, tuple[str, ...]]]:
    return _registry_index(registry)


def build_entity_key_coverage_report(
    entities: Iterable[ProjectEntity | Mapping[str, Any]],
    registry: GcsimEntityRegistry,
    *,
    seed_records: Iterable[GcsimKeyMappingRecord | Mapping[str, Any]] = (),
    production_mapping_source_present: bool = False,
    source_notes: Mapping[str, str] | None = None,
) -> EntityKeyCoverageReport:
    seed_report = build_key_mapping_report(
        seed_records,
        production_mapping_source_present=production_mapping_source_present,
    )
    seed_by_identity = _seed_records_by_identity(seed_report.records)
    registry_index = _registry_index(registry)
    entries = tuple(
        audit_project_entity(entity, registry_index, seed_by_identity)
        for entity in entities
    )

    warnings = [WARNING_DEV_SEED_NOT_PRODUCTION]
    if not production_mapping_source_present:
        warnings.append(WARNING_PRODUCTION_MAPPING_DATA_MISSING)

    return EntityKeyCoverageReport(
        entries=entries,
        registry=registry,
        seed_report=seed_report,
        source_notes=source_notes or {},
        warnings=_dedupe_tuple(warnings),
    )


def audit_project_entity(
    entity: ProjectEntity | Mapping[str, Any],
    registry_index: Mapping[str, Mapping[str, tuple[str, ...]]],
    seed_by_identity: Mapping[tuple[str, str], tuple[GcsimKeyMappingRecord, ...]],
) -> EntityKeyAuditEntry:
    normalized = normalize_project_entity(entity)
    warnings = list(normalized.warnings)

    if _is_traveler_entity(normalized):
        warnings.append(WARNING_TRAVELER_DEFERRED)
        return _entry(
            normalized,
            status=STATUS_UNSUPPORTED_TRAVELER,
            method=METHOD_UNSUPPORTED_TRAVELER,
            warnings=warnings,
        )

    if not normalized.project_id:
        warnings.append(WARNING_PROJECT_ID_MISSING)
    if not normalized.display_name:
        warnings.append(WARNING_DISPLAY_NAME_MISSING)

    seed_records = seed_by_identity.get(
        (normalized.entity_type, normalized.project_id),
        (),
    )
    if len(seed_records) > 1:
        warnings.append(WARNING_DUPLICATE_SEED_RECORDS)
        return _entry(
            normalized,
            status=STATUS_AMBIGUOUS,
            method=METHOD_EXPLICIT_SEED,
            candidates=tuple(record.gcsim_key for record in seed_records if record.gcsim_key),
            warnings=warnings,
        )
    if len(seed_records) == 1:
        return _entry_from_seed(normalized, seed_records[0], warnings)

    if warnings and (
        WARNING_PROJECT_ID_MISSING in warnings
        or WARNING_DISPLAY_NAME_MISSING in warnings
    ):
        return _entry(
            normalized,
            status=STATUS_MISSING,
            method=METHOD_MISSING,
            warnings=warnings,
        )

    candidates = registry_index.get(normalized.entity_type, {}).get(
        normalized.normalized_name,
        (),
    )
    if len(candidates) == 1:
        warnings.append(WARNING_AUTO_EXACT_NOT_CURATED)
        return _entry(
            normalized,
            status=STATUS_READY,
            method=METHOD_EXACT_NORMALIZED_NAME,
            gcsim_key=candidates[0],
            candidates=candidates,
            warnings=warnings,
        )
    if len(candidates) > 1:
        return _entry(
            normalized,
            status=STATUS_AMBIGUOUS,
            method=METHOD_AMBIGUOUS,
            candidates=candidates,
            warnings=warnings,
        )

    span_match = _contiguous_name_span_match(normalized, registry_index)
    if span_match.status == STATUS_READY:
        warnings.extend(span_match.warnings)
        return _entry(
            normalized,
            status=STATUS_READY,
            method=METHOD_CONTIGUOUS_NAME_SPAN,
            gcsim_key=span_match.gcsim_key,
            candidates=span_match.candidates,
            warnings=warnings,
        )
    if span_match.status == STATUS_AMBIGUOUS:
        warnings.extend(span_match.warnings)
        return _entry(
            normalized,
            status=STATUS_AMBIGUOUS,
            method=METHOD_CONTIGUOUS_NAME_SPAN,
            candidates=span_match.candidates,
            warnings=warnings,
        )

    warnings.append(WARNING_GCSIM_REGISTRY_KEY_MISSING)
    return _entry(
        normalized,
        status=STATUS_MISSING,
        method=METHOD_MISSING,
        warnings=warnings,
    )


def normalize_project_entity(entity: ProjectEntity | Mapping[str, Any]) -> ProjectEntity:
    if isinstance(entity, ProjectEntity):
        return entity.normalized()
    return ProjectEntity(
        entity_type=_text(entity.get("entity_type")),
        project_id=_text(
            _first_present(entity, "project_id", "character_id", "weapon_id", "set_uid")
        ),
        display_name=_text(
            _first_present(entity, "display_name", "canonical_name", "name", "fallback_name")
        ),
        source_name=_text(entity.get("source_name")),
        normalized_name=_text(entity.get("normalized_name")),
        warnings=_text_tuple(entity.get("warnings")),
    ).normalized()


def normalize_gcsim_key_candidate(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(re.findall(r"[a-z0-9]+", text))


@dataclass(frozen=True, slots=True)
class _ContiguousSpanMatch:
    status: str = STATUS_MISSING
    gcsim_key: str = ""
    candidates: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _contiguous_name_span_match(
    entity: ProjectEntity,
    registry_index: Mapping[str, Mapping[str, tuple[str, ...]]],
) -> _ContiguousSpanMatch:
    spans = _contiguous_name_span_map(entity.display_name)
    if not spans:
        return _ContiguousSpanMatch()

    candidates: list[tuple[str, str, int]] = []
    for normalized_key, keys in registry_index.get(entity.entity_type, {}).items():
        if (
            normalized_key in spans
            and len(normalized_key) >= _MIN_CONTIGUOUS_SPAN_KEY_LENGTH
        ):
            for key in keys:
                candidates.append((key, normalized_key, spans[normalized_key]))

    if not candidates:
        return _ContiguousSpanMatch()

    longest_length = max(len(normalized_key) for _, normalized_key, _ in candidates)
    longest = tuple(
        item for item in candidates if len(item[1]) == longest_length
    )
    if len(longest) != 1:
        return _ContiguousSpanMatch(
            status=STATUS_AMBIGUOUS,
            candidates=_dedupe_tuple(key for key, _, _ in longest),
        )

    key, _, token_count = longest[0]
    warnings = [WARNING_CONTIGUOUS_NAME_SPAN_NOT_CURATED]
    if token_count == 1:
        warnings.append(WARNING_SINGLE_TOKEN_CONTIGUOUS_SPAN)
    if len(candidates) > 1:
        warnings.append(WARNING_SHORTER_CONTIGUOUS_SPAN_CANDIDATES_IGNORED)
    return _ContiguousSpanMatch(
        status=STATUS_READY,
        gcsim_key=key,
        candidates=(key,),
        warnings=tuple(warnings),
    )


def _contiguous_name_span_map(value: Any) -> dict[str, int]:
    tokens = _normalized_name_tokens(value)
    spans: dict[str, int] = {}
    for start in range(len(tokens)):
        span = ""
        for end in range(start, len(tokens)):
            span += tokens[end]
            spans[span] = max(spans.get(span, 0), end - start + 1)
    return spans


def _normalized_name_tokens(value: Any) -> tuple[str, ...]:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = _POSSESSIVE_RE.sub(r"\1", text)
    tokens = re.findall(r"[a-z0-9]+", text)
    return tuple(token for token in tokens if token and token != "s")


def load_project_entities_from_json(path: str | Path) -> tuple[ProjectEntity, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return tuple(normalize_project_entity(item) for item in payload if isinstance(item, Mapping))
    if not isinstance(payload, Mapping):
        raise ValueError("project entity JSON root must be an object or list")

    records: list[Mapping[str, Any]] = []
    entities = payload.get("entities")
    if isinstance(entities, list):
        records.extend(item for item in entities if isinstance(item, Mapping))
    for key, entity_type in (
        ("characters", ENTITY_CHARACTER),
        ("weapons", ENTITY_WEAPON),
        ("artifact_sets", ENTITY_ARTIFACT_SET),
        ("sets", ENTITY_ARTIFACT_SET),
    ):
        items = payload.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, Mapping):
                    merged = dict(item)
                    merged.setdefault("entity_type", entity_type)
                    records.append(merged)
    return tuple(normalize_project_entity(item) for item in records)


def load_default_project_catalog_entities(
    *,
    character_cache_path: str | Path = CHARACTER_BASE_STATS_CACHE_PATH,
    weapon_cache_path: str | Path = WEAPON_STATS_CACHE_PATH,
    artifact_set_catalog_path: str | Path = SEED_CATALOG_PATH,
) -> tuple[ProjectEntity, ...]:
    entities: list[ProjectEntity] = []
    entities.extend(load_character_entities_from_stats_cache(character_cache_path))
    entities.extend(load_weapon_entities_from_stats_cache(weapon_cache_path))
    entities.extend(load_artifact_set_entities_from_seed_catalog(artifact_set_catalog_path))
    return tuple(entities)


def load_character_entities_from_stats_cache(path: str | Path) -> tuple[ProjectEntity, ...]:
    path = Path(path)
    if not path.exists():
        return ()
    catalog = read_character_base_stats_cache(path)
    if catalog is None:
        return ()
    return tuple(
        ProjectEntity(
            entity_type=ENTITY_CHARACTER,
            project_id=entry.entry_page_id,
            display_name=entry.name,
            source_name=f"{project_relative_path(path)}:entry_page_id",
            warnings=(WARNING_CHARACTER_IDENTITY_IS_HOYOWIKI_ENTRY_PAGE_ID,),
        ).normalized()
        for entry in catalog.entries
    )


def load_weapon_entities_from_stats_cache(path: str | Path) -> tuple[ProjectEntity, ...]:
    path = Path(path)
    if not path.exists():
        return ()
    catalog = read_weapon_stats_cache(path)
    if catalog is None:
        return ()
    return tuple(
        ProjectEntity(
            entity_type=ENTITY_WEAPON,
            project_id=entry.entry_page_id,
            display_name=entry.name,
            source_name=f"{project_relative_path(path)}:entry_page_id",
            warnings=(WARNING_WEAPON_IDENTITY_IS_HOYOWIKI_ENTRY_PAGE_ID,),
        ).normalized()
        for entry in catalog.entries
    )


def load_artifact_set_entities_from_seed_catalog(
    path: str | Path,
) -> tuple[ProjectEntity, ...]:
    path = Path(path)
    if not path.exists():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        return ()
    records = payload.get("sets") or []
    entities: list[ProjectEntity] = []
    for item in records:
        if not isinstance(item, Mapping):
            continue
        set_uid = _text(item.get("set_uid"))
        display_name = _artifact_set_english_name(item)
        entities.append(
            ProjectEntity(
                entity_type=ENTITY_ARTIFACT_SET,
                project_id=set_uid,
                display_name=display_name,
                source_name=f"{project_relative_path(path)}:set_uid",
            ).normalized()
        )
    return tuple(entities)


def format_entity_key_coverage_report_text(
    report: EntityKeyCoverageReport,
    *,
    examples_per_status: int = 8,
) -> str:
    lines = [
        "GCSIM entity key readiness report",
        f"total={report.total}",
        "counts:",
    ]
    for entity_type, counts in report.counts_by_entity_status.items():
        lines.append(
            "  "
            + entity_type
            + ": "
            + ", ".join(f"{key}={value}" for key, value in counts.items())
        )
    lines.append(
        "methods="
        + (
            ", ".join(
                f"{method}={count}"
                for method, count in report.method_counts.items()
            )
            or "none"
        )
    )
    warnings = report.to_dict().get("warnings", {})
    lines.append(
        "warnings="
        + (
            ", ".join(f"{key}={value}" for key, value in sorted(warnings.items()))
            if warnings
            else "none"
        )
    )
    for label, entries in (
        ("missing", report.missing_entries),
        ("ambiguous", report.ambiguous_entries),
        ("unsupported", report.unsupported_entries),
    ):
        lines.append(f"{label}={len(entries)}")
        for entry in entries[:examples_per_status]:
            parts = [
                entry.entity_type,
                f"id={entry.project_id or '-'}",
                f"name={entry.display_name or '-'}",
                f"candidate={entry.normalized_candidate or '-'}",
                f"method={entry.method}",
            ]
            if entry.candidates:
                parts.append("candidates=" + "|".join(entry.candidates))
            if entry.warnings:
                parts.append("warnings=" + "|".join(entry.warnings))
            lines.append("  " + "; ".join(parts))
    return "\n".join(lines)


def project_relative_path(path: str | Path) -> str:
    path = Path(path)
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def _entry_from_seed(
    entity: ProjectEntity,
    seed: GcsimKeyMappingRecord,
    warnings: list[str],
) -> EntityKeyAuditEntry:
    warnings.extend(seed.warnings)
    if seed.status == SEED_STATUS_READY:
        return _entry(
            entity,
            status=STATUS_READY,
            method=METHOD_EXPLICIT_SEED,
            gcsim_key=seed.gcsim_key,
            candidates=(seed.gcsim_key,),
            seed_source_kind=seed.source_kind,
            seed_source_name=seed.source_name,
            warnings=warnings,
        )
    if seed.status == SEED_STATUS_AMBIGUOUS:
        return _entry(
            entity,
            status=STATUS_AMBIGUOUS,
            method=METHOD_EXPLICIT_SEED,
            candidates=seed.candidates,
            seed_source_kind=seed.source_kind,
            seed_source_name=seed.source_name,
            warnings=warnings,
        )
    if seed.status == SEED_STATUS_UNSUPPORTED_TRAVELER:
        warnings.append(WARNING_TRAVELER_DEFERRED)
        return _entry(
            entity,
            status=STATUS_UNSUPPORTED_TRAVELER,
            method=METHOD_EXPLICIT_SEED,
            seed_source_kind=seed.source_kind,
            seed_source_name=seed.source_name,
            warnings=warnings,
        )
    warnings.append(WARNING_EXPLICIT_SEED_NOT_READY)
    return _entry(
        entity,
        status=STATUS_MISSING,
        method=METHOD_EXPLICIT_SEED,
        seed_source_kind=seed.source_kind,
        seed_source_name=seed.source_name,
        warnings=warnings,
    )


def _entry(
    entity: ProjectEntity,
    *,
    status: str,
    method: str,
    gcsim_key: str = "",
    candidates: Iterable[str] = (),
    seed_source_kind: str = "",
    seed_source_name: str = "",
    warnings: Iterable[str] = (),
) -> EntityKeyAuditEntry:
    return EntityKeyAuditEntry(
        entity_type=entity.entity_type,
        project_id=entity.project_id,
        display_name=entity.display_name,
        normalized_candidate=entity.normalized_name,
        status=status,
        method=method,
        gcsim_key=_text(gcsim_key),
        candidates=_dedupe_tuple(candidates),
        source_name=entity.source_name,
        seed_source_kind=_text(seed_source_kind),
        seed_source_name=_text(seed_source_name),
        warnings=_dedupe_tuple(warnings),
    )


def _registry_index(
    registry: GcsimEntityRegistry,
) -> dict[str, dict[str, tuple[str, ...]]]:
    result: dict[str, dict[str, tuple[str, ...]]] = {}
    for entity_type in ENTITY_TYPES:
        grouped: dict[str, list[str]] = defaultdict(list)
        for key in registry.keys_for(entity_type):
            normalized = normalize_gcsim_key_candidate(key)
            if normalized:
                grouped[normalized].append(key)
        result[entity_type] = {
            key: tuple(values)
            for key, values in grouped.items()
        }
    return result


def _seed_records_by_identity(
    records: Iterable[GcsimKeyMappingRecord],
) -> dict[tuple[str, str], tuple[GcsimKeyMappingRecord, ...]]:
    grouped: dict[tuple[str, str], list[GcsimKeyMappingRecord]] = defaultdict(list)
    for record in records:
        grouped[(record.entity_type, record.project_id)].append(record)
    return {key: tuple(values) for key, values in grouped.items()}


def _is_traveler_entity(entity: ProjectEntity) -> bool:
    normalized_name = normalize_gcsim_key_candidate(entity.display_name)
    return (
        entity.entity_type == ENTITY_CHARACTER
        and (
            entity.project_id in TRAVELER_PROJECT_CHARACTER_IDS
            or normalized_name == "traveler"
            or normalized_name.startswith("traveler")
            or normalized_name.startswith("aether")
            or normalized_name.startswith("lumine")
        )
    )


def _artifact_set_english_name(item: Mapping[str, Any]) -> str:
    for name_item in item.get("names") or ():
        if isinstance(name_item, Mapping) and _text(name_item.get("lang")) == "en-us":
            name = _text(name_item.get("name"))
            if name:
                return name
    return _text(item.get("fallback_name")) or _text(item.get("set_uid"))


def _first_present(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = _text(value)
        return (text,) if text else ()
    if isinstance(value, Iterable):
        return tuple(_text(item) for item in value if _text(item))
    text = _text(value)
    return (text,) if text else ()


def _dedupe_tuple(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return tuple(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report project entity GCSIM key readiness from local sources.",
    )
    parser.add_argument("--entities", help="Optional explicit project entity JSON path.")
    parser.add_argument("--seed", help="Optional explicit GCSIM key seed JSON path.")
    parser.add_argument(
        "--trusted-production-source",
        action="store_true",
        help="Only set when the seed is a trusted complete production mapping source.",
    )
    parser.add_argument(
        "--character-registry-source",
        default=str(DEFAULT_CHARACTER_SHORTCUT_SOURCE),
    )
    parser.add_argument(
        "--weapon-registry-source",
        default=str(DEFAULT_WEAPON_SHORTCUT_SOURCE),
    )
    parser.add_argument(
        "--artifact-set-registry-source",
        default=str(DEFAULT_ARTIFACT_SET_SHORTCUT_SOURCE),
    )
    parser.add_argument("--character-cache", default=str(CHARACTER_BASE_STATS_CACHE_PATH))
    parser.add_argument("--weapon-cache", default=str(WEAPON_STATS_CACHE_PATH))
    parser.add_argument("--artifact-set-catalog", default=str(SEED_CATALOG_PATH))
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--examples", type=int, default=8)
    args = parser.parse_args(argv)

    registry = load_gcsim_entity_registry(
        character_source_path=args.character_registry_source,
        weapon_source_path=args.weapon_registry_source,
        artifact_set_source_path=args.artifact_set_registry_source,
    )
    entities = (
        load_project_entities_from_json(args.entities)
        if args.entities
        else load_default_project_catalog_entities(
            character_cache_path=args.character_cache,
            weapon_cache_path=args.weapon_cache,
            artifact_set_catalog_path=args.artifact_set_catalog,
        )
    )
    seed_records = (
        load_mapping_records_from_json(args.seed)
        if args.seed
        else load_default_mapping_seed_records()
    )
    source_notes = {
        "entities": args.entities or "default local cache/static catalog files",
        "seed": args.seed or project_relative_path(DEFAULT_GCSIM_KEY_MAPPING_SEED_PATH),
    }
    report = build_entity_key_coverage_report(
        entities,
        registry,
        seed_records=seed_records,
        production_mapping_source_present=args.trusted_production_source,
        source_notes=source_notes,
    )

    if args.format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=True, indent=2, sort_keys=True))
    else:
        print(
            format_entity_key_coverage_report_text(
                report,
                examples_per_status=max(0, args.examples),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
