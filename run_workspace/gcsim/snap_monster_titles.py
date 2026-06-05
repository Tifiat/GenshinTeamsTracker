"""Opt-in Snap monster Name -> Title fallback for GCSIM enemy type matching.

This helper intentionally reads only the `Name` and `Title` fields from an
explicit caller-provided Snap `monster.json`. It is a last-resort name/title
bridge for enemy type matching and must not be used as HP, stat, resist, wave,
or enemy-count truth.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .enemy_type_registry import GcsimEnemyNameCandidate, normalize_gcsim_enemy_name


SNAP_TITLE_SOURCE_KIND = "snap_monster_title"
SNAP_TITLE_STATUS_MISSING = "missing"
SNAP_TITLE_STATUS_RESOLVED = "resolved"
SNAP_TITLE_STATUS_AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class SnapMonsterTitleCandidate:
    source_name: str
    title: str

    @property
    def normalized_source_name(self) -> str:
        return normalize_gcsim_enemy_name(self.source_name)

    @property
    def normalized_title(self) -> str:
        return normalize_gcsim_enemy_name(self.title)

    def to_name_candidate(self) -> GcsimEnemyNameCandidate:
        return GcsimEnemyNameCandidate(
            source_kind=SNAP_TITLE_SOURCE_KIND,
            source_name=self.title,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "source_name": self.source_name,
            "title": self.title,
            "normalized_source_name": self.normalized_source_name,
            "normalized_title": self.normalized_title,
        }


@dataclass(frozen=True, slots=True)
class SnapMonsterTitleLookup:
    status: str
    source_name: str
    candidates: tuple[SnapMonsterTitleCandidate, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.status == SNAP_TITLE_STATUS_RESOLVED and bool(self.candidates)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source_name": self.source_name,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class SnapMonsterTitleIndex:
    titles_by_normalized_name: Mapping[str, tuple[SnapMonsterTitleCandidate, ...]]
    source_path: str = ""

    def lookup(self, source_name: str) -> SnapMonsterTitleLookup:
        normalized = normalize_gcsim_enemy_name(source_name)
        if not normalized:
            return SnapMonsterTitleLookup(
                status=SNAP_TITLE_STATUS_MISSING,
                source_name=str(source_name or ""),
                warnings=("snap_title_source_name_empty",),
            )
        candidates = self.titles_by_normalized_name.get(normalized, ())
        if not candidates:
            return SnapMonsterTitleLookup(
                status=SNAP_TITLE_STATUS_MISSING,
                source_name=str(source_name or ""),
                warnings=(f"snap_title_missing_for_name:{normalized}",),
            )
        normalized_titles = {candidate.normalized_title for candidate in candidates}
        if len(normalized_titles) > 1:
            return SnapMonsterTitleLookup(
                status=SNAP_TITLE_STATUS_AMBIGUOUS,
                source_name=str(source_name or ""),
                candidates=candidates,
                warnings=(f"snap_title_ambiguous_for_name:{normalized}",),
            )
        return SnapMonsterTitleLookup(
            status=SNAP_TITLE_STATUS_RESOLVED,
            source_name=str(source_name or ""),
            candidates=candidates[:1],
        )

    def title_candidates_for_names(
        self,
        name_candidates: tuple[GcsimEnemyNameCandidate, ...] | list[GcsimEnemyNameCandidate],
    ) -> SnapMonsterTitleLookup:
        resolved: list[SnapMonsterTitleCandidate] = []
        missing_warnings: list[str] = []
        seen_titles: set[str] = set()
        source_names: list[str] = []
        for name_candidate in name_candidates:
            source_names.append(name_candidate.source_name)
            lookup = self.lookup(name_candidate.source_name)
            if lookup.status == SNAP_TITLE_STATUS_AMBIGUOUS:
                return SnapMonsterTitleLookup(
                    status=SNAP_TITLE_STATUS_AMBIGUOUS,
                    source_name=name_candidate.source_name,
                    candidates=lookup.candidates,
                    warnings=lookup.warnings,
                )
            if not lookup.ready:
                missing_warnings.extend(lookup.warnings)
                continue
            candidate = lookup.candidates[0]
            if candidate.normalized_title in seen_titles:
                continue
            seen_titles.add(candidate.normalized_title)
            resolved.append(candidate)
        if len(resolved) > 1:
            names = ",".join(candidate.normalized_title for candidate in resolved)
            return SnapMonsterTitleLookup(
                status=SNAP_TITLE_STATUS_AMBIGUOUS,
                source_name="|".join(source_names),
                candidates=tuple(resolved),
                warnings=(f"snap_title_multiple_titles_for_candidates:{names}",),
            )
        if resolved:
            return SnapMonsterTitleLookup(
                status=SNAP_TITLE_STATUS_RESOLVED,
                source_name=resolved[0].source_name,
                candidates=(resolved[0],),
            )
        return SnapMonsterTitleLookup(
            status=SNAP_TITLE_STATUS_MISSING,
            source_name="|".join(source_names),
            warnings=tuple(missing_warnings) or ("snap_title_missing_for_all_candidates",),
        )


def load_snap_monster_title_index(path: str | Path) -> SnapMonsterTitleIndex:
    source_path = Path(path)
    payload = json.loads(source_path.read_text(encoding="utf-8-sig"))
    records = _monster_records(payload)
    grouped: dict[str, list[SnapMonsterTitleCandidate]] = {}
    seen: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, Mapping):
            continue
        name = str(record.get("Name") or "").strip()
        title = str(record.get("Title") or "").strip()
        normalized_name = normalize_gcsim_enemy_name(name)
        normalized_title = normalize_gcsim_enemy_name(title)
        if not normalized_name or not normalized_title:
            continue
        key = (normalized_name, normalized_title)
        if key in seen:
            continue
        seen.add(key)
        grouped.setdefault(normalized_name, []).append(
            SnapMonsterTitleCandidate(source_name=name, title=title)
        )
    return SnapMonsterTitleIndex(
        titles_by_normalized_name={
            name: tuple(candidates) for name, candidates in grouped.items()
        },
        source_path=str(source_path),
    )


def _monster_records(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping):
        for key in ("items", "data", "monsters"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise ValueError("Snap monster JSON must be a list of objects with Name and Title")
