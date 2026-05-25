from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


DISPLAY_STAT_SCHEMA_VERSION = 1

DISPLAY_TOTALS_NOTE = "display_totals_provisional"
DISPLAY_TOTALS_EXCLUDE_PASSIVES = "display_totals_exclude_weapon_passives"
DISPLAY_TOTALS_EXCLUDE_SET_FORMULAS = "display_totals_exclude_set_bonus_formulas"
DISPLAY_TOTALS_EXCLUDE_RESONANCE = "display_totals_exclude_resonance"
DISPLAY_TOTALS_EXCLUDE_CONDITIONALS = "display_totals_exclude_conditional_bonuses"
DISPLAY_TOTALS_EXCLUDE_TALENTS_CONSTELLATIONS = (
    "display_totals_exclude_talents_constellations"
)
DISPLAY_TOTALS_SOURCE_HOYOLAB_STAT_SHEET = (
    "display_totals_from_hoyolab_account_detail_stat_sheet"
)
DISPLAY_TOTALS_USE_HOYOLAB_FINAL_VALUES = "display_totals_use_hoyolab_final_values"
DISPLAY_TOTALS_SOURCE_TEAM_BUILDER_VIRTUAL_BUILD = (
    "display_totals_from_team_builder_virtual_build"
)
DISPLAY_TOTALS_ACCOUNT_BASE_REFERENCE_HOYOLAB_STAT_SHEET = (
    "display_totals_account_base_from_hoyolab_stat_sheet"
)
DISPLAY_TOTALS_WEAPON_REFERENCE_HOYOLAB_STAT_SHEET = (
    "display_totals_weapon_reference_from_hoyolab_stat_sheet"
)
DISPLAY_TOTALS_INCLUDE_STATIC_ARTIFACT_SET_EFFECTS = (
    "display_totals_include_static_artifact_set_effects"
)
DISPLAY_TOTALS_INCLUDE_STATIC_WEAPON_PASSIVES = (
    "display_totals_include_static_weapon_passives"
)
DISPLAY_TOTALS_INCLUDE_ELEMENTAL_RESONANCE = (
    "display_totals_include_elemental_resonance"
)
DISPLAY_TOTALS_EXTERNAL_BONUSES_DISABLED = (
    "display_totals_external_bonuses_disabled"
)


TOTAL_HP = 2000
TOTAL_ATK = 2001
TOTAL_DEF = 2002
WEAPON_BASE_ATK = 4
HP_FLAT = 2
HP_PERCENT = 3
ATK_FLAT = 5
ATK_PERCENT = 6
DEF_FLAT = 8
DEF_PERCENT = 9
CRIT_RATE = 20
CRIT_DAMAGE = 22
ENERGY_RECHARGE = 23
HEALING_BONUS = 26
ELEMENTAL_MASTERY = 28
PHYSICAL_DAMAGE = 30
PYRO_DAMAGE = 40
ELECTRO_DAMAGE = 41
HYDRO_DAMAGE = 42
DENDRO_DAMAGE = 43
ANEMO_DAMAGE = 44
GEO_DAMAGE = 45
CRYO_DAMAGE = 46


