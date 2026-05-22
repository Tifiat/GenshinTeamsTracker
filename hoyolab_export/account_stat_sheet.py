from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


ACCOUNT_STAT_SHEET_SCHEMA_VERSION = 1

PROPERTY_TOTAL_HP = 2000
PROPERTY_TOTAL_ATK = 2001
PROPERTY_TOTAL_DEF = 2002
PROPERTY_WEAPON_BASE_ATK = 4

WARNING_BASE_HP_MISSING = "account_stat_sheet_base_hp_missing"
WARNING_BASE_ATK_MISSING = "account_stat_sheet_base_atk_missing"
WARNING_BASE_DEF_MISSING = "account_stat_sheet_base_def_missing"
WARNING_WEAPON_BASE_ATK_MISSING = "account_stat_sheet_weapon_base_atk_missing"


@dataclass(frozen=True, slots=True)
class AccountStatPropertyRow:
    property_type: int | None
    base: str = ""
    add: str = ""
    final: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "property_type": self.property_type,
            "base": self.base,
            "add": self.add,
            "final": self.final,
        }


@dataclass(frozen=True, slots=True)
class AccountWeaponStatSheet:
    id: str = ""
    name: str = ""
    level: int | None = None
    promote_level: int | None = None
    refinement: int | None = None
    desc: str = ""
    main_property: AccountStatPropertyRow | None = None
    sub_property: AccountStatPropertyRow | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level,
            "promote_level": self.promote_level,
            "refinement": self.refinement,
            "desc": self.desc,
            "main_property": (
                self.main_property.to_dict()
                if self.main_property is not None
                else None
            ),
            "sub_property": (
                self.sub_property.to_dict()
                if self.sub_property is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class AccountCharacterStatSheet:
    character_id: str = ""
    character_name: str = ""
    base_properties: tuple[AccountStatPropertyRow, ...] = ()
    extra_properties: tuple[AccountStatPropertyRow, ...] = ()
    element_properties: tuple[AccountStatPropertyRow, ...] = ()
    selected_properties: tuple[AccountStatPropertyRow, ...] = ()
    weapon: AccountWeaponStatSheet = AccountWeaponStatSheet()
    schema_version: int = ACCOUNT_STAT_SHEET_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "character_id": self.character_id,
            "character_name": self.character_name,
            "base_properties": [row.to_dict() for row in self.base_properties],
            "extra_properties": [row.to_dict() for row in self.extra_properties],
            "element_properties": [row.to_dict() for row in self.element_properties],
            "selected_properties": [row.to_dict() for row in self.selected_properties],
            "weapon": self.weapon.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class AccountCharacterBaseValues:
    base_hp: str = ""
    base_atk: str = ""
    base_def: str = ""
    source_notes: tuple[str, ...] = (
        "base_hp_from_hoyolab_base_properties",
        "base_def_from_hoyolab_base_properties",
        "base_atk_derived_from_hoyolab_base_atk_minus_weapon_base_atk",
    )
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_hp": self.base_hp,
            "base_atk": self.base_atk,
            "base_def": self.base_def,
            "source_notes": list(self.source_notes),
            "warnings": list(self.warnings),
        }


def parse_account_character_stat_sheet(
    record: Mapping[str, Any],
) -> AccountCharacterStatSheet:
    """Parse HoYoLAB `character/detail` stat-sheet fields from one list record."""

    base = _mapping(record.get("base"))
    weapon = _mapping(record.get("weapon"))
    return AccountCharacterStatSheet(
        character_id=_text(base.get("id") or record.get("id")),
        character_name=_text(base.get("name") or record.get("name")),
        base_properties=_property_rows(record.get("base_properties")),
        extra_properties=_property_rows(record.get("extra_properties")),
        element_properties=_property_rows(record.get("element_properties")),
        selected_properties=_property_rows(record.get("selected_properties")),
        weapon=AccountWeaponStatSheet(
            id=_text(weapon.get("id")),
            name=_text(weapon.get("name")),
            level=_optional_int(weapon.get("level")),
            promote_level=_optional_int(weapon.get("promote_level")),
            refinement=_optional_int(weapon.get("affix_level")),
            desc=_text(weapon.get("desc")),
            main_property=_property_row_or_none(weapon.get("main_property")),
            sub_property=_property_row_or_none(weapon.get("sub_property")),
        ),
    )


def extract_account_character_base_values(
    value: Mapping[str, Any] | AccountCharacterStatSheet,
) -> AccountCharacterBaseValues:
    sheet = (
        value
        if isinstance(value, AccountCharacterStatSheet)
        else parse_account_character_stat_sheet(value)
    )
    warnings: list[str] = []

    hp_row = _find_property(sheet.base_properties, PROPERTY_TOTAL_HP)
    atk_row = _find_property(sheet.base_properties, PROPERTY_TOTAL_ATK)
    def_row = _find_property(sheet.base_properties, PROPERTY_TOTAL_DEF)

    base_hp = hp_row.base if hp_row is not None else ""
    if not base_hp:
        warnings.append(WARNING_BASE_HP_MISSING)

    base_def = def_row.base if def_row is not None else ""
    if not base_def:
        warnings.append(WARNING_BASE_DEF_MISSING)

    base_atk = ""
    weapon_base_atk = (
        sheet.weapon.main_property.final
        if sheet.weapon.main_property is not None
        and sheet.weapon.main_property.property_type == PROPERTY_WEAPON_BASE_ATK
        else ""
    )
    if atk_row is None or not atk_row.base:
        warnings.append(WARNING_BASE_ATK_MISSING)
    elif not weapon_base_atk:
        warnings.append(WARNING_WEAPON_BASE_ATK_MISSING)
    else:
        base_atk = _format_number(_number(atk_row.base) - _number(weapon_base_atk))

    return AccountCharacterBaseValues(
        base_hp=base_hp,
        base_atk=base_atk,
        base_def=base_def,
        warnings=tuple(_dedupe(warnings)),
    )


def extract_account_weapon_property_values(
    value: Mapping[str, Any] | AccountCharacterStatSheet,
) -> AccountWeaponStatSheet:
    sheet = (
        value
        if isinstance(value, AccountCharacterStatSheet)
        else parse_account_character_stat_sheet(value)
    )
    return sheet.weapon


def _property_rows(value: Any) -> tuple[AccountStatPropertyRow, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        row
        for item in value
        if (row := _property_row_or_none(item)) is not None
    )


def _property_row_or_none(value: Any) -> AccountStatPropertyRow | None:
    if not isinstance(value, Mapping):
        return None
    return AccountStatPropertyRow(
        property_type=_optional_int(value.get("property_type")),
        base=_text(value.get("base")),
        add=_text(value.get("add")),
        final=_text(value.get("final")),
    )


def _find_property(
    rows: tuple[AccountStatPropertyRow, ...],
    property_type: int,
) -> AccountStatPropertyRow | None:
    for row in rows:
        if row.property_type == property_type:
            return row
    return None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float:
    text = str(value or "").replace("%", "").replace(",", "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:g}"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
