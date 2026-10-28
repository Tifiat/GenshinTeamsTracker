from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Literal


MappingStatus = Literal["matched", "unmatched", "ambiguous"]

STATUS_MATCHED = "matched"
STATUS_UNMATCHED = "unmatched"
STATUS_AMBIGUOUS = "ambiguous"

MATCH_METHOD_NAME = "normalized_name"

WARNING_ACCOUNT_NAME_MISSING = "account_name_missing"
WARNING_CATALOG_NAME_MISSING = "catalog_name_missing"
WARNING_LANGUAGE_MISMATCH = "language_mismatch"
WARNING_DIRECT_ID_EQUAL_UNVERIFIED = "direct_id_equal_unverified"
WARNING_ELEMENT_MISMATCH = "element_mismatch"
WARNING_ELEMENT_MISSING = "element_missing"
WARNING_RARITY_MISMATCH = "rarity_mismatch"
WARNING_RARITY_MISSING = "rarity_missing"
WARNING_WEAPON_TYPE_MISMATCH = "weapon_type_mismatch"
WARNING_WEAPON_TYPE_MISSING = "weapon_type_missing"
WARNING_DUPLICATE_ACCOUNT_VARIANT = "duplicate_account_variant"

_TOKEN_ALIASES = {
    "pyro": "pyro",
    "пиро": "pyro",
    "hydro": "hydro",
    "гидро": "hydro",
    "geo": "geo",
    "гео": "geo",
    "electro": "electro",
    "электро": "electro",
    "dendro": "dendro",
    "дендро": "dendro",
    "cryo": "cryo",
    "крио": "cryo",
    "anemo": "anemo",
    "анемо": "anemo",
    "sword": "sword",
    "одноручное": "sword",
    "одноручный_меч": "sword",
    "claymore": "claymore",
    "двуручное": "claymore",
    "двуручный_меч": "claymore",
    "bow": "bow",
    "лук": "bow",
    "стрелковое": "bow",
    "catalyst": "catalyst",
    "катализатор": "catalyst",
    "polearm": "polearm",
    "копье": "polearm",
    "древковое": "polearm",
}


@dataclass(frozen=True, slots=True)
class CatalogRecordRef:
    source_id: str
    name: str
    normalized_name: str
    lang: str = ""
    attributes: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "name": self.name,
            "normalized_name": self.normalized_name,
            "lang": self.lang,
            "attributes": dict(self.attributes or {}),
        }


@dataclass(frozen=True, slots=True)
class CatalogMappingEntry:
    status: MappingStatus
    account: CatalogRecordRef
    matches: tuple[CatalogRecordRef, ...] = ()
    match_method: str = ""
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "account": self.account.to_dict(),
            "matches": [match.to_dict() for match in self.matches],
            "match_method": self.match_method,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class CatalogMappingResult:
    kind: str
    entries: tuple[CatalogMappingEntry, ...]

    @property
    def total(self) -> int:
        return len(self.entries)

    @property
    def matched_count(self) -> int:
        return sum(1 for entry in self.entries if entry.status == STATUS_MATCHED)

    @property
    def unmatched_count(self) -> int:
        return sum(1 for entry in self.entries if entry.status == STATUS_UNMATCHED)

    @property
    def ambiguous_count(self) -> int:
        return sum(1 for entry in self.entries if entry.status == STATUS_AMBIGUOUS)

    def to_report(self, *, examples_per_status: int = 3) -> dict[str, Any]:
        method_counts = Counter(
            entry.match_method
            for entry in self.entries
            if entry.match_method
        )
        warning_counts = Counter(
            warning
            for entry in self.entries
            for warning in entry.warnings
        )

        return {
            "kind": self.kind,
            "total": self.total,
            "matched": self.matched_count,
            "unmatched": self.unmatched_count,
            "ambiguous": self.ambiguous_count,
            "match_methods": dict(sorted(method_counts.items())),
            "warnings": dict(sorted(warning_counts.items())),
            "examples": {
                status: [
                    entry.to_dict()
                    for entry in self.entries
                    if entry.status == status
                ][:examples_per_status]
                for status in (
                    STATUS_MATCHED,
                    STATUS_UNMATCHED,
                    STATUS_AMBIGUOUS,
                )
            },
        }


