from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hoyolab_export.character_trait_catalog import TRAIT_STANDARD_5_STAR


CHARACTER_SORT_MODE_COUNTS = {
    "constellation": 2,
    "level": 3,
}


@dataclass(frozen=True, slots=True)
class CharacterSortState:
    criterion: str | None = None
    mode: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.mode, bool) or not isinstance(self.mode, int):
            raise ValueError("sorting mode must be an integer")
        if self.criterion is None:
            if self.mode != 0:
                raise ValueError("sorting mode must be 0 when sorting is off")
            return
        if not isinstance(self.criterion, str):
            raise ValueError("sorting criterion must be a string or None")
        if self.criterion not in CHARACTER_SORT_MODE_COUNTS:
            raise ValueError(f"unknown character sort criterion: {self.criterion!r}")
        if not 1 <= self.mode <= CHARACTER_SORT_MODE_COUNTS[self.criterion]:
            raise ValueError(
                f"sorting mode for {self.criterion!r} must be between 1 and "
                f"{CHARACTER_SORT_MODE_COUNTS[self.criterion]}"
            )

    @property
    def active(self) -> bool:
        return self.criterion is not None

    def next(self, criterion: str) -> CharacterSortState:
        if not isinstance(criterion, str) or criterion not in CHARACTER_SORT_MODE_COUNTS:
            raise ValueError(f"unknown character sort criterion: {criterion!r}")
        if self.criterion != criterion:
            return CharacterSortState(criterion, 1)
        if self.mode == CHARACTER_SORT_MODE_COUNTS[criterion]:
            return DEFAULT_CHARACTER_SORT
        return CharacterSortState(criterion, self.mode + 1)


DEFAULT_CHARACTER_SORT = CharacterSortState()


def _character_metadata(asset: dict[str, Any]) -> dict[str, Any]:
    metadata = asset.get("metadata") or {}
    return metadata.get("character") or {}


def _metadata_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _canonical_name(asset: dict[str, Any], character: dict[str, Any]) -> str:
    return str(
        character.get("canonical_name")
        or character.get("name")
        or asset.get("filename")
        or ""
    ).casefold()


def _filename(asset: dict[str, Any]) -> str:
    return str(asset.get("filename") or "")


def _character_id_key(character: dict[str, Any]) -> tuple[int, int | str]:
    value = character.get("id")
    try:
        if isinstance(value, bool):
            raise ValueError
        return (0, int(value))
    except (TypeError, ValueError, OverflowError):
        return (1, str(value or ""))


def _numeric_metric(value: Any, *, minimum: int, maximum: int | None = None) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return None
    else:
        return None
    if parsed < minimum or (maximum is not None and parsed > maximum):
        return None
    return parsed


def is_standard_character(asset: dict[str, Any]) -> bool:
    metadata = asset.get("metadata") or {}
    character = metadata.get("character") or {}
    traits = set(character.get("traits") or metadata.get("traits") or [])
    return bool(
        character.get("is_standard_5_star")
        or metadata.get("is_standard_5_star")
        or TRAIT_STANDARD_5_STAR in traits
    )


def _rarity_group(rarity: int, mode: int, asset: dict[str, Any]) -> int:
    if mode == 2:
        if rarity == 5:
            return 1 if is_standard_character(asset) else 0
        if rarity == 4:
            return 2
        return 3
    if rarity == 5:
        return 0
    if rarity == 4:
        return 1
    return 2


def character_sort_key(
    asset: dict[str, Any],
    state: CharacterSortState = DEFAULT_CHARACTER_SORT,
) -> tuple[Any, ...]:
    character = _character_metadata(asset)
    rarity = _metadata_int(character.get("rarity"))
    level = _metadata_int(character.get("level"))
    name = _canonical_name(asset, character)
    filename = _filename(asset)

    if not state.active:
        return (-rarity, -level, name, filename)

    character_id_key = _character_id_key(character)
    if state.criterion == "constellation":
        metric = _numeric_metric(
            character.get("constellation"), minimum=0, maximum=6,
        )
        grouped = True
    else:
        metric = _numeric_metric(character.get("level"), minimum=1)
        grouped = state.mode in (1, 2)

    metric_key = (metric is None, -(metric or 0))
    if grouped:
        group = _rarity_group(rarity, state.mode, asset)
        return (group, *metric_key, name, filename, character_id_key)
    return (*metric_key, name, filename, character_id_key)
