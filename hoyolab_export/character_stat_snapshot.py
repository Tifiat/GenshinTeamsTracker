from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from .artifact_build_snapshot import ArtifactBuildSnapshot, build_artifact_build_snapshot
from .catalog_mapping import normalize_catalog_name
from .catalog_sanity import (
    DEFAULT_SPECIAL_TRAVELER_NAMES,
    STATUS_FUTURE_PENDING_STATS,
    STATUS_SPECIAL_DEFERRED,
    STATUS_STATS_UNAVAILABLE,
    WARNING_TRAVELER_SPECIAL_DEFERRED,
)
from .character_stats_catalog import (
    DEFAULT_BASE_STAT_ASSUMPTIONS,
    CharacterBaseStatRow,
    CharacterBaseStatsEntry,
    StatValuePair,
)
from .weapon_stats_catalog import WeaponAtkValuePair, WeaponStatsEntry


CHARACTER_STAT_SNAPSHOT_SCHEMA_VERSION = 1

SNAPSHOT_STATUS_READY = "ready"
SNAPSHOT_STATUS_PARTIAL = "partial"
SNAPSHOT_STATUS_UNSUPPORTED = "unsupported"

VALUE_SELECTION_BEFORE = "before"
VALUE_SELECTION_AFTER = "after"
VALUE_SELECTION_SINGLE = "single"
VALUE_SELECTION_AMBIGUOUS = "ambiguous"
VALUE_SELECTION_UNAVAILABLE = "unavailable"

WARNING_ARTIFACT_SUMMARY_MISSING = "artifact_summary_missing"
WARNING_ASCENSION_PHASE_UNKNOWN = "ascension_phase_unknown"
WARNING_CHARACTER_ASCENSION_PHASE_ASSUMED = "character_ascension_phase_assumed"
WARNING_CHARACTER_STATS_UNAVAILABLE = "character_stats_unavailable"
WARNING_CONDITIONAL_SET_BONUSES_NOT_INCLUDED = "conditional_set_bonuses_not_included"
WARNING_FINAL_TOTALS_NOT_COMPUTED = "final_totals_not_computed"
WARNING_INTERPOLATION_NOT_IMPLEMENTED = "interpolation_not_implemented"
WARNING_LEVEL_95_100_FALLBACK_TO_90 = "level_95_100_fallback_to_90"
WARNING_LEVEL_MISSING = "level_missing"
WARNING_LEVEL_ROW_UNAVAILABLE = "level_row_unavailable"
WARNING_SET_BONUS_FORMULAS_NOT_INCLUDED = "set_bonus_formulas_not_included"
WARNING_WEAPON_PASSIVE_NOT_INCLUDED = "weapon_passive_not_included"
WARNING_WEAPON_STATS_UNAVAILABLE = "weapon_stats_unavailable"

_ASCENSION_BREAKPOINTS = {
    20: (0, 1),
    40: (1, 2),
    50: (2, 3),
    60: (3, 4),
    70: (4, 5),
    80: (5, 6),
}
_LEVEL_95_100_FALLBACK_LEVELS = {95, 100}


@dataclass(frozen=True, slots=True)
class SnapshotAccountCharacter:
    id: str = ""
    name: str = ""
    level: int | None = None
    promote_level: int | None = None
    element: str = ""
    rarity: int | None = None
    constellation: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level,
            "promote_level": self.promote_level,
            "element": self.element,
            "rarity": self.rarity,
            "constellation": self.constellation,
        }


@dataclass(frozen=True, slots=True)
class SnapshotAccountWeapon:
    id: str = ""
    name: str = ""
    level: int | None = None
    promote_level: int | None = None
    rarity: int | None = None
    refinement: int | None = None
    weapon_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level,
            "promote_level": self.promote_level,
            "rarity": self.rarity,
            "refinement": self.refinement,
            "weapon_type": self.weapon_type,
        }


