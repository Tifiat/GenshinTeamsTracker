from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .character_stat_snapshot import build_character_base_stat_contribution
from .character_stats_catalog import CharacterBaseStatsEntry


ASCENSION_BONUS_SCHEMA_VERSION = 1

WARNING_ASCENSION_BONUS_MISSING = "ascension_bonus_missing"
WARNING_ASCENSION_BONUS_BASE_STAT_MISSING = "ascension_bonus_base_stat_missing"
WARNING_ASCENSION_BONUS_BASE_STAT_NO_MATCH = "ascension_bonus_base_stat_no_match"
WARNING_ASCENSION_BONUS_BASE_STAT_AMBIGUOUS = "ascension_bonus_base_stat_ambiguous"
WARNING_ASCENSION_BONUS_LEVEL_MISSING = "ascension_bonus_level_missing"
WARNING_ASCENSION_BONUS_LEVEL_ROW_MISSING = "ascension_bonus_level_row_missing"

MATCHED_BY_BASE_HP = "matched_by_base_hp"
MATCHED_BY_BASE_DEF = "matched_by_base_def"
MATCHED_BY_BASE_ATK = "matched_by_base_atk"


@dataclass(frozen=True, slots=True)
class CharacterAscensionBonusValue:
    level_key: str
    before: str | None = None
    after: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "level_key": self.level_key,
            "before": self.before,
            "after": self.after,
        }


@dataclass(frozen=True, slots=True)
class CharacterAscensionBonusInfo:
    entry_page_id: str
    name: str
    lang: str
    stat_type: str = ""
    values: tuple[CharacterAscensionBonusValue, ...] = ()
    selected_level_key: str = ""
    selected_phase: str = ""
    selected_source: str = ""
    selected_value: str | None = None
    warnings: tuple[str, ...] = ()
    schema_version: int = ASCENSION_BONUS_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "entry_page_id": self.entry_page_id,
            "name": self.name,
            "lang": self.lang,
            "stat_type": self.stat_type,
            "values": [value.to_dict() for value in self.values],
            "selected_level_key": self.selected_level_key,
            "selected_phase": self.selected_phase,
            "selected_source": self.selected_source,
            "selected_value": self.selected_value,
            "warnings": list(self.warnings),
        }


def extract_character_ascension_bonus(
    entry: CharacterBaseStatsEntry,
    *,
    account_level: int | None = None,
    promote_level: int | None = None,
) -> CharacterAscensionBonusInfo:
    values: list[CharacterAscensionBonusValue] = []
    stat_types: list[str] = []
    for row in entry.rows:
        if row.ascension_bonus.before or row.ascension_bonus.after:
            values.append(
                CharacterAscensionBonusValue(
                    level_key=row.level_key,
                    before=row.ascension_bonus.before,
                    after=row.ascension_bonus.after,
                )
            )
        if row.ascension_bonus_stat_type and row.ascension_bonus_stat_type not in stat_types:
            stat_types.append(row.ascension_bonus_stat_type)

    selected_level_key = ""
    selected_value: str | None = None
    warnings = list(entry.warnings)
    if account_level is not None:
        contribution = build_character_base_stat_contribution(
            entry,
            account_level=account_level,
            promote_level=promote_level,
        )
        selected_level_key = contribution.selected_level_key
        selected_value = contribution.ascension_bonus.selected
        warnings.extend(contribution.ascension_bonus.warnings)
        warnings.extend(contribution.warnings)

    if not values:
        warnings.append(WARNING_ASCENSION_BONUS_MISSING)

    return CharacterAscensionBonusInfo(
        entry_page_id=entry.entry_page_id,
        name=entry.name,
        lang=entry.lang,
        stat_type=stat_types[0] if stat_types else "",
        values=tuple(values),
        selected_level_key=selected_level_key,
        selected_value=selected_value,
        warnings=tuple(_dedupe(warnings)),
    )


