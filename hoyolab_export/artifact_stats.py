from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


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


ARTISCAN_STAT_KEY_TO_PROPERTY_TYPE = {
    "hp": HP_FLAT,
    "hp_": HP_PERCENT,
    "atk": ATK_FLAT,
    "atk_": ATK_PERCENT,
    "def": DEF_FLAT,
    "def_": DEF_PERCENT,
    "critRate_": CRIT_RATE,
    "critDMG_": CRIT_DAMAGE,
    "enerRech_": ENERGY_RECHARGE,
    "heal_": HEALING_BONUS,
    "eleMas": ELEMENTAL_MASTERY,
    "physical_dmg_": PHYSICAL_DAMAGE,
    "pyro_dmg_": PYRO_DAMAGE,
    "electro_dmg_": ELECTRO_DAMAGE,
    "hydro_dmg_": HYDRO_DAMAGE,
    "dendro_dmg_": DENDRO_DAMAGE,
    "anemo_dmg_": ANEMO_DAMAGE,
    "geo_dmg_": GEO_DAMAGE,
    "cryo_dmg_": CRYO_DAMAGE,
}


PROPERTY_TYPE_NAMES = {
    HP_FLAT: "HP",
    HP_PERCENT: "HP%",
    ATK_FLAT: "ATK",
    ATK_PERCENT: "ATK%",
    DEF_FLAT: "DEF",
    DEF_PERCENT: "DEF%",
    CRIT_RATE: "CRIT Rate",
    CRIT_DAMAGE: "CRIT DMG",
    ENERGY_RECHARGE: "Energy Recharge",
    HEALING_BONUS: "Healing Bonus",
    ELEMENTAL_MASTERY: "Elemental Mastery",
    PHYSICAL_DAMAGE: "Physical DMG Bonus",
    PYRO_DAMAGE: "Pyro DMG Bonus",
    ELECTRO_DAMAGE: "Electro DMG Bonus",
    HYDRO_DAMAGE: "Hydro DMG Bonus",
    DENDRO_DAMAGE: "Dendro DMG Bonus",
    ANEMO_DAMAGE: "Anemo DMG Bonus",
    GEO_DAMAGE: "Geo DMG Bonus",
    CRYO_DAMAGE: "Cryo DMG Bonus",
}


PERCENT_ARTISCAN_STAT_KEYS = {
    "hp_",
    "atk_",
    "def_",
    "critRate_",
    "critDMG_",
    "enerRech_",
    "heal_",
    "physical_dmg_",
    "pyro_dmg_",
    "electro_dmg_",
    "hydro_dmg_",
    "dendro_dmg_",
    "anemo_dmg_",
    "geo_dmg_",
    "cryo_dmg_",
}


# Artiscan does not include main stat values. MVP import supports the sample
# rarity (5-star) with deterministic max-level values.
ARTISCAN_MAX_MAIN_STAT_VALUES = {
    (5, "hp"): "4780",
    (5, "atk"): "311",
    (5, "hp_"): "46.6%",
    (5, "atk_"): "46.6%",
    (5, "def_"): "58.3%",
    (5, "eleMas"): "187",
    (5, "enerRech_"): "51.8%",
    (5, "critRate_"): "31.1%",
    (5, "critDMG_"): "62.2%",
    (5, "heal_"): "35.9%",
    (5, "physical_dmg_"): "58.3%",
    (5, "pyro_dmg_"): "46.6%",
    (5, "electro_dmg_"): "46.6%",
    (5, "hydro_dmg_"): "46.6%",
    (5, "dendro_dmg_"): "46.6%",
    (5, "anemo_dmg_"): "46.6%",
    (5, "geo_dmg_"): "46.6%",
    (5, "cryo_dmg_"): "46.6%",
}


def property_name(property_type: int | None) -> str | None:
    if property_type is None:
        return None
    return PROPERTY_TYPE_NAMES.get(int(property_type), str(property_type))


def artiscan_property_type(stat_key: str | None) -> int | None:
    return ARTISCAN_STAT_KEY_TO_PROPERTY_TYPE.get(str(stat_key or ""))


def artiscan_max_main_stat_value(rarity: int, stat_key: str) -> str | None:
    return ARTISCAN_MAX_MAIN_STAT_VALUES.get((int(rarity), stat_key))


def format_artiscan_substat_value(stat_key: str, value: Any) -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        return ""

    try:
        decimal = Decimal(text)
    except InvalidOperation:
        formatted = text
    else:
        formatted = format(decimal.normalize(), "f")
        if "." in formatted:
            formatted = formatted.rstrip("0").rstrip(".")

    if stat_key in PERCENT_ARTISCAN_STAT_KEYS:
        return f"{formatted}%"
    return formatted