@dataclass(frozen=True, slots=True)
class SelectedStatValue:
    before: str | None = None
    after: str | None = None
    selected: str | None = None
    selection: str = VALUE_SELECTION_UNAVAILABLE
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "before": self.before,
            "after": self.after,
            "selected": self.selected,
            "selection": self.selection,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class CharacterBaseStatContribution:
    source_entry_id: str
    source_name: str
    source_lang: str
    account_level: int | None
    promote_level: int | None
    selected_level_key: str = ""
    base_hp: SelectedStatValue = field(default_factory=SelectedStatValue)
    base_atk: SelectedStatValue = field(default_factory=SelectedStatValue)
    base_def: SelectedStatValue = field(default_factory=SelectedStatValue)
    ascension_bonus_stat_type: str = ""
    ascension_bonus: SelectedStatValue = field(default_factory=SelectedStatValue)
    default_base_stat_assumptions: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_BASE_STAT_ASSUMPTIONS)
    )
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_entry_id": self.source_entry_id,
            "source_name": self.source_name,
            "source_lang": self.source_lang,
            "account_level": self.account_level,
            "promote_level": self.promote_level,
            "selected_level_key": self.selected_level_key,
            "base_hp": self.base_hp.to_dict(),
            "base_atk": self.base_atk.to_dict(),
            "base_def": self.base_def.to_dict(),
            "ascension_bonus_stat_type": self.ascension_bonus_stat_type,
            "ascension_bonus": self.ascension_bonus.to_dict(),
            "default_base_stat_assumptions": dict(self.default_base_stat_assumptions),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class WeaponStatContribution:
    source_entry_id: str
    source_name: str
    source_lang: str
    account_level: int | None
    promote_level: int | None
    refinement: int | None
    selected_level_key: str = ""
    base_atk: SelectedStatValue = field(default_factory=SelectedStatValue)
    secondary_stat_type: str = ""
    secondary_stat_value: str | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_entry_id": self.source_entry_id,
            "source_name": self.source_name,
            "source_lang": self.source_lang,
            "account_level": self.account_level,
            "promote_level": self.promote_level,
            "refinement": self.refinement,
            "selected_level_key": self.selected_level_key,
            "base_atk": self.base_atk.to_dict(),
            "secondary_stat_type": self.secondary_stat_type,
            "secondary_stat_value": self.secondary_stat_value,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class ArtifactStatContribution:
    summary: dict[str, Any] | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class CharacterStatSnapshot:
    schema_version: int
    status: str
    account_character: SnapshotAccountCharacter
    account_weapon: SnapshotAccountWeapon | None = None
    character_base: CharacterBaseStatContribution | None = None
    weapon: WeaponStatContribution | None = None
    artifact: ArtifactStatContribution | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "account_character": self.account_character.to_dict(),
            "account_weapon": (
                self.account_weapon.to_dict()
                if self.account_weapon is not None
                else None
            ),
            "character_base": (
                self.character_base.to_dict()
                if self.character_base is not None
                else None
            ),
            "weapon": self.weapon.to_dict() if self.weapon is not None else None,
            "artifact": self.artifact.to_dict() if self.artifact is not None else None,
            "warnings": list(self.warnings),
        }