DAMAGE_BONUS_TYPES = {
    PHYSICAL_DAMAGE: ("physical_dmg", "Physical DMG", "PHYS"),
    PYRO_DAMAGE: ("pyro_dmg", "Pyro DMG", "PYRO"),
    ELECTRO_DAMAGE: ("electro_dmg", "Electro DMG", "ELEC"),
    HYDRO_DAMAGE: ("hydro_dmg", "Hydro DMG", "HYD"),
    DENDRO_DAMAGE: ("dendro_dmg", "Dendro DMG", "DEN"),
    ANEMO_DAMAGE: ("anemo_dmg", "Anemo DMG", "ANE"),
    GEO_DAMAGE: ("geo_dmg", "Geo DMG", "GEO"),
    CRYO_DAMAGE: ("cryo_dmg", "Cryo DMG", "CRYO"),
}
ACCOUNT_STAT_SHEET_DISPLAY_ROWS = (
    (TOTAL_HP, "hp", "HP", "HP"),
    (TOTAL_ATK, "atk", "ATK", "ATK"),
    (TOTAL_DEF, "def", "DEF", "DEF"),
    (ELEMENTAL_MASTERY, "em", "EM", "EM"),
    (CRIT_RATE, "crit_rate", "Crit Rate", "CR"),
    (CRIT_DAMAGE, "crit_damage", "Crit DMG", "CD"),
    (ENERGY_RECHARGE, "energy_recharge", "ER", "ER"),
    (PYRO_DAMAGE, "pyro_dmg", "Pyro DMG", "PYRO"),
    (HYDRO_DAMAGE, "hydro_dmg", "Hydro DMG", "HYD"),
    (ELECTRO_DAMAGE, "electro_dmg", "Electro DMG", "ELEC"),
    (CRYO_DAMAGE, "cryo_dmg", "Cryo DMG", "CRYO"),
    (ANEMO_DAMAGE, "anemo_dmg", "Anemo DMG", "ANE"),
    (GEO_DAMAGE, "geo_dmg", "Geo DMG", "GEO"),
    (DENDRO_DAMAGE, "dendro_dmg", "Dendro DMG", "DEN"),
    (PHYSICAL_DAMAGE, "physical_dmg", "Physical DMG", "PHYS"),
    (HEALING_BONUS, "healing_bonus", "Healing Bonus", "HEAL"),
)

ARTIFACT_PROPERTY_TO_BONUS = {
    HP_FLAT: ("hp_flat", False),
    HP_PERCENT: ("hp_percent", True),
    ATK_FLAT: ("atk_flat", False),
    ATK_PERCENT: ("atk_percent", True),
    DEF_FLAT: ("def_flat", False),
    DEF_PERCENT: ("def_percent", True),
    CRIT_RATE: ("crit_rate", True),
    CRIT_DAMAGE: ("crit_damage", True),
    ENERGY_RECHARGE: ("energy_recharge", True),
    HEALING_BONUS: ("healing_bonus", True),
    ELEMENTAL_MASTERY: ("elemental_mastery", False),
    PHYSICAL_DAMAGE: ("physical_dmg", True),
    PYRO_DAMAGE: ("pyro_dmg", True),
    ELECTRO_DAMAGE: ("electro_dmg", True),
    HYDRO_DAMAGE: ("hydro_dmg", True),
    DENDRO_DAMAGE: ("dendro_dmg", True),
    ANEMO_DAMAGE: ("anemo_dmg", True),
    GEO_DAMAGE: ("geo_dmg", True),
    CRYO_DAMAGE: ("cryo_dmg", True),
}

STATIC_EFFECT_STAT_TO_BONUS = {
    "HP_FLAT": "hp_flat",
    "HP_PERCENT": "hp_percent",
    "ATK_FLAT": "atk_flat",
    "ATK_PERCENT": "atk_percent",
    "DEF_FLAT": "def_flat",
    "DEF_PERCENT": "def_percent",
    "ELEMENTAL_MASTERY": "elemental_mastery",
    "ENERGY_RECHARGE": "energy_recharge",
    "CRIT_RATE": "crit_rate",
    "CRIT_DMG": "crit_damage",
    "PYRO_DMG_BONUS": "pyro_dmg",
    "HYDRO_DMG_BONUS": "hydro_dmg",
    "ELECTRO_DMG_BONUS": "electro_dmg",
    "CRYO_DMG_BONUS": "cryo_dmg",
    "ANEMO_DMG_BONUS": "anemo_dmg",
    "GEO_DMG_BONUS": "geo_dmg",
    "DENDRO_DMG_BONUS": "dendro_dmg",
    "PHYSICAL_DMG_BONUS": "physical_dmg",
    "ALL_ELEMENTAL_DMG_BONUS": "",
    "HEALING_BONUS": "healing_bonus",
}