class CharacterCatalogMapper:
    def __init__(
        self,
        catalog_records: Iterable[dict[str, Any]],
        *,
        account_language: str | None = None,
    ):
        self.account_language = _normalize_language(account_language)
        self.catalog_by_name = _index_catalog_records(
            catalog_records,
            _character_catalog_ref,
            account_language=self.account_language,
        )

    def map_records(self, account_records: Iterable[dict[str, Any]]) -> CatalogMappingResult:
        return CatalogMappingResult(
            kind="character",
            entries=tuple(self.map_record(record) for record in account_records),
        )

    def map_record(self, account_record: dict[str, Any]) -> CatalogMappingEntry:
        account_ref = _character_account_ref(account_record, language=self.account_language)
        warnings = _account_base_warnings(account_ref)
        candidates = list(self.catalog_by_name.get(account_ref.normalized_name, ()))
        warnings.extend(_direct_id_diagnostic(account_ref, candidates))

        if not candidates:
            return CatalogMappingEntry(
                status=STATUS_UNMATCHED,
                account=account_ref,
                warnings=tuple(warnings),
            )

        candidates, cross_warnings = _narrow_character_candidates(account_ref, candidates)
        warnings.extend(cross_warnings)
        return _entry_from_candidates(account_ref, candidates, warnings)


class WeaponCatalogMapper:
    def __init__(
        self,
        catalog_records: Iterable[dict[str, Any]],
        *,
        account_language: str | None = None,
    ):
        self.account_language = _normalize_language(account_language)
        self.catalog_by_name = _index_catalog_records(
            catalog_records,
            _weapon_catalog_ref,
            account_language=self.account_language,
        )

    def map_records(self, account_records: Iterable[dict[str, Any]]) -> CatalogMappingResult:
        records = list(account_records)
        duplicate_keys = _duplicate_weapon_variant_keys(records)
        return CatalogMappingResult(
            kind="weapon",
            entries=tuple(
                self.map_record(record, duplicate_keys=duplicate_keys)
                for record in records
            ),
        )

    def map_record(
        self,
        account_record: dict[str, Any],
        *,
        duplicate_keys: set[tuple[str, str, str, str]] | None = None,
    ) -> CatalogMappingEntry:
        account_ref = _weapon_account_ref(account_record, language=self.account_language)
        warnings = _account_base_warnings(account_ref)

        duplicate_key = _weapon_variant_key(account_record)
        if duplicate_keys and duplicate_key in duplicate_keys:
            warnings.append(WARNING_DUPLICATE_ACCOUNT_VARIANT)

        candidates = list(self.catalog_by_name.get(account_ref.normalized_name, ()))
        warnings.extend(_direct_id_diagnostic(account_ref, candidates))

        if not candidates:
            return CatalogMappingEntry(
                status=STATUS_UNMATCHED,
                account=account_ref,
                warnings=tuple(warnings),
            )

        candidates, cross_warnings = _narrow_weapon_candidates(account_ref, candidates)
        warnings.extend(cross_warnings)
        return _entry_from_candidates(account_ref, candidates, warnings)


def map_character_catalog(
    account_records: Iterable[dict[str, Any]],
    catalog_records: Iterable[dict[str, Any]],
    *,
    account_language: str | None = None,
) -> CatalogMappingResult:
    return CharacterCatalogMapper(
        catalog_records,
        account_language=account_language,
    ).map_records(account_records)


def map_weapon_catalog(
    account_records: Iterable[dict[str, Any]],
    catalog_records: Iterable[dict[str, Any]],
    *,
    account_language: str | None = None,
) -> CatalogMappingResult:
    return WeaponCatalogMapper(
        catalog_records,
        account_language=account_language,
    ).map_records(account_records)