def build_character_stat_snapshot(
    *,
    account_character: Mapping[str, Any],
    character_stats_entry: CharacterBaseStatsEntry | None = None,
    account_weapon: Mapping[str, Any] | None = None,
    weapon_stats_entry: WeaponStatsEntry | None = None,
    artifact_summary: Mapping[str, Any] | None = None,
    character_readiness_status: str | None = None,
) -> CharacterStatSnapshot:
    character_ref = account_character_ref(account_character)
    weapon_ref = account_weapon_ref(account_weapon) if account_weapon is not None else None
    warnings: list[str] = [WARNING_FINAL_TOTALS_NOT_COMPUTED]

    if _is_special_traveler(character_ref) or character_readiness_status == STATUS_SPECIAL_DEFERRED:
        warnings.append(WARNING_TRAVELER_SPECIAL_DEFERRED)
        return CharacterStatSnapshot(
            schema_version=CHARACTER_STAT_SNAPSHOT_SCHEMA_VERSION,
            status=SNAPSHOT_STATUS_UNSUPPORTED,
            account_character=character_ref,
            account_weapon=weapon_ref,
            artifact=_artifact_contribution(artifact_summary),
            warnings=tuple(_dedupe(warnings)),
        )

    character_base = build_character_base_stat_contribution(
        character_stats_entry,
        account_level=character_ref.level,
        promote_level=character_ref.promote_level,
    )
    weapon = build_weapon_stat_contribution(
        weapon_stats_entry,
        account_level=weapon_ref.level if weapon_ref is not None else None,
        promote_level=weapon_ref.promote_level if weapon_ref is not None else None,
        refinement=weapon_ref.refinement if weapon_ref is not None else None,
    )
    artifact = _artifact_contribution(artifact_summary)

    warnings.extend(character_base.warnings)
    warnings.extend(weapon.warnings)
    warnings.extend(artifact.warnings)

    status = SNAPSHOT_STATUS_READY
    if any(
        warning in warnings
        for warning in (
            WARNING_CHARACTER_STATS_UNAVAILABLE,
            WARNING_WEAPON_STATS_UNAVAILABLE,
            WARNING_LEVEL_MISSING,
            WARNING_LEVEL_ROW_UNAVAILABLE,
            WARNING_LEVEL_95_100_FALLBACK_TO_90,
            WARNING_INTERPOLATION_NOT_IMPLEMENTED,
            WARNING_ASCENSION_PHASE_UNKNOWN,
            WARNING_ARTIFACT_SUMMARY_MISSING,
        )
    ):
        status = SNAPSHOT_STATUS_PARTIAL

    return CharacterStatSnapshot(
        schema_version=CHARACTER_STAT_SNAPSHOT_SCHEMA_VERSION,
        status=status,
        account_character=character_ref,
        account_weapon=weapon_ref,
        character_base=character_base,
        weapon=weapon,
        artifact=artifact,
        warnings=tuple(_dedupe(warnings)),
    )


def build_character_base_stat_contribution(
    entry: CharacterBaseStatsEntry | None,
    *,
    account_level: int | None,
    promote_level: int | None = None,
) -> CharacterBaseStatContribution:
    warnings: list[str] = []
    if entry is None or not entry.rows:
        warnings.append(WARNING_CHARACTER_STATS_UNAVAILABLE)
        if account_level is None:
            warnings.append(WARNING_LEVEL_MISSING)
        return CharacterBaseStatContribution(
            source_entry_id=entry.entry_page_id if entry is not None else "",
            source_name=entry.name if entry is not None else "",
            source_lang=entry.lang if entry is not None else "",
            account_level=account_level,
            promote_level=promote_level,
            warnings=tuple(_dedupe(warnings)),
        )

    row = _find_row_for_level(entry.rows, account_level)
    fallback_to_90 = False
    if row is None and account_level in _LEVEL_95_100_FALLBACK_LEVELS:
        row = _find_row_for_level(entry.rows, 90)
        if row is not None:
            fallback_to_90 = True
            warnings.append(WARNING_LEVEL_95_100_FALLBACK_TO_90)

    if account_level is None:
        warnings.append(WARNING_LEVEL_MISSING)
    if row is None:
        warnings.append(WARNING_LEVEL_ROW_UNAVAILABLE)
        warnings.append(WARNING_INTERPOLATION_NOT_IMPLEMENTED)
        return CharacterBaseStatContribution(
            source_entry_id=entry.entry_page_id,
            source_name=entry.name,
            source_lang=entry.lang,
            account_level=account_level,
            promote_level=promote_level,
            warnings=tuple(_dedupe(warnings)),
        )

    if fallback_to_90:
        phase, phase_warning = VALUE_SELECTION_BEFORE, None
    else:
        phase, phase_warning = _character_phase_for_level(account_level, promote_level)
    values = [
        _select_pair(row.base_hp, phase=phase),
        _select_pair(row.base_atk, phase=phase),
        _select_pair(row.base_def, phase=phase),
        _select_pair(row.ascension_bonus, phase=phase),
    ]
    if phase_warning and _character_row_has_before_after(row):
        warnings.append(phase_warning)
    for value in values:
        warnings.extend(value.warnings)

    return CharacterBaseStatContribution(
        source_entry_id=entry.entry_page_id,
        source_name=entry.name,
        source_lang=entry.lang,
        account_level=account_level,
        promote_level=promote_level,
        selected_level_key=row.level_key,
        base_hp=values[0],
        base_atk=values[1],
        base_def=values[2],
        ascension_bonus_stat_type=row.ascension_bonus_stat_type,
        ascension_bonus=values[3],
        warnings=tuple(_dedupe(warnings)),
    )