STAT_LABEL_ALIASES = {
    "hp": "hp",
    "hp%": "hp_percent",
    "max hp": "hp",
    "atk": "atk",
    "atk%": "atk_percent",
    "attack": "atk",
    "def": "def",
    "def%": "def_percent",
    "defense": "def",
    "energy recharge": "energy_recharge",
    "er": "energy_recharge",
    "elemental mastery": "elemental_mastery",
    "em": "elemental_mastery",
    "crit rate": "crit_rate",
    "critical rate": "crit_rate",
    "cr": "crit_rate",
    "crit dmg": "crit_damage",
    "crit damage": "crit_damage",
    "critical damage": "crit_damage",
    "cd": "crit_damage",
    "healing bonus": "healing_bonus",
    "heal": "healing_bonus",
    "physical dmg bonus": "physical_dmg",
    "physical damage bonus": "physical_dmg",
    "pyro dmg bonus": "pyro_dmg",
    "pyro damage bonus": "pyro_dmg",
    "hydro dmg bonus": "hydro_dmg",
    "hydro damage bonus": "hydro_dmg",
    "electro dmg bonus": "electro_dmg",
    "electro damage bonus": "electro_dmg",
    "cryo dmg bonus": "cryo_dmg",
    "cryo damage bonus": "cryo_dmg",
    "anemo dmg bonus": "anemo_dmg",
    "anemo damage bonus": "anemo_dmg",
    "geo dmg bonus": "geo_dmg",
    "geo damage bonus": "geo_dmg",
    "dendro dmg bonus": "dendro_dmg",
    "dendro damage bonus": "dendro_dmg",
}


@dataclass(frozen=True, slots=True)
class DisplayedStatRow:
    key: str
    label: str
    value: str
    icon_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "value": self.value,
            "icon_label": self.icon_label,
        }


@dataclass(frozen=True, slots=True)
class CharacterDisplayStats:
    rows: tuple[DisplayedStatRow, ...]
    notes: tuple[str, ...] = (
        DISPLAY_TOTALS_NOTE,
        DISPLAY_TOTALS_EXCLUDE_PASSIVES,
        DISPLAY_TOTALS_EXCLUDE_SET_FORMULAS,
        DISPLAY_TOTALS_EXCLUDE_RESONANCE,
        DISPLAY_TOTALS_EXCLUDE_CONDITIONALS,
        DISPLAY_TOTALS_EXCLUDE_TALENTS_CONSTELLATIONS,
    )
    schema_version: int = DISPLAY_STAT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "rows": [row.to_dict() for row in self.rows],
            "notes": list(self.notes),
        }


def build_character_display_stats(value: Mapping[str, Any] | Any) -> CharacterDisplayStats:
    data = _to_mapping(value)
    snapshot = _to_mapping(data.get("stat_snapshot")) if "stat_snapshot" in data else data
    rows, source_notes = _display_rows_from_team_builder_virtual_sources(data, snapshot)
    resonance_notes = (
        []
        if DISPLAY_TOTALS_INCLUDE_ELEMENTAL_RESONANCE in source_notes
        else [DISPLAY_TOTALS_EXCLUDE_RESONANCE]
    )
    return CharacterDisplayStats(
        rows=tuple(rows),
        notes=tuple(
            _dedupe(
                [
                    DISPLAY_TOTALS_SOURCE_TEAM_BUILDER_VIRTUAL_BUILD,
                    *source_notes,
                    DISPLAY_TOTALS_NOTE,
                    DISPLAY_TOTALS_EXCLUDE_PASSIVES,
                    DISPLAY_TOTALS_EXCLUDE_SET_FORMULAS,
                    *resonance_notes,
                    DISPLAY_TOTALS_EXCLUDE_CONDITIONALS,
                    DISPLAY_TOTALS_EXCLUDE_TALENTS_CONSTELLATIONS,
                ]
            )
        ),
    )


