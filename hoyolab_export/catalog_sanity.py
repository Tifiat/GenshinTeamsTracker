from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from .catalog_mapping import (
    STATUS_AMBIGUOUS,
    STATUS_MATCHED,
    STATUS_UNMATCHED,
    CatalogMappingEntry,
    CatalogMappingResult,
    CatalogRecordRef,
    normalize_catalog_name,
)
from .character_stats_catalog import (
    WARNING_MALFORMED_ASCENSION_COMPONENT as CHARACTER_WARNING_MALFORMED_ASCENSION_COMPONENT,
    CharacterBaseStatRow,
    CharacterBaseStatsCatalog,
    CharacterBaseStatsEntry,
)
from .weapon_stats_catalog import (
    WARNING_MALFORMED_ASCENSION_COMPONENT as WEAPON_WARNING_MALFORMED_ASCENSION_COMPONENT,
    WeaponBaseStatRow,
    WeaponStatsCatalog,
    WeaponStatsEntry,
)


STATUS_READY = "ready"
STATUS_FUTURE_PENDING_STATS = "future_pending_stats"
STATUS_STATS_UNAVAILABLE = "stats_unavailable"
STATUS_MALFORMED = "malformed"
STATUS_SPECIAL_DEFERRED = "special_deferred"
STATUS_CATALOG_ENTRY_MISSING = "catalog_entry_missing"

WARNING_ENTRY_PAGE_ID_MISSING = "entry_page_id_missing"
WARNING_STATS_UNAVAILABLE = "stats_unavailable"
WARNING_BASE_STATS_MISSING = "base_stats_missing"
WARNING_BASE_ATK_MISSING = "base_atk_missing"
WARNING_TRAVELER_SPECIAL_DEFERRED = "traveler_special_deferred"
WARNING_CATALOG_ENTRY_MISSING = "catalog_entry_missing"

DEFAULT_SPECIAL_TRAVELER_NAMES = (
    "traveler",
    "путешественник",
    "путешественница",
)


@dataclass(frozen=True, slots=True)
class CatalogEntrySanity:
    kind: str
    entry_page_id: str
    name: str
    status: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "entry_page_id": self.entry_page_id,
            "name": self.name,
            "status": self.status,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class AccountCatalogReadinessEntry:
    kind: str
    account_id: str
    account_name: str
    status: str
    catalog_entry_id: str = ""
    catalog_entry_name: str = ""
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "status": self.status,
            "catalog_entry_id": self.catalog_entry_id,
            "catalog_entry_name": self.catalog_entry_name,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class CatalogSanityReport:
    character_entries: tuple[CatalogEntrySanity, ...] = ()
    weapon_entries: tuple[CatalogEntrySanity, ...] = ()
    account_characters: tuple[AccountCatalogReadinessEntry, ...] = ()
    account_weapons: tuple[AccountCatalogReadinessEntry, ...] = ()

    def to_dict(self, *, examples_per_status: int = 5) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "characters": _summary(self.character_entries, examples_per_status),
            "weapons": _summary(self.weapon_entries, examples_per_status),
            "account_characters": _summary(self.account_characters, examples_per_status),
            "account_weapons": _summary(self.account_weapons, examples_per_status),
            "notes": [
                (
                    "Empty character ascension rows are classified as "
                    "future_pending_stats, not non_playable."
                ),
                (
                    "Account Traveler is special_deferred and must not be "
                    "aliased to one HoYoWiki elemental variant."
                ),
            ],
        }


def classify_character_stats_entry(
    entry: CharacterBaseStatsEntry,
) -> CatalogEntrySanity:
    warnings = list(entry.warnings)
    if not entry.entry_page_id:
        warnings.append(WARNING_ENTRY_PAGE_ID_MISSING)
    if CHARACTER_WARNING_MALFORMED_ASCENSION_COMPONENT in entry.warnings:
        return CatalogEntrySanity(
            kind="character",
            entry_page_id=entry.entry_page_id,
            name=entry.name,
            status=STATUS_MALFORMED,
            warnings=tuple(_dedupe(warnings)),
        )
    if not entry.entry_page_id:
        return CatalogEntrySanity(
            kind="character",
            entry_page_id=entry.entry_page_id,
            name=entry.name,
            status=STATUS_MALFORMED,
            warnings=tuple(_dedupe(warnings)),
        )
    if not entry.rows:
        warnings.append(WARNING_STATS_UNAVAILABLE)
        return CatalogEntrySanity(
            kind="character",
            entry_page_id=entry.entry_page_id,
            name=entry.name,
            status=STATUS_FUTURE_PENDING_STATS,
            warnings=tuple(_dedupe(warnings)),
        )
    if not any(_character_row_has_base_stats(row) for row in entry.rows):
        warnings.append(WARNING_BASE_STATS_MISSING)
        return CatalogEntrySanity(
            kind="character",
            entry_page_id=entry.entry_page_id,
            name=entry.name,
            status=STATUS_MALFORMED,
            warnings=tuple(_dedupe(warnings)),
        )
    return CatalogEntrySanity(
        kind="character",
        entry_page_id=entry.entry_page_id,
        name=entry.name,
        status=STATUS_READY,
        warnings=tuple(_dedupe(warnings)),
    )