def build_weapon_stat_contribution(
    entry: WeaponStatsEntry | None,
    *,
    account_level: int | None,
    promote_level: int | None = None,
    refinement: int | None = None,
) -> WeaponStatContribution:
    warnings: list[str] = []
    if entry is None or not entry.rows:
        warnings.append(WARNING_WEAPON_STATS_UNAVAILABLE)
        if account_level is None:
            warnings.append(WARNING_LEVEL_MISSING)
        return WeaponStatContribution(
            source_entry_id=entry.entry_page_id if entry is not None else "",
            source_name=entry.name if entry is not None else "",
            source_lang=entry.lang if entry is not None else "",
            account_level=account_level,
            promote_level=promote_level,
            refinement=refinement,
            warnings=tuple(_dedupe(warnings)),
        )

    if entry.reference_info.passive_fields:
        warnings.append(WARNING_WEAPON_PASSIVE_NOT_INCLUDED)

    row = _find_row_for_level(entry.rows, account_level)
    if account_level is None:
        warnings.append(WARNING_LEVEL_MISSING)
    if row is None:
        warnings.append(WARNING_LEVEL_ROW_UNAVAILABLE)
        warnings.append(WARNING_INTERPOLATION_NOT_IMPLEMENTED)
        return WeaponStatContribution(
            source_entry_id=entry.entry_page_id,
            source_name=entry.name,
            source_lang=entry.lang,
            account_level=account_level,
            promote_level=promote_level,
            refinement=refinement,
            warnings=tuple(_dedupe(warnings)),
        )

    phase = _phase_for_level(account_level, promote_level)
    base_atk = _select_weapon_pair(row.base_atk, phase=phase)
    warnings.extend(base_atk.warnings)

    return WeaponStatContribution(
        source_entry_id=entry.entry_page_id,
        source_name=entry.name,
        source_lang=entry.lang,
        account_level=account_level,
        promote_level=promote_level,
        refinement=refinement,
        selected_level_key=row.level_key,
        base_atk=base_atk,
        secondary_stat_type=row.secondary_stat_type,
        secondary_stat_value=row.secondary_stat_value,
        warnings=tuple(_dedupe(warnings)),
    )


def account_character_ref(record: Mapping[str, Any]) -> SnapshotAccountCharacter:
    return SnapshotAccountCharacter(
        id=_text(record.get("id")),
        name=_text(record.get("name")),
        level=_optional_int(record.get("level")),
        promote_level=_optional_int(
            _first_present(record, "promote_level", "ascension", "ascension_phase")
        ),
        element=_text(record.get("element")),
        rarity=_optional_int(record.get("rarity")),
        constellation=_optional_int(
            _first_present(record, "constellation", "actived_constellation_num")
        ),
    )


def account_weapon_ref(record: Mapping[str, Any] | None) -> SnapshotAccountWeapon:
    record = record or {}
    return SnapshotAccountWeapon(
        id=_text(record.get("id")),
        name=_text(record.get("name")),
        level=_optional_int(record.get("level")),
        promote_level=_optional_int(
            _first_present(record, "promote_level", "ascension", "ascension_phase")
        ),
        rarity=_optional_int(record.get("rarity")),
        refinement=_optional_int(_first_present(record, "refinement", "affix_level")),
        weapon_type=_text(_first_present(record, "type_name", "weapon_type_name", "type")),
    )


