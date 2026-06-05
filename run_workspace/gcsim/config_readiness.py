"""Pure readiness audit for future GCSIM config generation.

This module is a backend-only foundation. It accepts lightweight, already
prepared inputs and checks whether each entity has an explicit, non-localized
GCSIM mapping plus enough account/build data for a future config generator.
It intentionally does not read UI widgets, query SQLite, infer GCSIM keys from
display names, generate config text, run the artifact, or solve Traveler
variant selection. Tests pin this temporary adapter-free contract until a real
mapping/source-owner layer exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from hoyolab_export.artifact_build_snapshot import ARTIFACT_POSITIONS
from hoyolab_export.stat_normalization import (
    NormalizedStatBlock,
    normalize_artifact_build_snapshot_stats,
    normalized_stats_to_gcsim_add_stats,
)


READINESS_READY = "ready"
READINESS_MISSING_MAPPING = "missing_mapping"
READINESS_AMBIGUOUS_MAPPING = "ambiguous_mapping"
READINESS_UNSUPPORTED_TRAVELER = "unsupported_traveler"
READINESS_MISSING_LEVEL = "missing_level"
READINESS_MISSING_WEAPON = "missing_weapon"
READINESS_MISSING_ARTIFACT_DATA = "missing_artifact_data"
READINESS_MISSING_TALENT_DATA = "missing_talent_data"

WARNING_DISPLAY_NAME_ONLY_MAPPING = "display_name_only_mapping_not_stable"
WARNING_MAPPING_SOURCE_MISSING = "mapping_source_missing"
WARNING_TRAVELER_DEFERRED = "traveler_variant_selection_deferred"
WARNING_ARTIFACT_SET_MAPPING_MISSING = "artifact_set_mapping_missing"
WARNING_ARTIFACT_ADD_STATS_EMPTY = "artifact_add_stats_empty"
WARNING_TALENT_ORDER_UNCONFIRMED = "talent_order_unconfirmed"

DISPLAY_NAME_MAPPING_SOURCES = {
    "display_name",
    "localized_display_name",
    "name",
}

STATUS_PRIORITY = (
    READINESS_UNSUPPORTED_TRAVELER,
    READINESS_AMBIGUOUS_MAPPING,
    READINESS_MISSING_MAPPING,
    READINESS_MISSING_LEVEL,
    READINESS_MISSING_WEAPON,
    READINESS_MISSING_ARTIFACT_DATA,
    READINESS_MISSING_TALENT_DATA,
)


@dataclass(frozen=True, slots=True)
class GcsimMappingRef:
    gcsim_key: str = ""
    source: str = ""
    ambiguous: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "gcsim_key": self.gcsim_key,
            "source": self.source,
            "ambiguous": self.ambiguous,
        }


@dataclass(frozen=True, slots=True)
class GcsimTalentInput:
    normal: int | None = None
    skill: int | None = None
    burst: int | None = None
    source_order_confirmed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "normal": self.normal,
            "skill": self.skill,
            "burst": self.burst,
            "source_order_confirmed": self.source_order_confirmed,
        }


@dataclass(frozen=True, slots=True)
class GcsimWeaponInput:
    project_weapon_id: str = ""
    display_name: str = ""
    level: int | None = None
    refinement: int | None = None
    mapping: GcsimMappingRef = field(default_factory=GcsimMappingRef)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_weapon_id": self.project_weapon_id,
            "display_name": self.display_name,
            "level": self.level,
            "refinement": self.refinement,
            "mapping": self.mapping.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GcsimArtifactSetInput:
    set_uid: str = ""
    display_name: str = ""
    piece_count: int = 0
    mapping: GcsimMappingRef = field(default_factory=GcsimMappingRef)

    def to_dict(self) -> dict[str, Any]:
        return {
            "set_uid": self.set_uid,
            "display_name": self.display_name,
            "piece_count": self.piece_count,
            "mapping": self.mapping.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GcsimArtifactBuildInput:
    artifact_ids_by_pos: Mapping[int, int] = field(default_factory=dict)
    missing_positions: tuple[int, ...] = ()
    active_sets: tuple[GcsimArtifactSetInput, ...] = ()
    stat_totals: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_ids_by_pos": {
                str(pos): artifact_id
                for pos, artifact_id in sorted(self.artifact_ids_by_pos.items())
            },
            "missing_positions": list(self.missing_positions),
            "active_sets": [item.to_dict() for item in self.active_sets],
            "stat_totals": [dict(item) for item in self.stat_totals],
        }


@dataclass(frozen=True, slots=True)
class GcsimCharacterInput:
    project_character_id: str = ""
    display_name: str = ""
    level: int | None = None
    max_level: int | None = None
    constellation: int | None = None
    mapping: GcsimMappingRef = field(default_factory=GcsimMappingRef)
    weapon: GcsimWeaponInput | None = None
    artifact_build: GcsimArtifactBuildInput | None = None
    talents: GcsimTalentInput | None = None
    is_traveler: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_character_id": self.project_character_id,
            "display_name": self.display_name,
            "level": self.level,
            "max_level": self.max_level,
            "constellation": self.constellation,
            "mapping": self.mapping.to_dict(),
            "weapon": self.weapon.to_dict() if self.weapon is not None else None,
            "artifact_build": (
                self.artifact_build.to_dict()
                if self.artifact_build is not None
                else None
            ),
            "talents": self.talents.to_dict() if self.talents is not None else None,
            "is_traveler": self.is_traveler,
        }


@dataclass(frozen=True, slots=True)
class GcsimTeamInput:
    characters: tuple[GcsimCharacterInput, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "characters": [character.to_dict() for character in self.characters],
        }


@dataclass(frozen=True, slots=True)
class GcsimReadinessIssue:
    status: str
    field: str
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "field": self.field,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class GcsimMappingAudit:
    entity_type: str
    status: str
    ready: bool
    project_id: str = ""
    display_name: str = ""
    gcsim_key: str = ""
    source: str = ""
    warnings: tuple[str, ...] = ()
    issues: tuple[GcsimReadinessIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "status": self.status,
            "ready": self.ready,
            "project_id": self.project_id,
            "display_name": self.display_name,
            "gcsim_key": self.gcsim_key,
            "source": self.source,
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class GcsimTalentReadinessAudit:
    status: str
    ready: bool
    warnings: tuple[str, ...] = ()
    issues: tuple[GcsimReadinessIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class GcsimWeaponReadinessAudit:
    status: str
    ready: bool
    mapping: GcsimMappingAudit | None = None
    warnings: tuple[str, ...] = ()
    issues: tuple[GcsimReadinessIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "mapping": self.mapping.to_dict() if self.mapping is not None else None,
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class GcsimArtifactSetReadinessAudit:
    status: str
    ready: bool
    set_uid: str = ""
    piece_count: int = 0
    mapping: GcsimMappingAudit | None = None
    warnings: tuple[str, ...] = ()
    issues: tuple[GcsimReadinessIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "set_uid": self.set_uid,
            "piece_count": self.piece_count,
            "mapping": self.mapping.to_dict() if self.mapping is not None else None,
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class GcsimArtifactReadinessAudit:
    status: str
    ready: bool
    artifact_count: int = 0
    missing_positions: tuple[int, ...] = ()
    add_stats: Mapping[str, float] = field(default_factory=dict)
    normalized_stats: NormalizedStatBlock | None = None
    set_audits: tuple[GcsimArtifactSetReadinessAudit, ...] = ()
    warnings: tuple[str, ...] = ()
    issues: tuple[GcsimReadinessIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "artifact_count": self.artifact_count,
            "missing_positions": list(self.missing_positions),
            "add_stats": dict(self.add_stats),
            "normalized_stats": (
                self.normalized_stats.to_dict()
                if self.normalized_stats is not None
                else None
            ),
            "set_audits": [audit.to_dict() for audit in self.set_audits],
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class GcsimCharacterReadinessAudit:
    status: str
    ready: bool
    project_character_id: str = ""
    display_name: str = ""
    character_mapping: GcsimMappingAudit | None = None
    weapon: GcsimWeaponReadinessAudit | None = None
    artifacts: GcsimArtifactReadinessAudit | None = None
    talents: GcsimTalentReadinessAudit | None = None
    warnings: tuple[str, ...] = ()
    issues: tuple[GcsimReadinessIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "project_character_id": self.project_character_id,
            "display_name": self.display_name,
            "character_mapping": (
                self.character_mapping.to_dict()
                if self.character_mapping is not None
                else None
            ),
            "weapon": self.weapon.to_dict() if self.weapon is not None else None,
            "artifacts": self.artifacts.to_dict() if self.artifacts is not None else None,
            "talents": self.talents.to_dict() if self.talents is not None else None,
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class GcsimTeamReadinessAudit:
    status: str
    ready: bool
    character_audits: tuple[GcsimCharacterReadinessAudit, ...] = ()
    warnings: tuple[str, ...] = ()
    issues: tuple[GcsimReadinessIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "character_audits": [audit.to_dict() for audit in self.character_audits],
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def audit_gcsim_team_readiness(
    team: GcsimTeamInput | Mapping[str, Any],
) -> GcsimTeamReadinessAudit:
    normalized = _team_input(team)
    character_audits = tuple(
        audit_gcsim_character_readiness(character)
        for character in normalized.characters
    )
    issues = tuple(
        issue
        for audit in character_audits
        for issue in audit.issues
    )
    warnings = _dedupe_tuple(
        warning
        for audit in character_audits
        for warning in audit.warnings
    )
    status = _status_from_issues(issues)
    return GcsimTeamReadinessAudit(
        status=status,
        ready=status == READINESS_READY,
        character_audits=character_audits,
        warnings=warnings,
        issues=issues,
    )


def audit_gcsim_character_readiness(
    character: GcsimCharacterInput | Mapping[str, Any],
) -> GcsimCharacterReadinessAudit:
    normalized = _character_input(character)
    issues: list[GcsimReadinessIssue] = []
    warnings: list[str] = []

    if normalized.is_traveler or _looks_like_account_traveler(normalized):
        warnings.append(WARNING_TRAVELER_DEFERRED)
        issues.append(
            GcsimReadinessIssue(
                READINESS_UNSUPPORTED_TRAVELER,
                "character",
                "Traveler variant selection is not confirmed for GCSIM.",
            )
        )

    character_mapping = audit_mapping_ref(
        normalized.mapping,
        entity_type="character",
        project_id=normalized.project_character_id,
        display_name=normalized.display_name,
    )
    issues.extend(character_mapping.issues)
    warnings.extend(character_mapping.warnings)

    if normalized.level is None or normalized.max_level is None:
        issues.append(
            GcsimReadinessIssue(
                READINESS_MISSING_LEVEL,
                "character.level",
                "GCSIM character level needs current/max level.",
            )
        )

    weapon = audit_gcsim_weapon_readiness(normalized.weapon)
    artifacts = audit_gcsim_artifact_readiness(normalized.artifact_build)
    talents = audit_gcsim_talent_readiness(normalized.talents)
    issues.extend(weapon.issues)
    issues.extend(artifacts.issues)
    issues.extend(talents.issues)
    warnings.extend(weapon.warnings)
    warnings.extend(artifacts.warnings)
    warnings.extend(talents.warnings)

    status = _status_from_issues(issues)
    return GcsimCharacterReadinessAudit(
        status=status,
        ready=status == READINESS_READY,
        project_character_id=normalized.project_character_id,
        display_name=normalized.display_name,
        character_mapping=character_mapping,
        weapon=weapon,
        artifacts=artifacts,
        talents=talents,
        warnings=_dedupe_tuple(warnings),
        issues=tuple(issues),
    )


def audit_gcsim_weapon_readiness(
    weapon: GcsimWeaponInput | Mapping[str, Any] | None,
) -> GcsimWeaponReadinessAudit:
    if weapon is None:
        issue = GcsimReadinessIssue(
            READINESS_MISSING_WEAPON,
            "weapon",
            "No equipped/current weapon input was provided.",
        )
        return GcsimWeaponReadinessAudit(
            status=READINESS_MISSING_WEAPON,
            ready=False,
            issues=(issue,),
        )

    normalized = _weapon_input(weapon)
    mapping = audit_mapping_ref(
        normalized.mapping,
        entity_type="weapon",
        project_id=normalized.project_weapon_id,
        display_name=normalized.display_name,
    )
    issues = list(mapping.issues)
    warnings = list(mapping.warnings)
    if normalized.level is None:
        issues.append(
            GcsimReadinessIssue(
                READINESS_MISSING_LEVEL,
                "weapon.level",
                "GCSIM weapon config needs the equipped weapon level.",
            )
        )
    if normalized.refinement is None:
        issues.append(
            GcsimReadinessIssue(
                READINESS_MISSING_WEAPON,
                "weapon.refinement",
                "GCSIM weapon config needs refinement.",
            )
        )
    status = _status_from_issues(issues)
    return GcsimWeaponReadinessAudit(
        status=status,
        ready=status == READINESS_READY,
        mapping=mapping,
        warnings=_dedupe_tuple(warnings),
        issues=tuple(issues),
    )


def audit_gcsim_artifact_readiness(
    artifact_build: GcsimArtifactBuildInput | Mapping[str, Any] | None,
) -> GcsimArtifactReadinessAudit:
    if artifact_build is None:
        issue = GcsimReadinessIssue(
            READINESS_MISSING_ARTIFACT_DATA,
            "artifact_build",
            "No artifact build/current equipment snapshot input was provided.",
        )
        return GcsimArtifactReadinessAudit(
            status=READINESS_MISSING_ARTIFACT_DATA,
            ready=False,
            issues=(issue,),
        )

    normalized = _artifact_build_input(artifact_build)
    warnings: list[str] = []
    issues: list[GcsimReadinessIssue] = []
    artifact_ids = {
        int(pos): int(artifact_id)
        for pos, artifact_id in normalized.artifact_ids_by_pos.items()
        if _optional_int(pos) in ARTIFACT_POSITIONS
        and _optional_int(artifact_id) is not None
    }
    missing_positions = tuple(
        sorted(
            {
                *normalized.missing_positions,
                *[pos for pos in ARTIFACT_POSITIONS if pos not in artifact_ids],
            }
        )
    )
    if missing_positions:
        issues.append(
            GcsimReadinessIssue(
                READINESS_MISSING_ARTIFACT_DATA,
                "artifact_build.missing_positions",
                "Artifact build is incomplete for future GCSIM add stats.",
            )
        )

    set_audits = tuple(
        audit_gcsim_artifact_set_readiness(active_set)
        for active_set in normalized.active_sets
    )
    for set_audit in set_audits:
        issues.extend(set_audit.issues)
        warnings.extend(set_audit.warnings)

    normalized_stats = normalize_artifact_build_snapshot_stats(
        {
            "build_id": None,
            "build_name": "",
            "stat_totals": list(normalized.stat_totals),
            "crit_value": None,
            "proc_count": None,
        }
    )
    add_stats = normalized_stats_to_gcsim_add_stats(normalized_stats)
    warnings.extend(normalized_stats.warnings)
    if not add_stats:
        warnings.append(WARNING_ARTIFACT_ADD_STATS_EMPTY)
        issues.append(
            GcsimReadinessIssue(
                READINESS_MISSING_ARTIFACT_DATA,
                "artifact_build.stat_totals",
                "No artifact stats could be mapped into GCSIM add stats.",
            )
        )

    status = _status_from_issues(issues)
    return GcsimArtifactReadinessAudit(
        status=status,
        ready=status == READINESS_READY,
        artifact_count=len(artifact_ids),
        missing_positions=missing_positions,
        add_stats=add_stats,
        normalized_stats=normalized_stats,
        set_audits=set_audits,
        warnings=_dedupe_tuple(warnings),
        issues=tuple(issues),
    )


def audit_gcsim_artifact_set_readiness(
    artifact_set: GcsimArtifactSetInput | Mapping[str, Any],
) -> GcsimArtifactSetReadinessAudit:
    normalized = _artifact_set_input(artifact_set)
    mapping = audit_mapping_ref(
        normalized.mapping,
        entity_type="artifact_set",
        project_id=normalized.set_uid,
        display_name=normalized.display_name,
    )
    warnings = list(mapping.warnings)
    issues = list(mapping.issues)
    if not mapping.ready:
        warnings.append(WARNING_ARTIFACT_SET_MAPPING_MISSING)
    status = _status_from_issues(issues)
    return GcsimArtifactSetReadinessAudit(
        status=status,
        ready=status == READINESS_READY,
        set_uid=normalized.set_uid,
        piece_count=normalized.piece_count,
        mapping=mapping,
        warnings=_dedupe_tuple(warnings),
        issues=tuple(issues),
    )


def audit_gcsim_talent_readiness(
    talents: GcsimTalentInput | Mapping[str, Any] | None,
) -> GcsimTalentReadinessAudit:
    if talents is None:
        issue = GcsimReadinessIssue(
            READINESS_MISSING_TALENT_DATA,
            "talents",
            "No account-observed talent input was provided.",
        )
        return GcsimTalentReadinessAudit(
            status=READINESS_MISSING_TALENT_DATA,
            ready=False,
            issues=(issue,),
        )

    normalized = _talent_input(talents)
    issues: list[GcsimReadinessIssue] = []
    warnings: list[str] = []
    if (
        normalized.normal is None
        or normalized.skill is None
        or normalized.burst is None
    ):
        issues.append(
            GcsimReadinessIssue(
                READINESS_MISSING_TALENT_DATA,
                "talents",
                "Normal/skill/burst talent levels must all be present.",
            )
        )
    if not normalized.source_order_confirmed:
        warnings.append(WARNING_TALENT_ORDER_UNCONFIRMED)
        issues.append(
            GcsimReadinessIssue(
                READINESS_MISSING_TALENT_DATA,
                "talents.source_order_confirmed",
                "Talent source order has not been confirmed.",
            )
        )
    status = _status_from_issues(issues)
    return GcsimTalentReadinessAudit(
        status=status,
        ready=status == READINESS_READY,
        warnings=_dedupe_tuple(warnings),
        issues=tuple(issues),
    )


def audit_mapping_ref(
    mapping: GcsimMappingRef | Mapping[str, Any] | None,
    *,
    entity_type: str,
    project_id: str = "",
    display_name: str = "",
) -> GcsimMappingAudit:
    normalized = _mapping_ref(mapping)
    warnings: list[str] = []
    issues: list[GcsimReadinessIssue] = []
    source = _text(normalized.source)
    gcsim_key = _text(normalized.gcsim_key)

    if normalized.ambiguous:
        issues.append(
            GcsimReadinessIssue(
                READINESS_AMBIGUOUS_MAPPING,
                f"{entity_type}.mapping",
                "GCSIM mapping is ambiguous.",
            )
        )
    if source in DISPLAY_NAME_MAPPING_SOURCES:
        warnings.append(WARNING_DISPLAY_NAME_ONLY_MAPPING)
        issues.append(
            GcsimReadinessIssue(
                READINESS_MISSING_MAPPING,
                f"{entity_type}.mapping",
                "Localized/display-name-only mapping is not a stable GCSIM key.",
            )
        )
    if not gcsim_key:
        issues.append(
            GcsimReadinessIssue(
                READINESS_MISSING_MAPPING,
                f"{entity_type}.mapping",
                "No explicit GCSIM key mapping was provided.",
            )
        )
    if gcsim_key and not source:
        warnings.append(WARNING_MAPPING_SOURCE_MISSING)

    status = _status_from_issues(issues)
    return GcsimMappingAudit(
        entity_type=entity_type,
        status=status,
        ready=status == READINESS_READY,
        project_id=_text(project_id),
        display_name=_text(display_name),
        gcsim_key=gcsim_key if status == READINESS_READY else "",
        source=source,
        warnings=_dedupe_tuple(warnings),
        issues=tuple(issues),
    )


def _team_input(value: GcsimTeamInput | Mapping[str, Any]) -> GcsimTeamInput:
    if isinstance(value, GcsimTeamInput):
        return value
    characters = value.get("characters") if isinstance(value, Mapping) else ()
    return GcsimTeamInput(
        characters=tuple(
            _character_input(item)
            for item in characters or ()
            if isinstance(item, (GcsimCharacterInput, Mapping))
        )
    )


def _character_input(value: GcsimCharacterInput | Mapping[str, Any]) -> GcsimCharacterInput:
    if isinstance(value, GcsimCharacterInput):
        return value
    mapping = value if isinstance(value, Mapping) else {}
    return GcsimCharacterInput(
        project_character_id=_text(_first_present(mapping, "project_character_id", "id", "character_id")),
        display_name=_text(_first_present(mapping, "display_name", "name")),
        level=_optional_int(mapping.get("level")),
        max_level=_optional_int(_first_present(mapping, "max_level", "level_cap")),
        constellation=_optional_int(mapping.get("constellation")),
        mapping=_mapping_ref(mapping.get("mapping") or mapping.get("gcsim_mapping")),
        weapon=_weapon_input_optional(mapping.get("weapon")),
        artifact_build=_artifact_build_input_optional(
            mapping.get("artifact_build") or mapping.get("artifacts")
        ),
        talents=_talent_input_optional(mapping.get("talents")),
        is_traveler=bool(mapping.get("is_traveler")),
    )


def _weapon_input_optional(value: Any) -> GcsimWeaponInput | None:
    if value is None:
        return None
    if isinstance(value, (GcsimWeaponInput, Mapping)):
        return _weapon_input(value)
    return None


def _weapon_input(value: GcsimWeaponInput | Mapping[str, Any]) -> GcsimWeaponInput:
    if isinstance(value, GcsimWeaponInput):
        return value
    mapping = value if isinstance(value, Mapping) else {}
    return GcsimWeaponInput(
        project_weapon_id=_text(_first_present(mapping, "project_weapon_id", "id", "weapon_id")),
        display_name=_text(_first_present(mapping, "display_name", "name")),
        level=_optional_int(mapping.get("level")),
        refinement=_optional_int(_first_present(mapping, "refinement", "affix_level")),
        mapping=_mapping_ref(mapping.get("mapping") or mapping.get("gcsim_mapping")),
    )


def _artifact_build_input_optional(value: Any) -> GcsimArtifactBuildInput | None:
    if value is None:
        return None
    if isinstance(value, (GcsimArtifactBuildInput, Mapping)):
        return _artifact_build_input(value)
    return None


def _artifact_build_input(
    value: GcsimArtifactBuildInput | Mapping[str, Any],
) -> GcsimArtifactBuildInput:
    if isinstance(value, GcsimArtifactBuildInput):
        return value
    mapping = value if isinstance(value, Mapping) else {}
    active_sets = mapping.get("active_sets") or mapping.get("active_set_bonuses") or ()
    return GcsimArtifactBuildInput(
        artifact_ids_by_pos=_artifact_ids_by_pos(mapping.get("artifact_ids_by_pos")),
        missing_positions=tuple(
            int(pos)
            for pos in (_optional_int(item) for item in mapping.get("missing_positions") or ())
            if pos in ARTIFACT_POSITIONS
        ),
        active_sets=tuple(
            _artifact_set_input(item)
            for item in active_sets
            if isinstance(item, (GcsimArtifactSetInput, Mapping))
        ),
        stat_totals=tuple(
            dict(item)
            for item in mapping.get("stat_totals") or ()
            if isinstance(item, Mapping)
        ),
    )


def _artifact_set_input(value: GcsimArtifactSetInput | Mapping[str, Any]) -> GcsimArtifactSetInput:
    if isinstance(value, GcsimArtifactSetInput):
        return value
    mapping = value if isinstance(value, Mapping) else {}
    return GcsimArtifactSetInput(
        set_uid=_text(mapping.get("set_uid")),
        display_name=_text(_first_present(mapping, "display_name", "set_name", "name")),
        piece_count=_optional_int(_first_present(mapping, "piece_count", "count")) or 0,
        mapping=_mapping_ref(mapping.get("mapping") or mapping.get("gcsim_mapping")),
    )


def _talent_input_optional(value: Any) -> GcsimTalentInput | None:
    if value is None:
        return None
    if isinstance(value, (GcsimTalentInput, Mapping)):
        return _talent_input(value)
    return None


def _talent_input(value: GcsimTalentInput | Mapping[str, Any]) -> GcsimTalentInput:
    if isinstance(value, GcsimTalentInput):
        return value
    mapping = value if isinstance(value, Mapping) else {}
    return GcsimTalentInput(
        normal=_optional_int(mapping.get("normal")),
        skill=_optional_int(mapping.get("skill")),
        burst=_optional_int(mapping.get("burst")),
        source_order_confirmed=bool(mapping.get("source_order_confirmed")),
    )


def _mapping_ref(value: GcsimMappingRef | Mapping[str, Any] | None) -> GcsimMappingRef:
    if isinstance(value, GcsimMappingRef):
        return value
    if not isinstance(value, Mapping):
        return GcsimMappingRef()
    return GcsimMappingRef(
        gcsim_key=_text(value.get("gcsim_key") or value.get("key")),
        source=_text(value.get("source")),
        ambiguous=bool(value.get("ambiguous")),
    )


def _artifact_ids_by_pos(value: Any) -> dict[int, int]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[int, int] = {}
    for pos, artifact_id in value.items():
        pos_int = _optional_int(pos)
        artifact_id_int = _optional_int(artifact_id)
        if pos_int in ARTIFACT_POSITIONS and artifact_id_int is not None:
            result[int(pos_int)] = int(artifact_id_int)
    return dict(sorted(result.items()))


def _looks_like_account_traveler(character: GcsimCharacterInput) -> bool:
    return _text(character.project_character_id) == "10000007" or _text(
        character.display_name
    ).casefold() == "traveler"


def _status_from_issues(issues: Iterable[GcsimReadinessIssue]) -> str:
    statuses = {issue.status for issue in issues}
    for status in STATUS_PRIORITY:
        if status in statuses:
            return status
    return READINESS_READY


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


def _dedupe_tuple(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return tuple(result)
