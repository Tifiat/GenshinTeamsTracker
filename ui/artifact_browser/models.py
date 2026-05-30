from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ARTIFACT_POSITIONS = {
    1: "Flower",
    2: "Plume",
    3: "Sands",
    4: "Goblet",
    5: "Circlet",
}


@dataclass(frozen=True, slots=True)
class ArtifactTagRef:
    id: int
    name: str


@dataclass(slots=True)
class ArtifactSubstat:
    slot_index: int
    property_type: int
    property_name: str
    value: str
    times: int | None = None


@dataclass(slots=True)
class ArtifactItem:
    id: int
    name: str
    set_id: int | None
    set_uid: str
    set_name: str
    pos: int
    pos_name: str
    rarity: int
    level: int
    main_property_type: int
    main_property_name: str
    main_property_value: str
    icon_key: str = ""
    icon_url: str = ""
    icon_path: Path | None = None
    set_icon_path: Path | None = None
    character_name: str = ""
    owner_character_id: int | None = None
    owner_icon_path: Path | None = None
    tags: list[ArtifactTagRef] = field(default_factory=list)
    substats: list[ArtifactSubstat] = field(default_factory=list)

    @property
    def is_equipped(self) -> bool:
        return bool(self.character_name)

    @property
    def cv(self) -> float:
        from .stat_types import CRIT_DAMAGE, CRIT_RATE

        total = 0.0

        for substat in self.substats:
            if substat.property_type == CRIT_RATE:
                total += parse_hoyolab_stat_value(substat.value) * 2
            elif substat.property_type == CRIT_DAMAGE:
                total += parse_hoyolab_stat_value(substat.value)

        return round(total, 1)

    @property
    def proc_count(self) -> int:
        return sum(int(substat.times or 0) for substat in self.substats)


def parse_hoyolab_stat_value(value: Any) -> float:
    text = str(value).strip().replace("%", "").replace(",", ".")
    return float(text)


def int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