def classify_weapon_stats_entry(entry: WeaponStatsEntry) -> CatalogEntrySanity:
    warnings = list(entry.warnings)
    if not entry.entry_page_id:
        warnings.append(WARNING_ENTRY_PAGE_ID_MISSING)
    if WEAPON_WARNING_MALFORMED_ASCENSION_COMPONENT in entry.warnings:
        return CatalogEntrySanity(
            kind="weapon",
            entry_page_id=entry.entry_page_id,
            name=entry.name,
            status=STATUS_MALFORMED,
            warnings=tuple(_dedupe(warnings)),
        )
    if not entry.entry_page_id:
        return CatalogEntrySanity(
            kind="weapon",
            entry_page_id=entry.entry_page_id,
            name=entry.name,
            status=STATUS_MALFORMED,
            warnings=tuple(_dedupe(warnings)),
        )
    if not entry.rows:
        warnings.append(WARNING_STATS_UNAVAILABLE)
        return CatalogEntrySanity(
            kind="weapon",
            entry_page_id=entry.entry_page_id,
            name=entry.name,
            status=STATUS_STATS_UNAVAILABLE,
            warnings=tuple(_dedupe(warnings)),
        )
    if not any(_weapon_row_has_base_atk(row) for row in entry.rows):
        warnings.append(WARNING_BASE_ATK_MISSING)
        return CatalogEntrySanity(
            kind="weapon",
            entry_page_id=entry.entry_page_id,
            name=entry.name,
            status=STATUS_MALFORMED,
            warnings=tuple(_dedupe(warnings)),
        )
    return CatalogEntrySanity(
        kind="weapon",
        entry_page_id=entry.entry_page_id,
        name=entry.name,
        status=STATUS_READY,
        warnings=tuple(_dedupe(warnings)),
    )


def classify_character_stats_catalog(
    catalog: CharacterBaseStatsCatalog,
) -> tuple[CatalogEntrySanity, ...]:
    return tuple(classify_character_stats_entry(entry) for entry in catalog.entries)


def classify_weapon_stats_catalog(
    catalog: WeaponStatsCatalog,
) -> tuple[CatalogEntrySanity, ...]:
    return tuple(classify_weapon_stats_entry(entry) for entry in catalog.entries)


def build_catalog_sanity_report(
    *,
    character_catalog: CharacterBaseStatsCatalog | None = None,
    weapon_catalog: WeaponStatsCatalog | None = None,
    character_mapping: CatalogMappingResult | None = None,
    weapon_mapping: CatalogMappingResult | None = None,
    special_traveler_names: Iterable[str] = DEFAULT_SPECIAL_TRAVELER_NAMES,
) -> CatalogSanityReport:
    character_entries = (
        classify_character_stats_catalog(character_catalog)
        if character_catalog is not None
        else ()
    )
    weapon_entries = (
        classify_weapon_stats_catalog(weapon_catalog)
        if weapon_catalog is not None
        else ()
    )

    return CatalogSanityReport(
        character_entries=character_entries,
        weapon_entries=weapon_entries,
        account_characters=(
            classify_account_character_readiness(
                character_mapping,
                character_entries,
                special_traveler_names=special_traveler_names,
            )
            if character_mapping is not None
            else ()
        ),
        account_weapons=(
            classify_account_weapon_readiness(weapon_mapping, weapon_entries)
            if weapon_mapping is not None
            else ()
        ),
    )