def _display_rows_from_team_builder_virtual_sources(
    data: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> tuple[list[DisplayedStatRow], list[str]]:
    stat_sheet = _to_mapping(data.get("account_stat_sheet"))

    character_base = _to_mapping(snapshot.get("character_base"))
    weapon = _to_mapping(snapshot.get("weapon"))
    artifact = _to_mapping(snapshot.get("artifact"))
    artifact_summary = _to_mapping(artifact.get("summary"))
    source_notes: list[str] = []
    external_bonuses_enabled = bool(data.get("external_bonuses_enabled", True))

    base_hp, base_atk, base_def, base_source_notes = _virtual_character_base_values(
        data,
        stat_sheet,
        character_base,
    )
    source_notes.extend(base_source_notes)
    weapon_atk, weapon_source_notes = _virtual_selected_weapon_base_atk(
        data,
        stat_sheet,
        weapon,
    )
    source_notes.extend(weapon_source_notes)

    bonuses = _empty_bonuses()
    _apply_virtual_ascension_bonus(bonuses, data, character_base)
    _apply_virtual_weapon_secondary(bonuses, data, stat_sheet, weapon)
    for stat in artifact_summary.get("stat_totals") or []:
        if isinstance(stat, Mapping):
            _apply_artifact_bonus(bonuses, stat)
    if external_bonuses_enabled:
        for effect in data.get("team_bonus_display_stat_effects") or []:
            if isinstance(effect, Mapping):
                if _apply_static_display_effect(bonuses, effect):
                    source_notes.append(DISPLAY_TOTALS_INCLUDE_ELEMENTAL_RESONANCE)
        for effect in data.get("artifact_set_display_stat_effects") or []:
            if isinstance(effect, Mapping):
                if _apply_static_display_effect(bonuses, effect):
                    source_notes.append(DISPLAY_TOTALS_INCLUDE_STATIC_ARTIFACT_SET_EFFECTS)
        for effect in data.get("weapon_display_stat_effects") or []:
            if isinstance(effect, Mapping):
                if _apply_static_display_effect(bonuses, effect):
                    source_notes.append(DISPLAY_TOTALS_INCLUDE_STATIC_WEAPON_PASSIVES)
    else:
        source_notes.append(DISPLAY_TOTALS_EXTERNAL_BONUSES_DISABLED)

    rows: list[DisplayedStatRow] = []
    hp = base_hp * (1 + bonuses["hp_percent"] / 100.0) + bonuses["hp_flat"]
    atk = (base_atk + weapon_atk) * (1 + bonuses["atk_percent"] / 100.0) + bonuses["atk_flat"]
    defense = base_def * (1 + bonuses["def_percent"] / 100.0) + bonuses["def_flat"]

    if hp > 0:
        rows.append(_row("hp", "HP", _format_number(hp), "HP"))
    if atk > 0:
        rows.append(_row("atk", "ATK", _format_number(atk), "ATK"))
    if defense > 0:
        rows.append(_row("def", "DEF", _format_number(defense), "DEF"))
    if bonuses["elemental_mastery"] > 0:
        rows.append(_row("em", "EM", _format_number(bonuses["elemental_mastery"]), "EM"))

    rows.append(_row("crit_rate", "Crit Rate", _format_percent(5.0 + bonuses["crit_rate"]), "CR"))
    rows.append(_row("crit_damage", "Crit DMG", _format_percent(50.0 + bonuses["crit_damage"]), "CD"))
    rows.append(_row("energy_recharge", "ER", _format_percent(100.0 + bonuses["energy_recharge"]), "ER"))

    for property_type in (
        PYRO_DAMAGE,
        HYDRO_DAMAGE,
        ELECTRO_DAMAGE,
        CRYO_DAMAGE,
        ANEMO_DAMAGE,
        GEO_DAMAGE,
        DENDRO_DAMAGE,
        PHYSICAL_DAMAGE,
    ):
        key, label, icon_label = DAMAGE_BONUS_TYPES[property_type]
        if bonuses[key] > 0:
            rows.append(_row(key, label, _format_percent(bonuses[key]), icon_label))

    if bonuses["healing_bonus"] > 0:
        rows.append(
            _row(
                "healing_bonus",
                "Healing Bonus",
                _format_percent(bonuses["healing_bonus"]),
                "HEAL",
            )
        )

    return rows, source_notes


def _virtual_character_base_values(
    data: Mapping[str, Any],
    stat_sheet: Mapping[str, Any],
    snapshot_character_base: Mapping[str, Any],
) -> tuple[float, float, float, list[str]]:
    base_rows = _account_sheet_group_rows_by_property_type(
        stat_sheet,
        "base_properties",
    )
    notes: list[str] = []

    hp_row = base_rows.get(TOTAL_HP)
    atk_row = base_rows.get(TOTAL_ATK)
    def_row = base_rows.get(TOTAL_DEF)

    base_hp = _number(hp_row.get("base") if hp_row is not None else "")
    base_def = _number(def_row.get("base") if def_row is not None else "")

    account_base_atk = _number(atk_row.get("base") if atk_row is not None else "")
    current_weapon_atk = _account_stat_sheet_weapon_base_atk(stat_sheet)
    base_atk = account_base_atk - current_weapon_atk if account_base_atk and current_weapon_atk else 0.0
    if base_atk < 0:
        base_atk = 0.0

    if base_hp or base_atk or base_def:
        notes.append(DISPLAY_TOTALS_ACCOUNT_BASE_REFERENCE_HOYOLAB_STAT_SHEET)

    account_character = _to_mapping(data.get("account_character"))
    if not base_hp:
        base_hp = _number(account_character.get("base_hp"))
    if not base_atk:
        base_atk = _number(account_character.get("base_atk"))
    if not base_def:
        base_def = _number(account_character.get("base_def"))
    if (base_hp or base_atk or base_def) and not notes:
        notes.append(DISPLAY_TOTALS_ACCOUNT_BASE_REFERENCE_HOYOLAB_STAT_SHEET)

    if not base_hp:
        base_hp = _selected_number(snapshot_character_base.get("base_hp"))
    if not base_atk:
        base_atk = _selected_number(snapshot_character_base.get("base_atk"))
    if not base_def:
        base_def = _selected_number(snapshot_character_base.get("base_def"))

    return base_hp, base_atk, base_def, notes


def _virtual_selected_weapon_base_atk(
    data: Mapping[str, Any],
    stat_sheet: Mapping[str, Any],
    snapshot_weapon: Mapping[str, Any],
) -> tuple[float, list[str]]:
    selected_weapon_atk = _selected_number(snapshot_weapon.get("base_atk"))
    if selected_weapon_atk:
        return selected_weapon_atk, []

    account_weapon = _to_mapping(data.get("account_weapon"))
    for key in ("base_atk", "weapon_base_atk"):
        selected_weapon_atk = _number(account_weapon.get(key))
        if selected_weapon_atk:
            return selected_weapon_atk, []

    account_sheet_weapon_atk = _account_stat_sheet_weapon_base_atk(stat_sheet)
    if account_sheet_weapon_atk:
        return account_sheet_weapon_atk, [DISPLAY_TOTALS_WEAPON_REFERENCE_HOYOLAB_STAT_SHEET]
    return 0.0, []


def _apply_virtual_ascension_bonus(
    bonuses: dict[str, float],
    data: Mapping[str, Any],
    character_base: Mapping[str, Any],
) -> None:
    stat_type = character_base.get("ascension_bonus_stat_type")
    value = _selected_text(character_base.get("ascension_bonus"))
    value_from_account_runtime = False
    if not stat_type or not value:
        ascension_bonus = _to_mapping(data.get("ascension_bonus"))
        stat_type = ascension_bonus.get("stat_type")
        value = _text(ascension_bonus.get("selected_value"))
        value_from_account_runtime = (
            _text(ascension_bonus.get("source")) == "account_sqlite_character_reference"
        )
    if not stat_type or not value:
        account_character = _to_mapping(data.get("account_character"))
        stat_type = account_character.get("ascension_bonus_stat_type")
        value = _text(account_character.get("ascension_bonus_value"))
        value_from_account_runtime = True
    if value_from_account_runtime:
        value = _account_runtime_ascension_bonus_value(stat_type, value)
    _apply_named_bonus(bonuses, stat_type, value)


def _account_runtime_ascension_bonus_value(raw_label: Any, raw_value: Any) -> str:
    value = _text(raw_value)
    if not value or "%" in value:
        return value
    if _normalize_stat_label(raw_label) in {"hp", "atk", "def"}:
        return f"{value}%"
    return value


def _apply_virtual_weapon_secondary(
    bonuses: dict[str, float],
    data: Mapping[str, Any],
    stat_sheet: Mapping[str, Any],
    snapshot_weapon: Mapping[str, Any],
) -> None:
    secondary_type = snapshot_weapon.get("secondary_stat_type")
    secondary_value = str(snapshot_weapon.get("secondary_stat_value") or "")
    if secondary_type and secondary_value:
        _apply_named_bonus(bonuses, secondary_type, secondary_value)
        return

    account_weapon = _to_mapping(data.get("account_weapon"))
    property_type = _optional_int(account_weapon.get("secondary_property_type"))
    value = account_weapon.get("secondary_stat_value_raw")
    if value in (None, ""):
        value = account_weapon.get("secondary_stat_value")
    if property_type is not None and value not in (None, ""):
        _apply_property_bonus(bonuses, property_type, value)
        return

    weapon_sheet = _to_mapping(stat_sheet.get("weapon"))
    sub_property = _to_mapping(weapon_sheet.get("sub_property"))
    property_type = _optional_int(sub_property.get("property_type"))
    if property_type is None:
        return
    _apply_property_bonus(
        bonuses,
        property_type,
        sub_property.get("final") or sub_property.get("base"),
    )


def _account_stat_sheet_weapon_base_atk(stat_sheet: Mapping[str, Any]) -> float:
    weapon_sheet = _to_mapping(stat_sheet.get("weapon"))
    main_property = _to_mapping(weapon_sheet.get("main_property"))
    property_type = _optional_int(main_property.get("property_type"))
    if property_type != WEAPON_BASE_ATK:
        return 0.0
    return _number(main_property.get("final") or main_property.get("base"))


def _display_rows_from_account_stat_sheet(
    stat_sheet: Mapping[str, Any],
) -> list[DisplayedStatRow]:
    rows_by_property_type = _account_sheet_rows_by_property_type(stat_sheet)
    rows: list[DisplayedStatRow] = []
    for property_type, key, label, icon_label in ACCOUNT_STAT_SHEET_DISPLAY_ROWS:
        raw_row = rows_by_property_type.get(property_type)
        if raw_row is None:
            continue
        value = _text(raw_row.get("final") or raw_row.get("base"))
        if not value or _is_zero_stat_sheet_value(value):
            continue
        rows.append(_row(key, label, value, icon_label))
    return rows


def _account_sheet_rows_by_property_type(
    stat_sheet: Mapping[str, Any],
) -> dict[int, dict[str, Any]]:
    rows_by_property_type: dict[int, dict[str, Any]] = {}
    for group_name in (
        "base_properties",
        "extra_properties",
        "element_properties",
        "selected_properties",
    ):
        for row in stat_sheet.get(group_name) or []:
            if not isinstance(row, Mapping):
                continue
            property_type = _optional_int(row.get("property_type"))
            if property_type is None or property_type in rows_by_property_type:
                continue
            rows_by_property_type[property_type] = dict(row)
    return rows_by_property_type


def _account_sheet_group_rows_by_property_type(
    stat_sheet: Mapping[str, Any],
    group_name: str,
) -> dict[int, dict[str, Any]]:
    rows_by_property_type: dict[int, dict[str, Any]] = {}
    for row in stat_sheet.get(group_name) or []:
        if not isinstance(row, Mapping):
            continue
        property_type = _optional_int(row.get("property_type"))
        if property_type is None:
            continue
        rows_by_property_type[property_type] = dict(row)
    return rows_by_property_type


def _is_zero_stat_sheet_value(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    numeric = text.replace("%", "").replace(",", "")
    try:
        return float(numeric) == 0
    except ValueError:
        return False


def _empty_bonuses() -> dict[str, float]:
    return {
        "hp_flat": 0.0,
        "hp_percent": 0.0,
        "atk_flat": 0.0,
        "atk_percent": 0.0,
        "def_flat": 0.0,
        "def_percent": 0.0,
        "elemental_mastery": 0.0,
        "crit_rate": 0.0,
        "crit_damage": 0.0,
        "energy_recharge": 0.0,
        "healing_bonus": 0.0,
        "physical_dmg": 0.0,
        "pyro_dmg": 0.0,
        "hydro_dmg": 0.0,
        "electro_dmg": 0.0,
        "cryo_dmg": 0.0,
        "anemo_dmg": 0.0,
        "geo_dmg": 0.0,
        "dendro_dmg": 0.0,
    }


def _apply_named_bonus(
    bonuses: dict[str, float],
    raw_label: Any,
    raw_value: Any,
) -> None:
    label = _normalize_stat_label(raw_label)
    amount, is_percent = _parse_stat_value(raw_value)
    if amount == 0:
        return

    if label in {"hp", "atk", "def"}:
        bonuses[f"{label}_percent" if is_percent else f"{label}_flat"] += amount
        return
    if label in bonuses:
        bonuses[label] += amount


def _apply_artifact_bonus(
    bonuses: dict[str, float],
    stat: Mapping[str, Any],
) -> None:
    property_type = _optional_int(stat.get("property_type"))
    _apply_property_bonus(bonuses, property_type, stat.get("raw_value") or stat.get("value"))


def _apply_property_bonus(
    bonuses: dict[str, float],
    property_type: int | None,
    raw_value: Any,
) -> None:
    if property_type not in ARTIFACT_PROPERTY_TO_BONUS:
        return
    key, _is_percent = ARTIFACT_PROPERTY_TO_BONUS[int(property_type)]
    amount, _parsed_percent = _parse_stat_value(raw_value)
    bonuses[key] += amount


def _apply_static_display_effect(
    bonuses: dict[str, float],
    effect: Mapping[str, Any],
) -> bool:
    stat_key = str(effect.get("stat_key") or "").strip().upper()
    amount = _number(effect.get("value"))
    if not stat_key or amount == 0:
        return False
    target = STATIC_EFFECT_STAT_TO_BONUS.get(stat_key)
    if target is None:
        return False
    if stat_key == "ALL_ELEMENTAL_DMG_BONUS":
        for key in (
            "pyro_dmg",
            "hydro_dmg",
            "electro_dmg",
            "cryo_dmg",
            "anemo_dmg",
            "geo_dmg",
            "dendro_dmg",
        ):
            bonuses[key] += amount
        return True
    bonuses[target] += amount
    return True


def _selected_number(value: Any) -> float:
    return _number(_selected_text(value))


def _selected_text(value: Any) -> str:
    data = _to_mapping(value)
    if data:
        return str(data.get("selected") or "").strip()
    return str(value or "").strip()


def _parse_stat_value(value: Any) -> tuple[float, bool]:
    text = str(value or "").strip()
    is_percent = "%" in text
    return _number(text), is_percent


def _number(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    text = text.replace("%", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_stat_label(value: Any) -> str:
    text = str(value or "").strip().replace("_", " ").casefold()
    return STAT_LABEL_ALIASES.get(text, text)


def _row(key: str, label: str, value: str, icon_label: str) -> DisplayedStatRow:
    return DisplayedStatRow(
        key=key,
        label=label,
        value=value,
        icon_label=icon_label,
    )


def _format_number(value: float) -> str:
    rounded = round(value)
    return str(int(rounded))


def _format_percent(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return f"{int(round(value))}%"
    return f"{value:.1f}%"


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_mapping(value: Any) -> dict[str, Any]:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
    return dict(value) if isinstance(value, Mapping) else {}


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