def _artifact_contribution(
    artifact_summary: Mapping[str, Any] | ArtifactBuildSnapshot | None,
) -> ArtifactStatContribution:
    if artifact_summary is None:
        return ArtifactStatContribution(
            summary=None,
            warnings=(WARNING_ARTIFACT_SUMMARY_MISSING,),
        )

    build_snapshot = (
        artifact_summary
        if isinstance(artifact_summary, ArtifactBuildSnapshot)
        else build_artifact_build_snapshot(artifact_summary)
    )
    return ArtifactStatContribution(
        summary=build_snapshot.to_dict(),
        warnings=tuple(_dedupe(build_snapshot.warnings)),
    )


def _select_pair(
    pair: StatValuePair,
    *,
    phase: str | None,
) -> SelectedStatValue:
    return _select_values(pair.before, pair.after, phase=phase)


def _select_weapon_pair(
    pair: WeaponAtkValuePair,
    *,
    phase: str | None,
) -> SelectedStatValue:
    return _select_values(pair.before, pair.after, phase=phase)


def _select_values(
    before: str | None,
    after: str | None,
    *,
    phase: str | None,
) -> SelectedStatValue:
    if before and after:
        if phase == VALUE_SELECTION_BEFORE:
            return SelectedStatValue(
                before=before,
                after=after,
                selected=before,
                selection=VALUE_SELECTION_BEFORE,
            )
        if phase == VALUE_SELECTION_AFTER:
            return SelectedStatValue(
                before=before,
                after=after,
                selected=after,
                selection=VALUE_SELECTION_AFTER,
            )
        return SelectedStatValue(
            before=before,
            after=after,
            selected=None,
            selection=VALUE_SELECTION_AMBIGUOUS,
            warnings=(WARNING_ASCENSION_PHASE_UNKNOWN,),
        )
    if before:
        return SelectedStatValue(
            before=before,
            after=after,
            selected=before,
            selection=VALUE_SELECTION_SINGLE,
        )
    if after:
        return SelectedStatValue(
            before=before,
            after=after,
            selected=after,
            selection=VALUE_SELECTION_SINGLE,
        )
    return SelectedStatValue(
        before=before,
        after=after,
        selected=None,
        selection=VALUE_SELECTION_UNAVAILABLE,
    )


def _find_row_for_level(rows: tuple[Any, ...], level: int | None) -> Any | None:
    if level is None:
        return None
    for row in rows:
        if _level_from_key(getattr(row, "level_key", "")) == level:
            return row
    return None


def _level_from_key(value: str) -> int | None:
    match = re.search(r"\d+", str(value or ""))
    if not match:
        return None
    return _optional_int(match.group(0))


def _phase_for_level(level: int | None, promote_level: int | None) -> str | None:
    if level is None or promote_level is None:
        return None
    before_after = _ASCENSION_BREAKPOINTS.get(level)
    if before_after is None:
        return None
    before_promote, after_promote = before_after
    if promote_level <= before_promote:
        return VALUE_SELECTION_BEFORE
    if promote_level >= after_promote:
        return VALUE_SELECTION_AFTER
    return None


def _character_phase_for_level(
    level: int | None,
    promote_level: int | None,
) -> tuple[str | None, str | None]:
    if promote_level is not None:
        return _phase_for_level(level, promote_level), None
    if level in _ASCENSION_BREAKPOINTS:
        return VALUE_SELECTION_AFTER, WARNING_CHARACTER_ASCENSION_PHASE_ASSUMED
    if level == 90:
        return VALUE_SELECTION_BEFORE, WARNING_CHARACTER_ASCENSION_PHASE_ASSUMED
    return None, None


def _character_row_has_before_after(row: CharacterBaseStatRow) -> bool:
    return any(
        pair.before and pair.after
        for pair in (
            row.base_hp,
            row.base_atk,
            row.base_def,
            row.ascension_bonus,
        )
    )


def _is_special_traveler(character: SnapshotAccountCharacter) -> bool:
    normalized = normalize_catalog_name(character.name)
    return normalized in {
        normalize_catalog_name(name)
        for name in DEFAULT_SPECIAL_TRAVELER_NAMES
    }


def _first_present(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return None


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: list[str] | tuple[str, ...]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