def extract_character_ascension_bonus_by_base_stats(
    entry: CharacterBaseStatsEntry,
    *,
    account_level: int | None,
    base_hp: Any = None,
    base_def: Any = None,
    base_atk: Any = None,
) -> CharacterAscensionBonusInfo:
    """Select ascension bonus row by matching actual HoYoLAB account base stats."""

    values, stat_types = _ascension_values_and_stat_types(entry)
    warnings = list(entry.warnings)

    if not values:
        warnings.append(WARNING_ASCENSION_BONUS_MISSING)

    if account_level is None:
        warnings.append(WARNING_ASCENSION_BONUS_LEVEL_MISSING)
        warnings.append(WARNING_ASCENSION_BONUS_BASE_STAT_NO_MATCH)
        return _bonus_info(
            entry,
            values=values,
            stat_type=stat_types[0] if stat_types else "",
            warnings=warnings,
        )

    row = _find_row_for_level(entry, account_level)
    if row is None:
        warnings.append(WARNING_ASCENSION_BONUS_LEVEL_ROW_MISSING)
        warnings.append(WARNING_ASCENSION_BONUS_BASE_STAT_NO_MATCH)
        return _bonus_info(
            entry,
            values=values,
            stat_type=stat_types[0] if stat_types else "",
            warnings=warnings,
        )

    for source, pair, account_value in (
        (MATCHED_BY_BASE_HP, row.base_hp, base_hp),
        (MATCHED_BY_BASE_DEF, row.base_def, base_def),
        (MATCHED_BY_BASE_ATK, row.base_atk, base_atk),
    ):
        if not _has_number(account_value):
            continue
        matches = _matching_phases(pair.before, pair.after, account_value)
        if len(matches) == 1:
            phase = matches[0]
            selected_value = _value_for_phase(
                row.ascension_bonus.before,
                row.ascension_bonus.after,
                phase,
            )
            if not selected_value:
                warnings.append(WARNING_ASCENSION_BONUS_MISSING)
            return _bonus_info(
                entry,
                values=values,
                stat_type=row.ascension_bonus_stat_type or (stat_types[0] if stat_types else ""),
                selected_level_key=row.level_key,
                selected_phase=phase,
                selected_source=source,
                selected_value=selected_value,
                warnings=warnings,
            )
        if len(matches) > 1:
            warnings.append(WARNING_ASCENSION_BONUS_BASE_STAT_AMBIGUOUS)
            return _bonus_info(
                entry,
                values=values,
                stat_type=row.ascension_bonus_stat_type or (stat_types[0] if stat_types else ""),
                selected_level_key=row.level_key,
                warnings=warnings,
            )

    warnings.append(WARNING_ASCENSION_BONUS_BASE_STAT_MISSING)
    warnings.append(WARNING_ASCENSION_BONUS_BASE_STAT_NO_MATCH)
    return _bonus_info(
        entry,
        values=values,
        stat_type=row.ascension_bonus_stat_type or (stat_types[0] if stat_types else ""),
        selected_level_key=row.level_key,
        warnings=warnings,
    )


def _ascension_values_and_stat_types(
    entry: CharacterBaseStatsEntry,
) -> tuple[list[CharacterAscensionBonusValue], list[str]]:
    values: list[CharacterAscensionBonusValue] = []
    stat_types: list[str] = []
    for row in entry.rows:
        if row.ascension_bonus.before or row.ascension_bonus.after:
            values.append(
                CharacterAscensionBonusValue(
                    level_key=row.level_key,
                    before=row.ascension_bonus.before,
                    after=row.ascension_bonus.after,
                )
            )
        if row.ascension_bonus_stat_type and row.ascension_bonus_stat_type not in stat_types:
            stat_types.append(row.ascension_bonus_stat_type)
    return values, stat_types


def _bonus_info(
    entry: CharacterBaseStatsEntry,
    *,
    values: list[CharacterAscensionBonusValue],
    stat_type: str,
    selected_level_key: str = "",
    selected_phase: str = "",
    selected_source: str = "",
    selected_value: str | None = None,
    warnings: list[str],
) -> CharacterAscensionBonusInfo:
    return CharacterAscensionBonusInfo(
        entry_page_id=entry.entry_page_id,
        name=entry.name,
        lang=entry.lang,
        stat_type=stat_type,
        values=tuple(values),
        selected_level_key=selected_level_key,
        selected_phase=selected_phase,
        selected_source=selected_source,
        selected_value=selected_value,
        warnings=tuple(_dedupe(warnings)),
    )


def _find_row_for_level(entry: CharacterBaseStatsEntry, account_level: int):
    for row in entry.rows:
        if _level_from_key(row.level_key) == account_level:
            return row
    return None


def _level_from_key(value: str) -> int | None:
    digits = "".join(char for char in str(value or "") if char.isdigit())
    return int(digits) if digits else None


def _matching_phases(before: Any, after: Any, account_value: Any) -> list[str]:
    matches: list[str] = []
    account_number = _number(account_value)
    if before not in (None, "") and _numbers_match(account_number, _number(before)):
        matches.append("before")
    if after not in (None, "") and _numbers_match(account_number, _number(after)):
        matches.append("after")
    return matches


def _value_for_phase(before: str | None, after: str | None, phase: str) -> str | None:
    if phase == "before":
        return before
    if phase == "after":
        return after
    return None


def _has_number(value: Any) -> bool:
    return value not in (None, "") and _number(value) is not None


def _number(value: Any) -> float | None:
    text = str(value or "").replace("%", "").replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _numbers_match(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) < 0.05


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
