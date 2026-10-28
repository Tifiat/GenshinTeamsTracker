"""Pure GCSIM config block builders for prepared backend inputs.

This module is the first narrow config text boundary. It renders only one
character/equipment block from already-audited backend data. It does not read
UI state, infer localized names into GCSIM keys, generate a full sim config,
choose enemies, or run the engine.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from hoyolab_export.artifact_build_snapshot import (
    ArtifactBuildSnapshot,
    ArtifactStatTotalSnapshot,
)
from hoyolab_export.stat_normalization import (
    NormalizedStatBlock,
    normalize_artifact_build_snapshot_stats,
    normalized_stats_to_gcsim_add_stats,
)
from run_workspace.gcsim.config_level import (
    GcsimLevelResolution,
    STATUS_INVALID_LEVEL as LEVEL_STATUS_INVALID_LEVEL,
    STATUS_MISSING_LEVEL as LEVEL_STATUS_MISSING_LEVEL,
    STATUS_READY as LEVEL_STATUS_READY,
    resolve_gcsim_level_text,
)
from run_workspace.gcsim.config_readiness import (
    DISPLAY_NAME_MAPPING_SOURCES,
    GcsimArtifactBuildInput,
    GcsimArtifactSetInput,
    GcsimMappingRef,
    GcsimTalentInput,
    READINESS_AMBIGUOUS_MAPPING,
    READINESS_MISSING_ARTIFACT_DATA,
    READINESS_MISSING_MAPPING,
    READINESS_MISSING_TALENT_DATA,
    READINESS_MISSING_WEAPON,
    READINESS_UNSUPPORTED_TRAVELER,
    WARNING_DISPLAY_NAME_ONLY_MAPPING,
    WARNING_MAPPING_SOURCE_MISSING,
    WARNING_TALENT_ORDER_UNCONFIRMED,
    WARNING_TRAVELER_DEFERRED,
)
from run_workspace.gcsim.key_mapping import TRAVELER_PROJECT_CHARACTER_IDS


CONFIG_BLOCK_READY = "ready"
CONFIG_BLOCK_MISSING_LEVEL = "missing_level"
CONFIG_BLOCK_INVALID_LEVEL = "invalid_level"
CONFIG_BLOCK_MISSING_CONSTELLATION = "missing_constellation"
CONFIG_BLOCK_MISSING_REFINEMENT = "missing_refinement"
CONFIG_BLOCK_MISSING_ARTIFACT_STATS = "missing_artifact_stats"

WARNING_FORBIDDEN_ARTIFACT_STAT_SOURCE_IGNORED = (
    "forbidden_artifact_stat_source_ignored"
)
WARNING_ARTIFACT_SET_COUNT_BELOW_TWO_IGNORED = (
    "artifact_set_count_below_two_ignored"
)
WARNING_ARTIFACT_SET_COUNTS_MISSING = "artifact_set_counts_missing"

ADD_STATS_ORDER = (
    "hp",
    "atk",
    "def",
    "hp%",
    "atk%",
    "def%",
    "em",
    "er",
    "cr",
    "cd",
    "pyro%",
    "hydro%",
    "electro%",
    "cryo%",
    "anemo%",
    "geo%",
    "dendro%",
    "phys%",
    "heal",
)

FORBIDDEN_ARTIFACT_STAT_SOURCES = {
    "account_stat_sheet",
    "artifact_set_bonus",
    "character_base",
    "final_stats",
    "right_panel_total",
    "set_bonus",
    "weapon_base",
    "weapon_passive",
}

_STATUS_PRIORITY = (
    READINESS_UNSUPPORTED_TRAVELER,
    READINESS_AMBIGUOUS_MAPPING,
    READINESS_MISSING_MAPPING,
    CONFIG_BLOCK_INVALID_LEVEL,
    CONFIG_BLOCK_MISSING_LEVEL,
    CONFIG_BLOCK_MISSING_CONSTELLATION,
    READINESS_MISSING_WEAPON,
    CONFIG_BLOCK_MISSING_REFINEMENT,
    READINESS_MISSING_TALENT_DATA,
    READINESS_MISSING_ARTIFACT_DATA,
    CONFIG_BLOCK_MISSING_ARTIFACT_STATS,
)


@dataclass(frozen=True, slots=True)
class GcsimConfigBlockIssue:
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
class GcsimArtifactSetConfigInput:
    set_uid: str = ""
    display_name: str = ""
    count: int = 0
    mapping: GcsimMappingRef = field(default_factory=GcsimMappingRef)

    def to_dict(self) -> dict[str, Any]:
        return {
            "set_uid": self.set_uid,
            "display_name": self.display_name,
            "count": self.count,
            "mapping": self.mapping.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GcsimArtifactConfigInput:
    set_counts: tuple[GcsimArtifactSetConfigInput, ...] = ()
    stat_totals: tuple[ArtifactStatTotalSnapshot | Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "set_counts": [item.to_dict() for item in self.set_counts],
            "stat_totals": [_stat_total_to_dict(item) for item in self.stat_totals],
        }


@dataclass(frozen=True, slots=True)
class GcsimWeaponConfigInput:
    project_weapon_id: str = ""
    display_name: str = ""
    level: Any = None
    promote_level: Any = None
    level_resolution: GcsimLevelResolution | Mapping[str, Any] | None = None
    refinement: Any = None
    mapping: GcsimMappingRef = field(default_factory=GcsimMappingRef)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_weapon_id": self.project_weapon_id,
            "display_name": self.display_name,
            "level": self.level,
            "promote_level": self.promote_level,
            "level_resolution": (
                self.level_resolution.to_dict()
                if isinstance(self.level_resolution, GcsimLevelResolution)
                else dict(self.level_resolution or {})
            ),
            "refinement": self.refinement,
            "mapping": self.mapping.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GcsimCharacterConfigInput:
    project_character_id: str = ""
    display_name: str = ""
    level: Any = None
    promote_level: Any = None
    level_resolution: GcsimLevelResolution | Mapping[str, Any] | None = None
    constellation: Any = None
    mapping: GcsimMappingRef = field(default_factory=GcsimMappingRef)
    weapon: GcsimWeaponConfigInput | Mapping[str, Any] | None = None
    artifacts: GcsimArtifactConfigInput | Mapping[str, Any] | None = None
    talents: GcsimTalentInput | Mapping[str, Any] | None = None
    is_traveler: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_character_id": self.project_character_id,
            "display_name": self.display_name,
            "level": self.level,
            "promote_level": self.promote_level,
            "level_resolution": (
                self.level_resolution.to_dict()
                if isinstance(self.level_resolution, GcsimLevelResolution)
                else dict(self.level_resolution or {})
            ),
            "constellation": self.constellation,
            "mapping": self.mapping.to_dict(),
            "weapon": (
                self.weapon.to_dict()
                if isinstance(self.weapon, GcsimWeaponConfigInput)
                else dict(self.weapon or {})
            ),
            "artifacts": (
                self.artifacts.to_dict()
                if isinstance(self.artifacts, GcsimArtifactConfigInput)
                else dict(self.artifacts or {})
            ),
            "talents": (
                self.talents.to_dict()
                if isinstance(self.talents, GcsimTalentInput)
                else dict(self.talents or {})
            ),
            "is_traveler": self.is_traveler,
        }


@dataclass(frozen=True, slots=True)
class GcsimCharacterConfigBlock:
    status: str
    ready: bool
    lines: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    issues: tuple[GcsimConfigBlockIssue, ...] = ()
    add_stats: Mapping[str, float] = field(default_factory=dict)
    normalized_stats: NormalizedStatBlock | None = None
    character_level: GcsimLevelResolution | None = None
    weapon_level: GcsimLevelResolution | None = None

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "lines": list(self.lines),
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
            "add_stats": dict(self.add_stats),
            "normalized_stats": (
                self.normalized_stats.to_dict()
                if self.normalized_stats is not None
                else None
            ),
            "character_level": (
                self.character_level.to_dict()
                if self.character_level is not None
                else None
            ),
            "weapon_level": (
                self.weapon_level.to_dict()
                if self.weapon_level is not None
                else None
            ),
        }


def build_gcsim_character_config_block(
    character: GcsimCharacterConfigInput | Mapping[str, Any],
) -> GcsimCharacterConfigBlock:
    normalized = _character_input(character)
    warnings: list[str] = []
    issues: list[GcsimConfigBlockIssue] = []

    if normalized.is_traveler or _looks_like_traveler(normalized):
        warnings.append(WARNING_TRAVELER_DEFERRED)
        issues.append(
            _issue(
                READINESS_UNSUPPORTED_TRAVELER,
                "character",
                "Traveler variant selection is still deferred.",
            )
        )

    character_key = _require_mapping(
        normalized.mapping,
        field="character.mapping",
        entity_type="character",
        issues=issues,
        warnings=warnings,
    )
    character_level = _resolve_level(
        normalized.level,
        normalized.promote_level,
        normalized.level_resolution,
    )
    _require_level(
        character_level,
        field="character.level",
        issues=issues,
        warnings=warnings,
    )

    constellation = _optional_int(normalized.constellation)
    if constellation is None:
        issues.append(
            _issue(
                CONFIG_BLOCK_MISSING_CONSTELLATION,
                "character.constellation",
                "Character constellation is required for GCSIM config text.",
            )
        )

    talents = _talent_input_optional(normalized.talents)
    if talents is None:
        issues.append(
            _issue(
                READINESS_MISSING_TALENT_DATA,
                "talents",
                "Normal/skill/burst talent levels are required.",
            )
        )
    else:
        _require_talents(talents, issues=issues, warnings=warnings)

    weapon = _weapon_input_optional(normalized.weapon)
    weapon_key = ""
    weapon_level: GcsimLevelResolution | None = None
    refinement: int | None = None
    if weapon is None:
        issues.append(
            _issue(
                READINESS_MISSING_WEAPON,
                "weapon",
                "Equipped weapon data is required.",
            )
        )
    else:
        weapon_key = _require_mapping(
            weapon.mapping,
            field="weapon.mapping",
            entity_type="weapon",
            issues=issues,
            warnings=warnings,
        )
        weapon_level = _resolve_level(
            weapon.level,
            weapon.promote_level,
            weapon.level_resolution,
        )
        _require_level(
            weapon_level,
            field="weapon.level",
            issues=issues,
            warnings=warnings,
        )
        refinement = _optional_int(weapon.refinement)
        if refinement is None:
            issues.append(
                _issue(
                    CONFIG_BLOCK_MISSING_REFINEMENT,
                    "weapon.refinement",
                    "Weapon refinement is required.",
                )
            )

    artifacts = _artifact_config_input_optional(normalized.artifacts)
    set_lines: list[str] = []
    add_stats: dict[str, float] = {}
    normalized_stats: NormalizedStatBlock | None = None
    if artifacts is None:
        issues.append(
            _issue(
                READINESS_MISSING_ARTIFACT_DATA,
                "artifacts",
                "Artifact set counts and artifact stat totals are required.",
            )
        )
    else:
        set_lines = _artifact_set_lines(
            character_key,
            artifacts.set_counts,
            issues=issues,
            warnings=warnings,
        )
        normalized_stats, add_stats = _artifact_add_stats(
            artifacts.stat_totals,
            issues=issues,
            warnings=warnings,
        )

    status = _status_from_issues(issues)
    if status != CONFIG_BLOCK_READY:
        return GcsimCharacterConfigBlock(
            status=status,
            ready=False,
            warnings=_dedupe_tuple(warnings),
            issues=tuple(issues),
            add_stats=add_stats,
            normalized_stats=normalized_stats,
            character_level=character_level,
            weapon_level=weapon_level,
        )

    assert talents is not None
    assert weapon_level is not None
    assert refinement is not None
    lines = [
        (
            f"{character_key} char lvl={character_level.gcsim_level_text} "
            f"cons={constellation} "
            f"talent={talents.normal},{talents.skill},{talents.burst};"
        ),
        (
            f"{character_key} add weapon={_quote_gcsim_string(weapon_key)} "
            f"refine={refinement} lvl={weapon_level.gcsim_level_text};"
        ),
        *set_lines,
        f"{character_key} add stats {_format_add_stats(add_stats)};",
    ]
    return GcsimCharacterConfigBlock(
        status=CONFIG_BLOCK_READY,
        ready=True,
        lines=tuple(lines),
        warnings=_dedupe_tuple(warnings),
        issues=(),
        add_stats=add_stats,
        normalized_stats=normalized_stats,
        character_level=character_level,
        weapon_level=weapon_level,
    )


def render_gcsim_character_config_block(
    character: GcsimCharacterConfigInput | Mapping[str, Any],
) -> str:
    return build_gcsim_character_config_block(character).text


def _artifact_set_lines(
    character_key: str,
    set_counts: Iterable[GcsimArtifactSetConfigInput],
    *,
    issues: list[GcsimConfigBlockIssue],
    warnings: list[str],
) -> list[str]:
    set_counts = tuple(set_counts)
    if not set_counts:
        warnings.append(WARNING_ARTIFACT_SET_COUNTS_MISSING)
        issues.append(
            _issue(
                READINESS_MISSING_ARTIFACT_DATA,
                "artifacts.set_counts",
                "Artifact set counts are required before rendering config text.",
            )
        )
        return []

    lines: list[str] = []
    for index, set_count in enumerate(set_counts):
        count = _optional_int(set_count.count) or 0
        if count < 2:
            warnings.append(WARNING_ARTIFACT_SET_COUNT_BELOW_TWO_IGNORED)
            continue
        set_key = _require_mapping(
            set_count.mapping,
            field=f"artifact_sets[{index}].mapping",
            entity_type="artifact_set",
            issues=issues,
            warnings=warnings,
        )
        if set_key:
            lines.append(
                f"{character_key} add set={_quote_gcsim_string(set_key)} count={count};"
            )
    return lines


def _artifact_add_stats(
    stat_totals: Iterable[ArtifactStatTotalSnapshot | Mapping[str, Any]],
    *,
    issues: list[GcsimConfigBlockIssue],
    warnings: list[str],
) -> tuple[NormalizedStatBlock, dict[str, float]]:
    filtered_stats = _artifact_only_stat_totals(stat_totals, warnings=warnings)
    normalized = normalize_artifact_build_snapshot_stats(
        {
            "build_id": None,
            "build_name": "",
            "stat_totals": list(filtered_stats),
            "crit_value": None,
            "proc_count": None,
        }
    )
    warnings.extend(normalized.warnings)
    add_stats = _finite_add_stats(normalized_stats_to_gcsim_add_stats(normalized))
    if not add_stats:
        issues.append(
            _issue(
                CONFIG_BLOCK_MISSING_ARTIFACT_STATS,
                "artifacts.stat_totals",
                "No artifact stat total could be mapped into GCSIM add stats.",
            )
        )
    return normalized, add_stats


def _artifact_only_stat_totals(
    stat_totals: Iterable[ArtifactStatTotalSnapshot | Mapping[str, Any]],
    *,
    warnings: list[str],
) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for item in stat_totals:
        record = _stat_total_to_dict(item)
        source = _text(
            _first_present(
                record,
                "source",
                "source_kind",
                "source_scope",
                "stat_source",
            )
        ).casefold()
        if source in FORBIDDEN_ARTIFACT_STAT_SOURCES:
            warnings.append(WARNING_FORBIDDEN_ARTIFACT_STAT_SOURCE_IGNORED)
            continue
        result.append(record)
    return tuple(result)


def _require_mapping(
    mapping: GcsimMappingRef,
    *,
    field: str,
    entity_type: str,
    issues: list[GcsimConfigBlockIssue],
    warnings: list[str],
) -> str:
    source = _text(mapping.source)
    gcsim_key = _text(mapping.gcsim_key)

    if mapping.ambiguous:
        issues.append(
            _issue(
                READINESS_AMBIGUOUS_MAPPING,
                field,
                f"{entity_type} GCSIM mapping is ambiguous.",
            )
        )
    if source.casefold() in DISPLAY_NAME_MAPPING_SOURCES:
        warnings.append(WARNING_DISPLAY_NAME_ONLY_MAPPING)
        issues.append(
            _issue(
                READINESS_MISSING_MAPPING,
                field,
                f"{entity_type} display-name-only mapping is not stable.",
            )
        )
    if not gcsim_key:
        issues.append(
            _issue(
                READINESS_MISSING_MAPPING,
                field,
                f"{entity_type} GCSIM key mapping is missing.",
            )
        )
    if gcsim_key and not source:
        warnings.append(WARNING_MAPPING_SOURCE_MISSING)

    return gcsim_key if not any(issue.field == field for issue in issues) else ""


def _require_level(
    resolution: GcsimLevelResolution,
    *,
    field: str,
    issues: list[GcsimConfigBlockIssue],
    warnings: list[str],
) -> None:
    warnings.extend(resolution.warnings)
    if resolution.status == LEVEL_STATUS_READY and resolution.gcsim_level_text:
        return
    if resolution.status == LEVEL_STATUS_INVALID_LEVEL:
        issues.append(
            _issue(
                CONFIG_BLOCK_INVALID_LEVEL,
                field,
                "Level input is invalid for GCSIM config text.",
            )
        )
        return
    issues.append(
        _issue(
            CONFIG_BLOCK_MISSING_LEVEL,
            field,
            "Level/promote data or a ready level helper result is required.",
        )
    )


def _require_talents(
    talents: GcsimTalentInput,
    *,
    issues: list[GcsimConfigBlockIssue],
    warnings: list[str],
) -> None:
    if talents.normal is None or talents.skill is None or talents.burst is None:
        issues.append(
            _issue(
                READINESS_MISSING_TALENT_DATA,
                "talents",
                "Normal/skill/burst talent levels are all required.",
            )
        )
    if not talents.source_order_confirmed:
        warnings.append(WARNING_TALENT_ORDER_UNCONFIRMED)
        issues.append(
            _issue(
                READINESS_MISSING_TALENT_DATA,
                "talents.source_order_confirmed",
                "Talent source order must be confirmed before rendering.",
            )
        )


def _format_add_stats(add_stats: Mapping[str, float]) -> str:
    keys = [
        *[key for key in ADD_STATS_ORDER if key in add_stats],
        *sorted(key for key in add_stats if key not in ADD_STATS_ORDER),
    ]
    return " ".join(f"{key}={_format_number(add_stats[key])}" for key in keys)


def _finite_add_stats(add_stats: Mapping[str, float]) -> dict[str, float]:
    result: dict[str, float] = {}
    for key, value in add_stats.items():
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(number):
            continue
        result[_text(key)] = result.get(_text(key), 0.0) + number
    return result


def _format_number(value: Any) -> str:
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return format(number, ".12g")


def _quote_gcsim_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _character_input(
    value: GcsimCharacterConfigInput | Mapping[str, Any],
) -> GcsimCharacterConfigInput:
    if isinstance(value, GcsimCharacterConfigInput):
        return value
    mapping = value if isinstance(value, Mapping) else {}
    return GcsimCharacterConfigInput(
        project_character_id=_text(
            _first_present(mapping, "project_character_id", "character_id", "id")
        ),
        display_name=_text(_first_present(mapping, "display_name", "name")),
        level=_first_present(mapping, "level", "current_level"),
        promote_level=_first_present(mapping, "promote_level", "promote"),
        level_resolution=_first_present(
            mapping,
            "level_resolution",
            "level_helper_result",
        ),
        constellation=_first_present(mapping, "constellation", "cons"),
        mapping=_mapping_ref(
            mapping.get("mapping")
            or mapping.get("gcsim_mapping")
            or _inline_mapping(mapping)
        ),
        weapon=_first_present(mapping, "weapon", "equipped_weapon"),
        artifacts=_first_present(mapping, "artifacts", "artifact_build"),
        talents=mapping.get("talents"),
        is_traveler=bool(mapping.get("is_traveler")),
    )


def _weapon_input_optional(value: Any) -> GcsimWeaponConfigInput | None:
    if value is None:
        return None
    if isinstance(value, GcsimWeaponConfigInput):
        return value
    if not isinstance(value, Mapping):
        return None
    return GcsimWeaponConfigInput(
        project_weapon_id=_text(
            _first_present(value, "project_weapon_id", "weapon_id", "id")
        ),
        display_name=_text(_first_present(value, "display_name", "name")),
        level=_first_present(value, "level", "current_level"),
        promote_level=_first_present(value, "promote_level", "promote"),
        level_resolution=_first_present(
            value,
            "level_resolution",
            "level_helper_result",
        ),
        refinement=_first_present(value, "refinement", "refine", "affix_level"),
        mapping=_mapping_ref(
            value.get("mapping")
            or value.get("gcsim_mapping")
            or _inline_mapping(value)
        ),
    )


def _artifact_config_input_optional(value: Any) -> GcsimArtifactConfigInput | None:
    if value is None:
        return None
    if isinstance(value, GcsimArtifactConfigInput):
        return value
    if isinstance(value, GcsimArtifactBuildInput):
        return GcsimArtifactConfigInput(
            set_counts=tuple(
                _artifact_set_input(item)
                for item in value.active_sets
            ),
            stat_totals=value.stat_totals,
        )
    if isinstance(value, ArtifactBuildSnapshot):
        return GcsimArtifactConfigInput(
            set_counts=tuple(
                GcsimArtifactSetConfigInput(
                    set_uid=item.set_uid,
                    display_name=item.set_name,
                    count=item.count,
                )
                for item in value.set_counts
            ),
            stat_totals=value.stat_totals,
        )
    if not isinstance(value, Mapping):
        return None

    sets = (
        value.get("set_counts")
        or value.get("active_sets")
        or value.get("active_set_bonuses")
        or value.get("set_bonuses")
        or ()
    )
    stat_totals = value.get("stat_totals") or value.get("total_stats") or ()
    return GcsimArtifactConfigInput(
        set_counts=tuple(
            _artifact_set_input(item)
            for item in sets
            if isinstance(item, (GcsimArtifactSetConfigInput, GcsimArtifactSetInput, Mapping))
        ),
        stat_totals=tuple(
            item
            for item in stat_totals
            if isinstance(item, (ArtifactStatTotalSnapshot, Mapping))
        ),
    )


def _artifact_set_input(
    value: GcsimArtifactSetConfigInput | GcsimArtifactSetInput | Mapping[str, Any],
) -> GcsimArtifactSetConfigInput:
    if isinstance(value, GcsimArtifactSetConfigInput):
        return value
    if isinstance(value, GcsimArtifactSetInput):
        return GcsimArtifactSetConfigInput(
            set_uid=value.set_uid,
            display_name=value.display_name,
            count=value.piece_count,
            mapping=value.mapping,
        )
    return GcsimArtifactSetConfigInput(
        set_uid=_text(_first_present(value, "set_uid", "project_id", "id")),
        display_name=_text(_first_present(value, "display_name", "set_name", "name")),
        count=_optional_int(
            _first_present(value, "count", "piece_count", "owned_count")
        )
        or 0,
        mapping=_mapping_ref(
            value.get("mapping")
            or value.get("gcsim_mapping")
            or _inline_mapping(value)
        ),
    )


def _talent_input_optional(value: Any) -> GcsimTalentInput | None:
    if value is None:
        return None
    if isinstance(value, GcsimTalentInput):
        return value
    if not isinstance(value, Mapping):
        return None
    return GcsimTalentInput(
        normal=_optional_int(value.get("normal")),
        skill=_optional_int(value.get("skill")),
        burst=_optional_int(value.get("burst")),
        source_order_confirmed=bool(value.get("source_order_confirmed")),
    )


def _mapping_ref(value: GcsimMappingRef | Mapping[str, Any] | None) -> GcsimMappingRef:
    if isinstance(value, GcsimMappingRef):
        return value
    if not isinstance(value, Mapping):
        return GcsimMappingRef()
    return GcsimMappingRef(
        gcsim_key=_text(value.get("gcsim_key") or value.get("key")),
        source=_text(value.get("source") or value.get("source_kind")),
        ambiguous=bool(value.get("ambiguous")),
    )


def _inline_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    if "gcsim_key" not in mapping and "key" not in mapping:
        return {}
    return {
        "gcsim_key": mapping.get("gcsim_key") or mapping.get("key"),
        "source": mapping.get("source") or mapping.get("source_kind"),
        "ambiguous": mapping.get("ambiguous"),
    }


def _resolve_level(
    level: Any,
    promote_level: Any,
    resolution: GcsimLevelResolution | Mapping[str, Any] | None,
) -> GcsimLevelResolution:
    if isinstance(resolution, GcsimLevelResolution):
        return resolution
    if isinstance(resolution, Mapping):
        status = _text(resolution.get("status"))
        level_text = _text(
            resolution.get("gcsim_level_text") or resolution.get("level_text")
        )
        if status or level_text:
            return GcsimLevelResolution(
                status=status or (
                    LEVEL_STATUS_READY if level_text else LEVEL_STATUS_MISSING_LEVEL
                ),
                current_level=_optional_int(resolution.get("current_level")),
                max_level=_optional_int(resolution.get("max_level")),
                gcsim_level_text=level_text,
                phase_source=_text(resolution.get("phase_source")),
                warnings=_text_tuple(resolution.get("warnings")),
            )
    return resolve_gcsim_level_text(level, promote_level)


def _looks_like_traveler(character: GcsimCharacterConfigInput) -> bool:
    normalized_name = _text(character.display_name).casefold()
    return (
        _text(character.project_character_id) in TRAVELER_PROJECT_CHARACTER_IDS
        or normalized_name == "traveler"
        or normalized_name.startswith("traveler")
    )


def _status_from_issues(issues: Iterable[GcsimConfigBlockIssue]) -> str:
    statuses = {issue.status for issue in issues}
    for status in _STATUS_PRIORITY:
        if status in statuses:
            return status
    return CONFIG_BLOCK_READY


def _issue(status: str, field: str, message: str) -> GcsimConfigBlockIssue:
    return GcsimConfigBlockIssue(status=status, field=field, message=message)


def _stat_total_to_dict(
    item: ArtifactStatTotalSnapshot | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(item, ArtifactStatTotalSnapshot):
        return item.to_dict()
    return dict(item)


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
