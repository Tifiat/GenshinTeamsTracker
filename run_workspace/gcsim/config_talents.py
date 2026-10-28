"""Prepare account-observed talent levels for the GCSIM parser.

HoYoLAB account detail payloads expose displayed talent levels, including
active C3/C5 bonuses. GCSIM config syntax currently accepts only parser-safe
base levels in the 1..10 range. This helper removes only the narrow, account
observable C3/C5 +3 bonus when the active constellation effect names exactly
one active talent inside HoYoLAB color markup. It is not a constellation buff
engine and does not parse arbitrary effect text.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
import html
import re
import unicodedata
from typing import Any


GCSIM_MIN_TALENT_LEVEL = 1
GCSIM_MAX_TALENT_LEVEL = 10

TALENT_SLOT_NORMAL = "normal"
TALENT_SLOT_SKILL = "skill"
TALENT_SLOT_BURST = "burst"
TALENT_SLOTS: tuple[str, str, str] = (
    TALENT_SLOT_NORMAL,
    TALENT_SLOT_SKILL,
    TALENT_SLOT_BURST,
)

TALENT_METHOD_DISPLAYED_LEVEL = "displayed_level"
TALENT_METHOD_CONSTELLATION_BONUS_REMOVED = "constellation_bonus_removed"
TALENT_METHOD_CAPPED_AFTER_NORMALIZATION = "post_normalization_cap"
TALENT_METHOD_INVALID_LEVEL = "invalid_level"

WARNING_CONSTELLATION_TALENT_BONUS_NOT_RESOLVED = (
    "constellation_talent_bonus_not_resolved"
)
WARNING_POST_NORMALIZATION_TALENT_LEVEL_CAPPED_TO_GCSIM_RANGE = (
    "post_normalization_talent_level_capped_to_gcsim_range"
)
WARNING_TALENT_LEVEL_INVALID_FOR_GCSIM = "talent_level_invalid_for_gcsim"

_COLOR_RE = re.compile(r"<color=[^>]*>(.*?)</color>", re.IGNORECASE | re.DOTALL)
_LINK_MARKUP_RE = re.compile(r"\{/?LINK[^}]*\}", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class GcsimTalentSource:
    slot: str
    skill_id: str
    name: str
    displayed_level: int | None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], *, slot: str = "") -> "GcsimTalentSource":
        return cls(
            slot=_text(value.get("slot")) or slot,
            skill_id=_text(value.get("skill_id")),
            name=_text(value.get("name")),
            displayed_level=_optional_int(value.get("displayed_level", value.get("level"))),
        )


@dataclass(frozen=True, slots=True)
class GcsimConstellationSource:
    pos: int | None
    is_actived: bool
    effect: str = ""
    name: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GcsimConstellationSource":
        return cls(
            pos=_optional_int(value.get("pos")),
            is_actived=_bool_value(value.get("is_actived")),
            effect=_text(value.get("effect")),
            name=_text(value.get("name")),
        )


@dataclass(frozen=True, slots=True)
class GcsimPreparedTalent:
    slot: str
    skill_id: str
    name: str
    displayed_level: int | None
    parsed_constellation_bonus: int = 0
    gcsim_level: int | None = None
    method: str = TALENT_METHOD_DISPLAYED_LEVEL
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "skill_id": self.skill_id,
            "name": self.name,
            "displayed_level": self.displayed_level,
            "parsed_constellation_bonus": self.parsed_constellation_bonus,
            "gcsim_level": self.gcsim_level,
            "method": self.method,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class GcsimTalentPreparationResult:
    ready: bool
    talents: tuple[GcsimPreparedTalent, ...]
    warnings: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()
    matched_constellation_bonus_by_skill_id: Mapping[str, int] = field(default_factory=dict)

    @property
    def normal(self) -> int | None:
        return self._level_for_slot(TALENT_SLOT_NORMAL)

    @property
    def skill(self) -> int | None:
        return self._level_for_slot(TALENT_SLOT_SKILL)

    @property
    def burst(self) -> int | None:
        return self._level_for_slot(TALENT_SLOT_BURST)

    def _level_for_slot(self, slot: str) -> int | None:
        for talent in self.talents:
            if talent.slot == slot:
                return talent.gcsim_level
        return None

    def to_talent_input_dict(self) -> dict[str, Any] | None:
        if not self.ready:
            return None
        return {
            "normal": self.normal,
            "skill": self.skill,
            "burst": self.burst,
            "source_order_confirmed": True,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "talents": [talent.to_dict() for talent in self.talents],
            "warnings": list(self.warnings),
            "issues": list(self.issues),
            "matched_constellation_bonus_by_skill_id": dict(
                self.matched_constellation_bonus_by_skill_id
            ),
        }


def prepare_gcsim_talent_levels(
    talents: Iterable[GcsimTalentSource | Mapping[str, Any]],
    constellations: Iterable[GcsimConstellationSource | Mapping[str, Any]] = (),
) -> GcsimTalentPreparationResult:
    """Return parser-safe GCSIM talent levels plus a transparent audit."""

    source_talents = _coerce_talents(talents)
    source_constellations = _coerce_constellations(constellations)
    bonus_by_skill_id, unresolved_warnings = _constellation_bonuses_by_skill_id(
        source_talents,
        source_constellations,
    )
    prepared: list[GcsimPreparedTalent] = []
    all_warnings: list[str] = list(unresolved_warnings)
    issues: list[str] = []
    for talent in source_talents:
        talent_warnings: list[str] = []
        displayed_level = talent.displayed_level
        bonus = int(bonus_by_skill_id.get(talent.skill_id, 0))
        if displayed_level is None or displayed_level < GCSIM_MIN_TALENT_LEVEL:
            talent_warnings.append(WARNING_TALENT_LEVEL_INVALID_FOR_GCSIM)
            issues.append(WARNING_TALENT_LEVEL_INVALID_FOR_GCSIM)
            prepared.append(
                GcsimPreparedTalent(
                    slot=talent.slot,
                    skill_id=talent.skill_id,
                    name=talent.name,
                    displayed_level=displayed_level,
                    parsed_constellation_bonus=bonus,
                    gcsim_level=None,
                    method=TALENT_METHOD_INVALID_LEVEL,
                    warnings=tuple(talent_warnings),
                )
            )
            continue

        level = int(displayed_level) - bonus
        method = (
            TALENT_METHOD_CONSTELLATION_BONUS_REMOVED
            if bonus
            else TALENT_METHOD_DISPLAYED_LEVEL
        )
        if level < GCSIM_MIN_TALENT_LEVEL:
            talent_warnings.append(WARNING_TALENT_LEVEL_INVALID_FOR_GCSIM)
            issues.append(WARNING_TALENT_LEVEL_INVALID_FOR_GCSIM)
            gcsim_level = None
            method = TALENT_METHOD_INVALID_LEVEL
        else:
            gcsim_level = level
            if gcsim_level > GCSIM_MAX_TALENT_LEVEL:
                gcsim_level = GCSIM_MAX_TALENT_LEVEL
                method = TALENT_METHOD_CAPPED_AFTER_NORMALIZATION
                talent_warnings.append(
                    WARNING_POST_NORMALIZATION_TALENT_LEVEL_CAPPED_TO_GCSIM_RANGE
                )
        all_warnings.extend(talent_warnings)
        prepared.append(
            GcsimPreparedTalent(
                slot=talent.slot,
                skill_id=talent.skill_id,
                name=talent.name,
                displayed_level=displayed_level,
                parsed_constellation_bonus=bonus,
                gcsim_level=gcsim_level,
                method=method,
                warnings=tuple(_dedupe(talent_warnings)),
            )
        )

    ready = (
        len(prepared) == len(TALENT_SLOTS)
        and not issues
        and all(
            item.gcsim_level is not None
            and GCSIM_MIN_TALENT_LEVEL <= item.gcsim_level <= GCSIM_MAX_TALENT_LEVEL
            for item in prepared
        )
    )
    return GcsimTalentPreparationResult(
        ready=ready,
        talents=tuple(prepared),
        warnings=tuple(_dedupe(all_warnings)),
        issues=tuple(_dedupe(issues)),
        matched_constellation_bonus_by_skill_id=dict(bonus_by_skill_id),
    )


def normalized_talent_text(value: Any) -> str:
    text = html.unescape(_text(value))
    text = _LINK_MARKUP_RE.sub("", text)
    text = unicodedata.normalize("NFKC", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text.casefold()


def extract_colored_texts(effect: str) -> tuple[str, ...]:
    return tuple(
        _text(html.unescape(match.group(1)))
        for match in _COLOR_RE.finditer(_text(effect))
        if _text(match.group(1))
    )


def _constellation_bonuses_by_skill_id(
    talents: tuple[GcsimTalentSource, ...],
    constellations: tuple[GcsimConstellationSource, ...],
) -> tuple[dict[str, int], tuple[str, ...]]:
    talent_by_normalized_name: dict[str, list[GcsimTalentSource]] = {}
    for talent in talents:
        normalized = normalized_talent_text(talent.name)
        if normalized:
            talent_by_normalized_name.setdefault(normalized, []).append(talent)

    bonus_by_skill_id: dict[str, int] = {}
    warnings: list[str] = []
    for constellation in constellations:
        if constellation.pos not in (3, 5) or not constellation.is_actived:
            continue
        colored_texts = extract_colored_texts(constellation.effect)
        matched_skill_ids: set[str] = set()
        for colored_text in colored_texts:
            matches = talent_by_normalized_name.get(normalized_talent_text(colored_text), [])
            if len(matches) == 1 and matches[0].skill_id:
                matched_skill_ids.add(matches[0].skill_id)
        if len(matched_skill_ids) == 1:
            skill_id = next(iter(matched_skill_ids))
            bonus_by_skill_id[skill_id] = bonus_by_skill_id.get(skill_id, 0) + 3
        else:
            warnings.append(WARNING_CONSTELLATION_TALENT_BONUS_NOT_RESOLVED)
    return bonus_by_skill_id, tuple(_dedupe(warnings))


def _coerce_talents(
    talents: Iterable[GcsimTalentSource | Mapping[str, Any]],
) -> tuple[GcsimTalentSource, ...]:
    result: list[GcsimTalentSource] = []
    for index, item in enumerate(talents):
        slot = TALENT_SLOTS[index] if index < len(TALENT_SLOTS) else ""
        if isinstance(item, GcsimTalentSource):
            result.append(
                item if item.slot else GcsimTalentSource(
                    slot=slot,
                    skill_id=item.skill_id,
                    name=item.name,
                    displayed_level=item.displayed_level,
                )
            )
        elif isinstance(item, Mapping):
            result.append(GcsimTalentSource.from_mapping(item, slot=slot))
    return tuple(result[: len(TALENT_SLOTS)])


def _coerce_constellations(
    constellations: Iterable[GcsimConstellationSource | Mapping[str, Any]],
) -> tuple[GcsimConstellationSource, ...]:
    result: list[GcsimConstellationSource] = []
    for item in constellations:
        if isinstance(item, GcsimConstellationSource):
            result.append(item)
        elif isinstance(item, Mapping):
            result.append(GcsimConstellationSource.from_mapping(item))
    return tuple(result)


def _optional_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = _text(value).casefold()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return bool(value)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return result