def classify_account_character_readiness(
    mapping: CatalogMappingResult,
    character_sanity: Iterable[CatalogEntrySanity],
    *,
    special_traveler_names: Iterable[str] = DEFAULT_SPECIAL_TRAVELER_NAMES,
) -> tuple[AccountCatalogReadinessEntry, ...]:
    sanity_by_id = _sanity_by_id(character_sanity)
    special_names = {
        normalize_catalog_name(name)
        for name in special_traveler_names
        if normalize_catalog_name(name)
    }
    return tuple(
        _account_entry_readiness(
            entry,
            sanity_by_id,
            kind="character",
            special_names=special_names,
        )
        for entry in mapping.entries
    )


def classify_account_weapon_readiness(
    mapping: CatalogMappingResult,
    weapon_sanity: Iterable[CatalogEntrySanity],
) -> tuple[AccountCatalogReadinessEntry, ...]:
    sanity_by_id = _sanity_by_id(weapon_sanity)
    return tuple(
        _account_entry_readiness(
            entry,
            sanity_by_id,
            kind="weapon",
            special_names=set(),
        )
        for entry in mapping.entries
    )


def _account_entry_readiness(
    entry: CatalogMappingEntry,
    sanity_by_id: dict[str, CatalogEntrySanity],
    *,
    kind: str,
    special_names: set[str],
) -> AccountCatalogReadinessEntry:
    account = entry.account
    if account.normalized_name in special_names:
        return AccountCatalogReadinessEntry(
            kind=kind,
            account_id=account.source_id,
            account_name=account.name,
            status=STATUS_SPECIAL_DEFERRED,
            warnings=(WARNING_TRAVELER_SPECIAL_DEFERRED,),
        )

    if entry.status == STATUS_UNMATCHED:
        return _account_result(entry, kind=kind, status=STATUS_UNMATCHED)
    if entry.status == STATUS_AMBIGUOUS or len(entry.matches) != 1:
        return _account_result(entry, kind=kind, status=STATUS_AMBIGUOUS)

    match = entry.matches[0]
    sanity = sanity_by_id.get(match.source_id)
    if sanity is None:
        return AccountCatalogReadinessEntry(
            kind=kind,
            account_id=account.source_id,
            account_name=account.name,
            status=STATUS_CATALOG_ENTRY_MISSING,
            catalog_entry_id=match.source_id,
            catalog_entry_name=match.name,
            warnings=tuple(_dedupe([*entry.warnings, WARNING_CATALOG_ENTRY_MISSING])),
        )

    return AccountCatalogReadinessEntry(
        kind=kind,
        account_id=account.source_id,
        account_name=account.name,
        status=sanity.status,
        catalog_entry_id=sanity.entry_page_id,
        catalog_entry_name=sanity.name,
        warnings=tuple(_dedupe([*entry.warnings, *sanity.warnings])),
    )


def _account_result(
    entry: CatalogMappingEntry,
    *,
    kind: str,
    status: str,
) -> AccountCatalogReadinessEntry:
    return AccountCatalogReadinessEntry(
        kind=kind,
        account_id=entry.account.source_id,
        account_name=entry.account.name,
        status=status,
        warnings=entry.warnings,
    )


def _summary(entries: Iterable[Any], examples_per_status: int) -> dict[str, Any]:
    values = tuple(entries)
    status_counts = Counter(entry.status for entry in values)
    warning_counts = Counter(
        warning
        for entry in values
        for warning in getattr(entry, "warnings", ())
    )
    return {
        "total": len(values),
        "statuses": dict(sorted(status_counts.items())),
        "warnings": dict(sorted(warning_counts.items())),
        "examples": {
            status: [
                entry.to_dict()
                for entry in values
                if entry.status == status
            ][:examples_per_status]
            for status in sorted(status_counts)
        },
    }


def _sanity_by_id(
    entries: Iterable[CatalogEntrySanity],
) -> dict[str, CatalogEntrySanity]:
    return {
        entry.entry_page_id: entry
        for entry in entries
        if entry.entry_page_id
    }


def _character_row_has_base_stats(row: CharacterBaseStatRow) -> bool:
    return bool(
        row.level_key
        and (
            row.base_hp.before
            or row.base_hp.after
            or row.base_atk.before
            or row.base_atk.after
            or row.base_def.before
            or row.base_def.after
        )
    )


def _weapon_row_has_base_atk(row: WeaponBaseStatRow) -> bool:
    return bool(row.level_key and (row.base_atk.before or row.base_atk.after))


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
