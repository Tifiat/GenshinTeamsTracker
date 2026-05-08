from __future__ import annotations


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


def stat_badge(property_type: int) -> str:
    return STAT_BADGES[property_type]


def is_crit_type(property_type: int) -> bool:
    return property_type in CRIT_TYPES