def normalize_catalog_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = text.replace("ё", "е")
    text = re.sub(r"[^\w\s-]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"[-_]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _index_catalog_records(
    records: Iterable[dict[str, Any]],
    ref_builder,
    *,
    account_language: str,
) -> dict[str, tuple[CatalogRecordRef, ...]]:
    grouped: dict[str, list[CatalogRecordRef]] = {}
    for record in records:
        ref = ref_builder(record, account_language=account_language)
        if not ref.normalized_name:
            grouped.setdefault("", []).append(ref)
            continue
        grouped.setdefault(ref.normalized_name, []).append(ref)
    return {
        key: tuple(values)
        for key, values in grouped.items()
    }


def _entry_from_candidates(
    account_ref: CatalogRecordRef,
    candidates: list[CatalogRecordRef],
    warnings: list[str],
) -> CatalogMappingEntry:
    warnings.extend(_candidate_mapping_warnings(candidates))
    warnings = _dedupe(warnings)
    if len(candidates) == 1:
        return CatalogMappingEntry(
            status=STATUS_MATCHED,
            account=account_ref,
            matches=(candidates[0],),
            match_method=MATCH_METHOD_NAME,
            warnings=tuple(warnings),
        )
    return CatalogMappingEntry(
        status=STATUS_AMBIGUOUS,
        account=account_ref,
        matches=tuple(candidates),
        match_method=MATCH_METHOD_NAME,
        warnings=tuple(warnings),
    )


def _account_base_warnings(account_ref: CatalogRecordRef) -> list[str]:
    return [WARNING_ACCOUNT_NAME_MISSING] if not account_ref.normalized_name else []


def _candidate_mapping_warnings(candidates: list[CatalogRecordRef]) -> list[str]:
    warnings: list[str] = []
    for candidate in candidates:
        attributes = candidate.attributes or {}
        for warning in attributes.get("mapping_warnings") or ():
            warnings.append(str(warning))
    return warnings


def _direct_id_diagnostic(
    account_ref: CatalogRecordRef,
    candidates: list[CatalogRecordRef],
) -> list[str]:
    if not account_ref.source_id:
        return []
    return [
        WARNING_DIRECT_ID_EQUAL_UNVERIFIED
        for candidate in candidates
        if candidate.source_id and candidate.source_id == account_ref.source_id
    ][:1]


def _narrow_character_candidates(
    account_ref: CatalogRecordRef,
    candidates: list[CatalogRecordRef],
) -> tuple[list[CatalogRecordRef], list[str]]:
    warnings: list[str] = []
    narrowed = _narrow_by_attribute(
        account_ref,
        candidates,
        "element",
        missing_warning=WARNING_ELEMENT_MISSING,
        mismatch_warning=WARNING_ELEMENT_MISMATCH,
    )
    candidates, attr_warnings = narrowed
    warnings.extend(attr_warnings)

    narrowed = _narrow_by_attribute(
        account_ref,
        candidates,
        "rarity",
        missing_warning=WARNING_RARITY_MISSING,
        mismatch_warning=WARNING_RARITY_MISMATCH,
    )
    candidates, attr_warnings = narrowed
    warnings.extend(attr_warnings)
    return candidates, warnings


def _narrow_weapon_candidates(
    account_ref: CatalogRecordRef,
    candidates: list[CatalogRecordRef],
) -> tuple[list[CatalogRecordRef], list[str]]:
    warnings: list[str] = []
    narrowed = _narrow_by_attribute(
        account_ref,
        candidates,
        "weapon_type",
        missing_warning=WARNING_WEAPON_TYPE_MISSING,
        mismatch_warning=WARNING_WEAPON_TYPE_MISMATCH,
    )
    candidates, attr_warnings = narrowed
    warnings.extend(attr_warnings)

    narrowed = _narrow_by_attribute(
        account_ref,
        candidates,
        "rarity",
        missing_warning=WARNING_RARITY_MISSING,
        mismatch_warning=WARNING_RARITY_MISMATCH,
    )
    candidates, attr_warnings = narrowed
    warnings.extend(attr_warnings)
    return candidates, warnings


def _narrow_by_attribute(
    account_ref: CatalogRecordRef,
    candidates: list[CatalogRecordRef],
    attribute: str,
    *,
    missing_warning: str,
    mismatch_warning: str,
) -> tuple[list[CatalogRecordRef], list[str]]:
    account_value = _attribute_value(account_ref, attribute)
    candidate_values = [
        _attribute_value(candidate, attribute)
        for candidate in candidates
    ]
    known_candidate_values = [value for value in candidate_values if value]

    if not account_value or not known_candidate_values:
        return candidates, [missing_warning]

    matching = [
        candidate
        for candidate in candidates
        if _attribute_value(candidate, attribute) == account_value
    ]
    if matching:
        return matching, []
    return candidates, [mismatch_warning]


def _attribute_value(ref: CatalogRecordRef, attribute: str) -> str:
    attributes = ref.attributes or {}
    value = attributes.get(attribute)
    if value is None:
        return ""
    if attribute in {"element", "weapon_type"}:
        return _normalize_token(value)
    if attribute == "rarity":
        return _normalize_rarity_text(value)
    return str(value).strip()


def _character_account_ref(record: dict[str, Any], *, language: str) -> CatalogRecordRef:
    return CatalogRecordRef(
        source_id=_string(record.get("id")),
        name=_string(record.get("name")),
        normalized_name=normalize_catalog_name(record.get("name")),
        lang=language,
        attributes={
            "element": _first_present(record, "element", "vision"),
            "rarity": record.get("rarity"),
            "level": record.get("level"),
            "constellation": record.get("constellation"),
            "weapon_type": _first_present(record, "weapon_type_name", "weapon_type"),
        },
    )


def _character_catalog_ref(
    record: dict[str, Any],
    *,
    account_language: str,
) -> CatalogRecordRef:
    name = _string(record.get("name"))
    normalized_name = _string(record.get("normalized_name")) or normalize_catalog_name(name)
    lang = _normalize_language(record.get("lang"))
    warnings = _language_warnings(account_language, lang)
    attributes = {
        "element": _first_present(
            record,
            "element",
            "vision",
            "character_vision",
        ) or _filter_value(record, "character_vision"),
        "rarity": _first_present(record, "rarity", "character_rarity")
        or _filter_value(record, "character_rarity"),
        "region": _first_present(record, "region_key", "region_name"),
    }
    if warnings:
        attributes["mapping_warnings"] = tuple(warnings)
    return CatalogRecordRef(
        source_id=_string(record.get("entry_page_id") or record.get("id")),
        name=name,
        normalized_name=normalized_name,
        lang=lang,
        attributes=attributes,
    )


def _weapon_account_ref(record: dict[str, Any], *, language: str) -> CatalogRecordRef:
    return CatalogRecordRef(
        source_id=_string(record.get("id")),
        name=_string(record.get("name")),
        normalized_name=normalize_catalog_name(record.get("name")),
        lang=language,
        attributes={
            "rarity": record.get("rarity"),
            "weapon_type": _first_present(record, "type_name", "type", "weapon_type"),
            "level": record.get("level"),
            "refinement": record.get("refinement"),
        },
    )


def _weapon_catalog_ref(
    record: dict[str, Any],
    *,
    account_language: str,
) -> CatalogRecordRef:
    name = _string(record.get("name"))
    normalized_name = _string(record.get("normalized_name")) or normalize_catalog_name(name)
    lang = _normalize_language(record.get("lang"))
    warnings = _language_warnings(account_language, lang)
    attributes = {
        "rarity": _first_present(record, "rarity", "weapon_rarity")
        or _filter_value(record, "weapon_rarity"),
        "weapon_type": _first_present(record, "type", "type_name", "weapon_type")
        or _filter_value(record, "weapon_type"),
        "secondary_attribute": _first_present(
            record,
            "secondary_attribute",
            "weapon_property",
        ) or _filter_value(record, "weapon_property"),
    }
    if warnings:
        attributes["mapping_warnings"] = tuple(warnings)
    return CatalogRecordRef(
        source_id=_string(record.get("entry_page_id") or record.get("id")),
        name=name,
        normalized_name=normalized_name,
        lang=lang,
        attributes=attributes,
    )


def _language_warnings(account_language: str, catalog_language: str) -> list[str]:
    if account_language and catalog_language and account_language != catalog_language:
        return [WARNING_LANGUAGE_MISMATCH]
    return []


def _filter_value(record: dict[str, Any], key: str) -> str:
    filter_values = record.get("filter_values") or {}
    if not isinstance(filter_values, dict):
        return ""
    item = filter_values.get(key) or {}
    if not isinstance(item, dict):
        return ""
    values = item.get("values") or []
    if not isinstance(values, list) or not values:
        return ""
    return _string(values[0])


def _first_present(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return ""


def _duplicate_weapon_variant_keys(records: list[dict[str, Any]]) -> set[tuple[str, str, str, str]]:
    counts = Counter(_weapon_variant_key(record) for record in records)
    return {
        key
        for key, count in counts.items()
        if count > 1 and any(key)
    }


def _weapon_variant_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        normalize_catalog_name(record.get("name")),
        _normalize_int_text(record.get("level")),
        _normalize_int_text(record.get("refinement")),
        _normalize_token(_first_present(record, "type_name", "type", "weapon_type")),
    )


def _normalize_language(value: Any) -> str:
    return str(value or "").strip().replace("_", "-").lower()


def _normalize_token(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = text.replace("ё", "е")
    text = re.sub(r"[^\w]+", "_", text, flags=re.UNICODE)
    text = text.strip("_")
    return _TOKEN_ALIASES.get(text, text)


def _normalize_int_text(value: Any) -> str:
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value or "").strip()


def _normalize_rarity_text(value: Any) -> str:
    text = str(value or "").strip()
    try:
        return str(int(text))
    except (TypeError, ValueError):
        pass

    match = re.search(r"\d+", text)
    return match.group(0) if match else text


def _string(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
