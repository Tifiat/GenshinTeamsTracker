from __future__ import annotations

from dataclasses import dataclass


# Virtual sort key, not a HoYoLAB property type.
CRIT_VALUE = -1
PROC_COUNT = -2

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


CRIT_TYPES = {CRIT_RATE, CRIT_DAMAGE}


STAT_BADGES = {
    HP_FLAT: "HP",
    HP_PERCENT: "HP%",
    ATK_FLAT: "ATK",
    ATK_PERCENT: "ATK%",
    DEF_FLAT: "DEF",
    DEF_PERCENT: "DEF%",
    CRIT_RATE: "CR",
    CRIT_DAMAGE: "CD",
    ENERGY_RECHARGE: "ER",
    HEALING_BONUS: "Heal",
    ELEMENTAL_MASTERY: "EM",
    PHYSICAL_DAMAGE: "Phys",
    PYRO_DAMAGE: "Pyro",
    ELECTRO_DAMAGE: "Electro",
    HYDRO_DAMAGE: "Hydro",
    DENDRO_DAMAGE: "Dendro",
    ANEMO_DAMAGE: "Anemo",
    GEO_DAMAGE: "Geo",
    CRYO_DAMAGE: "Cryo",
}


STAT_LABEL_KEYS = {
    CRIT_VALUE: "artifact.stat.crit_value",
    PROC_COUNT: "artifact.stat.proc_count",
    HP_FLAT: "artifact.stat.hp_flat",
    HP_PERCENT: "artifact.stat.hp_percent",
    ATK_FLAT: "artifact.stat.atk_flat",
    ATK_PERCENT: "artifact.stat.atk_percent",
    DEF_FLAT: "artifact.stat.def_flat",
    DEF_PERCENT: "artifact.stat.def_percent",
    CRIT_RATE: "artifact.stat.crit_rate",
    CRIT_DAMAGE: "artifact.stat.crit_damage",
    ENERGY_RECHARGE: "artifact.stat.energy_recharge",
    HEALING_BONUS: "artifact.stat.healing_bonus",
    ELEMENTAL_MASTERY: "artifact.stat.elemental_mastery",
    PHYSICAL_DAMAGE: "artifact.stat.physical_damage",
    PYRO_DAMAGE: "artifact.stat.pyro_damage",
    ELECTRO_DAMAGE: "artifact.stat.electro_damage",
    HYDRO_DAMAGE: "artifact.stat.hydro_damage",
    DENDRO_DAMAGE: "artifact.stat.dendro_damage",
    ANEMO_DAMAGE: "artifact.stat.anemo_damage",
    GEO_DAMAGE: "artifact.stat.geo_damage",
    CRYO_DAMAGE: "artifact.stat.cryo_damage",
}


@dataclass(frozen=True, slots=True)
class SortableStatOption:
    property_type: int
    label_key: str


SORTABLE_STAT_OPTIONS = [
    SortableStatOption(CRIT_VALUE, STAT_LABEL_KEYS[CRIT_VALUE]),
    SortableStatOption(CRIT_RATE, STAT_LABEL_KEYS[CRIT_RATE]),
    SortableStatOption(CRIT_DAMAGE, STAT_LABEL_KEYS[CRIT_DAMAGE]),

    SortableStatOption(ATK_PERCENT, STAT_LABEL_KEYS[ATK_PERCENT]),
    SortableStatOption(HP_PERCENT, STAT_LABEL_KEYS[HP_PERCENT]),
    SortableStatOption(DEF_PERCENT, STAT_LABEL_KEYS[DEF_PERCENT]),

    SortableStatOption(ELEMENTAL_MASTERY, STAT_LABEL_KEYS[ELEMENTAL_MASTERY]),
    SortableStatOption(ENERGY_RECHARGE, STAT_LABEL_KEYS[ENERGY_RECHARGE]),

    SortableStatOption(PYRO_DAMAGE, STAT_LABEL_KEYS[PYRO_DAMAGE]),
    SortableStatOption(ELECTRO_DAMAGE, STAT_LABEL_KEYS[ELECTRO_DAMAGE]),
    SortableStatOption(HYDRO_DAMAGE, STAT_LABEL_KEYS[HYDRO_DAMAGE]),
    SortableStatOption(DENDRO_DAMAGE, STAT_LABEL_KEYS[DENDRO_DAMAGE]),
    SortableStatOption(ANEMO_DAMAGE, STAT_LABEL_KEYS[ANEMO_DAMAGE]),
    SortableStatOption(GEO_DAMAGE, STAT_LABEL_KEYS[GEO_DAMAGE]),
    SortableStatOption(CRYO_DAMAGE, STAT_LABEL_KEYS[CRYO_DAMAGE]),

    SortableStatOption(HEALING_BONUS, STAT_LABEL_KEYS[HEALING_BONUS]),
    SortableStatOption(PHYSICAL_DAMAGE, STAT_LABEL_KEYS[PHYSICAL_DAMAGE]),

    SortableStatOption(ATK_FLAT, STAT_LABEL_KEYS[ATK_FLAT]),
    SortableStatOption(DEF_FLAT, STAT_LABEL_KEYS[DEF_FLAT]),
    SortableStatOption(HP_FLAT, STAT_LABEL_KEYS[HP_FLAT]),

    SortableStatOption(PROC_COUNT, STAT_LABEL_KEYS[PROC_COUNT]),
]


def stat_badge(property_type: int) -> str:
    return STAT_BADGES[property_type]


def stat_label_key(property_type: int) -> str:
    return STAT_LABEL_KEYS[property_type]


def sortable_stat_options() -> list[SortableStatOption]:
    return list(SORTABLE_STAT_OPTIONS)


def is_crit_type(property_type: int) -> bool:
    return property_type in CRIT_TYPES
