"""Canonical artifact investment rules shared by formula search boundaries.

The values in this module are game configuration, not character heuristics.
They deliberately contain no artifact enumeration, optimizer strategy, engine
runner, UI state or account data.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Mapping


ARTIFACT_INVESTMENT_RULES_KIND = "gtt.artifact_investment_rules"
ARTIFACT_INVESTMENT_RULES_SCHEMA_VERSION = 1

FIVE_STAR_ARTIFACTS_PER_BUILD = 5
FIVE_STAR_MAX_STARTING_SUBSTATS = 4
FIVE_STAR_UPGRADE_EVENTS = 5
FIVE_STAR_MAX_ROLLS_PER_ARTIFACT = (
    FIVE_STAR_MAX_STARTING_SUBSTATS + FIVE_STAR_UPGRADE_EVENTS
)
FIVE_STAR_MAX_ROLL_UNITS_PER_WEARER = (
    FIVE_STAR_ARTIFACTS_PER_BUILD * FIVE_STAR_MAX_ROLLS_PER_ARTIFACT
)
FIVE_STAR_MAX_ROLLS_PER_STAT_PER_ELIGIBLE_PIECE = 1 + FIVE_STAR_UPGRADE_EVENTS

ROLL_VALUE_QUALITIES = (0.7, 0.8, 0.9, 1.0)


@dataclass(frozen=True, slots=True)
class FiveStarSubstatRollRule:
    stat_key: str
    values: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        if not self.stat_key or self.stat_key != self.stat_key.strip():
            raise ValueError("stat_key must be a non-empty trimmed string")
        if len(self.values) != len(ROLL_VALUE_QUALITIES):
            raise ValueError("a five-star substat must have four roll tiers")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) <= 0.0
            for value in self.values
        ):
            raise ValueError("substat roll values must be finite and positive")
        if tuple(sorted(self.values)) != self.values:
            raise ValueError("substat roll values must be strictly ordered")

    @property
    def maximum(self) -> float:
        return float(self.values[-1])

    @property
    def expected(self) -> float:
        return sum(float(value) for value in self.values) / len(self.values)

    def value_for_max_roll_units(self, roll_units: float) -> float:
        if (
            isinstance(roll_units, bool)
            or not isinstance(roll_units, (int, float))
            or not math.isfinite(float(roll_units))
            or float(roll_units) < 0.0
        ):
            raise ValueError("roll_units must be finite and non-negative")
        return self.maximum * float(roll_units)


FIVE_STAR_SUBSTAT_ROLL_RULES: Mapping[str, FiveStarSubstatRollRule] = (
    MappingProxyType(
        {
            "hp": FiveStarSubstatRollRule(
                "hp", (209.13, 239.00, 268.88, 298.75)
            ),
            "atk": FiveStarSubstatRollRule(
                "atk", (13.62, 15.56, 17.51, 19.45)
            ),
            "def": FiveStarSubstatRollRule(
                "def", (16.20, 18.52, 20.83, 23.15)
            ),
            "hp%": FiveStarSubstatRollRule(
                "hp%", (0.0408, 0.0466, 0.0525, 0.0583)
            ),
            "atk%": FiveStarSubstatRollRule(
                "atk%", (0.0408, 0.0466, 0.0525, 0.0583)
            ),
            "def%": FiveStarSubstatRollRule(
                "def%", (0.0510, 0.0583, 0.0656, 0.0729)
            ),
            "em": FiveStarSubstatRollRule(
                "em", (16.32, 18.65, 20.98, 23.31)
            ),
            "er": FiveStarSubstatRollRule(
                "er", (0.0453, 0.0518, 0.0583, 0.0648)
            ),
            "cr": FiveStarSubstatRollRule(
                "cr", (0.0272, 0.0311, 0.0350, 0.0389)
            ),
            "cd": FiveStarSubstatRollRule(
                "cd", (0.0544, 0.0622, 0.0699, 0.0777)
            ),
        }
    )
)


# Strings preserve the already-established GCSIM config rendering contract.
FIVE_STAR_MAIN_STAT_VALUES: Mapping[str, str] = MappingProxyType(
    {
        "hp": "4780",
        "atk": "311",
        "hp%": "0.466",
        "atk%": "0.466",
        "def%": "0.583",
        "em": "186.5",
        "er": "0.518",
        "cr": "0.311",
        "cd": "0.622",
        "pyro%": "0.466",
        "hydro%": "0.466",
        "electro%": "0.466",
        "cryo%": "0.466",
        "anemo%": "0.466",
        "geo%": "0.466",
        "dendro%": "0.466",
        "phys%": "0.583",
        "heal": "0.359",
    }
)

# Retained here because the existing GCSIM config renderer owns both rarity
# contracts. Continuous target v1 consumes only the five-star table above.
FOUR_STAR_MAIN_STAT_VALUES: Mapping[str, str] = MappingProxyType(
    {
        "hp": "3571",
        "atk": "232",
        "hp%": "0.348",
        "atk%": "0.348",
        "def%": "0.435",
        "em": "139",
        "er": "0.387",
        "cr": "0.232",
        "cd": "0.464",
        "pyro%": "0.348",
        "hydro%": "0.348",
        "electro%": "0.348",
        "cryo%": "0.348",
        "anemo%": "0.348",
        "geo%": "0.348",
        "dendro%": "0.348",
        "phys%": "0.435",
        "heal": "0.268",
    }
)

ARTIFACT_MAIN_STAT_SLOTS = ("flower", "plume", "sands", "goblet", "circlet")
LEGAL_FIVE_STAR_SANDS_MAIN_STATS = ("hp%", "atk%", "def%", "em", "er")
LEGAL_FIVE_STAR_GOBLET_MAIN_STATS = (
    "hp%",
    "atk%",
    "def%",
    "em",
    "pyro%",
    "hydro%",
    "electro%",
    "cryo%",
    "anemo%",
    "geo%",
    "dendro%",
    "phys%",
)
LEGAL_FIVE_STAR_CIRCLET_MAIN_STATS = (
    "hp%",
    "atk%",
    "def%",
    "em",
    "cr",
    "cd",
    "heal",
)
LEGAL_FIVE_STAR_MAIN_STATS_BY_SLOT: Mapping[str, tuple[str, ...]] = (
    MappingProxyType(
        {
            "flower": ("hp",),
            "plume": ("atk",),
            "sands": LEGAL_FIVE_STAR_SANDS_MAIN_STATS,
            "goblet": LEGAL_FIVE_STAR_GOBLET_MAIN_STATS,
            "circlet": LEGAL_FIVE_STAR_CIRCLET_MAIN_STATS,
        }
    )
)


def five_star_main_stat_value(slot_key: str, stat_key: str) -> float:
    slot = str(slot_key or "").strip().casefold()
    stat = str(stat_key or "").strip().casefold()
    if stat not in LEGAL_FIVE_STAR_MAIN_STATS_BY_SLOT.get(slot, ()):
        raise ValueError(f"illegal five-star main stat: {slot}/{stat}")
    return float(FIVE_STAR_MAIN_STAT_VALUES[stat])


def five_star_substat_coordinate_cap(
    stat_key: str,
    main_stat_keys: tuple[str, ...],
) -> float:
    """Optimistic max-roll-unit cap after same-main-stat exclusions."""

    stat = str(stat_key or "").strip().casefold()
    if stat not in FIVE_STAR_SUBSTAT_ROLL_RULES:
        raise ValueError(f"unsupported five-star substat: {stat}")
    normalized = tuple(str(value or "").strip().casefold() for value in main_stat_keys)
    if len(normalized) != FIVE_STAR_ARTIFACTS_PER_BUILD:
        raise ValueError("one main stat is required for each of five artifact slots")
    eligible_pieces = sum(value != stat for value in normalized)
    return float(
        eligible_pieces * FIVE_STAR_MAX_ROLLS_PER_STAT_PER_ELIGIBLE_PIECE
    )


def _rules_payload() -> dict[str, object]:
    return {
        "kind": ARTIFACT_INVESTMENT_RULES_KIND,
        "schema_version": ARTIFACT_INVESTMENT_RULES_SCHEMA_VERSION,
        "roll_value_qualities": list(ROLL_VALUE_QUALITIES),
        "max_roll_units_per_wearer": FIVE_STAR_MAX_ROLL_UNITS_PER_WEARER,
        "substats": {
            key: list(rule.values)
            for key, rule in sorted(FIVE_STAR_SUBSTAT_ROLL_RULES.items())
        },
        "main_stats": {
            slot: list(stats)
            for slot, stats in LEGAL_FIVE_STAR_MAIN_STATS_BY_SLOT.items()
        },
        "main_stat_values": dict(sorted(FIVE_STAR_MAIN_STAT_VALUES.items())),
    }


ARTIFACT_INVESTMENT_RULES_SHA256 = hashlib.sha256(
    json.dumps(
        _rules_payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
).hexdigest()


__all__ = [
    "ARTIFACT_INVESTMENT_RULES_KIND",
    "ARTIFACT_INVESTMENT_RULES_SCHEMA_VERSION",
    "ARTIFACT_INVESTMENT_RULES_SHA256",
    "ARTIFACT_MAIN_STAT_SLOTS",
    "FIVE_STAR_ARTIFACTS_PER_BUILD",
    "FIVE_STAR_MAIN_STAT_VALUES",
    "FIVE_STAR_MAX_ROLLS_PER_ARTIFACT",
    "FIVE_STAR_MAX_ROLLS_PER_STAT_PER_ELIGIBLE_PIECE",
    "FIVE_STAR_MAX_ROLL_UNITS_PER_WEARER",
    "FIVE_STAR_SUBSTAT_ROLL_RULES",
    "FOUR_STAR_MAIN_STAT_VALUES",
    "FiveStarSubstatRollRule",
    "LEGAL_FIVE_STAR_CIRCLET_MAIN_STATS",
    "LEGAL_FIVE_STAR_GOBLET_MAIN_STATS",
    "LEGAL_FIVE_STAR_MAIN_STATS_BY_SLOT",
    "LEGAL_FIVE_STAR_SANDS_MAIN_STATS",
    "ROLL_VALUE_QUALITIES",
    "five_star_main_stat_value",
    "five_star_substat_coordinate_cap",
]
