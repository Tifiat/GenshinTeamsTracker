from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


ARTIFACT_BUILD_SNAPSHOT_SCHEMA_VERSION = 1

ARTIFACT_POSITIONS = (1, 2, 3, 4, 5)

WARNING_ARTIFACT_SUMMARY_MISSING = "artifact_summary_missing"
WARNING_ARTIFACT_SLOTS_MISSING = "artifact_slots_missing"
WARNING_ARTIFACT_BUILD_INCOMPLETE = "artifact_build_incomplete"
WARNING_ARTIFACT_STAT_TOTALS_PARTIAL = "artifact_stat_totals_partial"
WARNING_CONDITIONAL_SET_BONUSES_NOT_INCLUDED = (
    "conditional_set_bonuses_not_included"
)
WARNING_SET_BONUS_FORMULAS_NOT_INCLUDED = "set_bonus_formulas_not_included"


@dataclass(frozen=True, slots=True)
class ArtifactBuildSlotSnapshot:
    pos: int
    artifact_id: int | None = None
    name: str = ""
    set_uid: str = ""
    set_name: str = ""
    rarity: int | None = None
    level: int | None = None
    main_property_type: int | None = None
    main_property_name: str = ""
    main_property_value: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pos": self.pos,
            "artifact_id": self.artifact_id,
            "name": self.name,
            "set_uid": self.set_uid,
            "set_name": self.set_name,
            "rarity": self.rarity,
            "level": self.level,
            "main_property_type": self.main_property_type,
            "main_property_name": self.main_property_name,
            "main_property_value": self.main_property_value,
        }


@dataclass(frozen=True, slots=True)
class ArtifactStatTotalSnapshot:
    property_type: int | None = None
    property_name: str = ""
    raw_value: float | None = None
    stat_key: str = ""
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "property_type": self.property_type,
            "property_name": self.property_name,
            "raw_value": self.raw_value,
            "stat_key": self.stat_key,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class ArtifactSetCountSnapshot:
    set_uid: str = ""
    set_name: str = ""
    count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "set_uid": self.set_uid,
            "set_name": self.set_name,
            "count": self.count,
        }


@dataclass(frozen=True, slots=True)
class ArtifactActiveSetBonusSnapshot:
    set_uid: str = ""
    set_name: str = ""
    piece_count: int = 0
    owned_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "set_uid": self.set_uid,
            "set_name": self.set_name,
            "piece_count": self.piece_count,
            "owned_count": self.owned_count,
        }


@dataclass(frozen=True, slots=True)
class ArtifactBuildSnapshot:
    schema_version: int = ARTIFACT_BUILD_SNAPSHOT_SCHEMA_VERSION
    build_id: int | None = None
    build_name: str = ""
    artifact_ids_by_pos: dict[int, int] = field(default_factory=dict)
    slots: tuple[ArtifactBuildSlotSnapshot, ...] = ()
    missing_positions: tuple[int, ...] = ARTIFACT_POSITIONS
    set_counts: tuple[ArtifactSetCountSnapshot, ...] = ()
    active_set_bonuses: tuple[ArtifactActiveSetBonusSnapshot, ...] = ()
    stat_totals: tuple[ArtifactStatTotalSnapshot, ...] = ()
    crit_value: float | None = None
    proc_count: int | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "build_id": self.build_id,
            "build_name": self.build_name,
            "artifact_ids_by_pos": {
                str(pos): artifact_id
                for pos, artifact_id in sorted(self.artifact_ids_by_pos.items())
            },
            "slots": [slot.to_dict() for slot in self.slots],
            "missing_positions": list(self.missing_positions),
            "set_counts": [item.to_dict() for item in self.set_counts],
            "active_set_bonuses": [
                item.to_dict()
                for item in self.active_set_bonuses
            ],
            "stat_totals": [item.to_dict() for item in self.stat_totals],
            "crit_value": self.crit_value,
            "proc_count": self.proc_count,
            "warnings": list(self.warnings),
        }


def build_artifact_build_snapshot(
    summary: Mapping[str, Any] | None = None,
    *,
    build_preset: Mapping[str, Any] | None = None,
) -> ArtifactBuildSnapshot:
    if summary is None and build_preset is None:
        return ArtifactBuildSnapshot(
            missing_positions=ARTIFACT_POSITIONS,
            warnings=(WARNING_ARTIFACT_SUMMARY_MISSING,),
        )

    summary = dict(summary or {})
    build_preset = dict(build_preset or {})
    build_id = _optional_int(_first_present(build_preset, summary, "id", "build_id"))
    build_name = _text(_first_present(build_preset, summary, "name", "build_name"))
    slots = _slots_from_build_preset(build_preset)
    artifact_ids_by_pos = _artifact_ids_by_pos(summary, slots)
    missing_positions = _missing_positions(summary, artifact_ids_by_pos)
    set_counts = _set_counts(summary)
    active_set_bonuses = _active_set_bonuses(summary, set_counts)
    stat_totals = _stat_totals(summary)
    warnings: list[str] = []

    if not artifact_ids_by_pos and not slots:
        warnings.append(WARNING_ARTIFACT_SLOTS_MISSING)
    if missing_positions:
        warnings.append(WARNING_ARTIFACT_BUILD_INCOMPLETE)
    if not stat_totals and artifact_ids_by_pos:
        warnings.append(WARNING_ARTIFACT_STAT_TOTALS_PARTIAL)
    if active_set_bonuses:
        warnings.append(WARNING_SET_BONUS_FORMULAS_NOT_INCLUDED)
        warnings.append(WARNING_CONDITIONAL_SET_BONUSES_NOT_INCLUDED)

    return ArtifactBuildSnapshot(
        build_id=build_id,
        build_name=build_name,
        artifact_ids_by_pos=artifact_ids_by_pos,
        slots=tuple(slots),
        missing_positions=tuple(missing_positions),
        set_counts=tuple(set_counts),
        active_set_bonuses=tuple(active_set_bonuses),
        stat_totals=tuple(stat_totals),
        crit_value=_optional_float(summary.get("crit_value")),
        proc_count=_optional_int(summary.get("proc_count")),
        warnings=tuple(_dedupe(warnings)),
    )


def _slots_from_build_preset(
    build_preset: Mapping[str, Any],
) -> list[ArtifactBuildSlotSnapshot]:
    slots = build_preset.get("slots")
    if not isinstance(slots, list):
        return []

    result: list[ArtifactBuildSlotSnapshot] = []
    for slot in slots:
        if not isinstance(slot, Mapping):
            continue
        pos = _optional_int(slot.get("pos"))
        if pos not in ARTIFACT_POSITIONS:
            continue
        result.append(
            ArtifactBuildSlotSnapshot(
                pos=int(pos),
                artifact_id=_optional_int(slot.get("artifact_id")),
                name=_text(slot.get("name")),
                set_uid=_text(slot.get("set_uid")),
                set_name=_text(slot.get("set_name")),
                rarity=_optional_int(slot.get("rarity")),
                level=_optional_int(slot.get("level")),
                main_property_type=_optional_int(slot.get("main_property_type")),
                main_property_name=_text(slot.get("main_property_name")),
                main_property_value=_text(slot.get("main_property_value")),
            )
        )
    return sorted(result, key=lambda item: item.pos)


def _artifact_ids_by_pos(
    summary: Mapping[str, Any],
    slots: list[ArtifactBuildSlotSnapshot],
) -> dict[int, int]:
    result: dict[int, int] = {}
    raw = summary.get("artifact_ids_by_pos")
    if isinstance(raw, Mapping):
        for pos, artifact_id in raw.items():
            pos_int = _optional_int(pos)
            artifact_id_int = _optional_int(artifact_id)
            if pos_int in ARTIFACT_POSITIONS and artifact_id_int is not None:
                result[int(pos_int)] = int(artifact_id_int)

    for slot in slots:
        if slot.artifact_id is not None:
            result.setdefault(slot.pos, slot.artifact_id)
    return dict(sorted(result.items()))


def _missing_positions(
    summary: Mapping[str, Any],
    artifact_ids_by_pos: Mapping[int, int],
) -> list[int]:
    raw = summary.get("missing_positions")
    if isinstance(raw, list):
        result = [
            int(pos)
            for pos in (_optional_int(item) for item in raw)
            if pos in ARTIFACT_POSITIONS
        ]
        return sorted(set(result))
    return [
        pos
        for pos in ARTIFACT_POSITIONS
        if pos not in artifact_ids_by_pos
    ]


def _set_counts(summary: Mapping[str, Any]) -> list[ArtifactSetCountSnapshot]:
    result: list[ArtifactSetCountSnapshot] = []
    for item in summary.get("set_counts") or []:
        if not isinstance(item, Mapping):
            continue
        result.append(
            ArtifactSetCountSnapshot(
                set_uid=_text(item.get("set_uid")),
                set_name=_text(item.get("set_name")),
                count=_optional_int(item.get("count")) or 0,
            )
        )
    return result


def _active_set_bonuses(
    summary: Mapping[str, Any],
    set_counts: list[ArtifactSetCountSnapshot],
) -> list[ArtifactActiveSetBonusSnapshot]:
    result: list[ArtifactActiveSetBonusSnapshot] = []
    raw = summary.get("active_set_bonuses") or summary.get("set_bonuses")
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            piece_count = _optional_int(
                _first_present(item, item, "piece_count", "count")
            ) or 0
            owned_count = _optional_int(item.get("owned_count")) or piece_count
            if piece_count <= 0:
                continue
            result.append(
                ArtifactActiveSetBonusSnapshot(
                    set_uid=_text(item.get("set_uid")),
                    set_name=_text(item.get("set_name")),
                    piece_count=piece_count,
                    owned_count=owned_count,
                )
            )
        if result:
            return result

    for item in set_counts:
        if item.count >= 4:
            result.append(
                ArtifactActiveSetBonusSnapshot(
                    set_uid=item.set_uid,
                    set_name=item.set_name,
                    piece_count=4,
                    owned_count=item.count,
                )
            )
        elif item.count >= 2:
            result.append(
                ArtifactActiveSetBonusSnapshot(
                    set_uid=item.set_uid,
                    set_name=item.set_name,
                    piece_count=2,
                    owned_count=item.count,
                )
            )
    return result


def _stat_totals(summary: Mapping[str, Any]) -> list[ArtifactStatTotalSnapshot]:
    result: list[ArtifactStatTotalSnapshot] = []
    for item in summary.get("total_stats") or []:
        if not isinstance(item, Mapping):
            continue
        result.append(
            ArtifactStatTotalSnapshot(
                property_type=_optional_int(item.get("property_type")),
                property_name=_text(item.get("property_name")),
                raw_value=_optional_float(item.get("raw_value")),
            )
        )

    stat_totals = summary.get("stat_totals")
    if isinstance(stat_totals, Mapping):
        for key, value in sorted(stat_totals.items()):
            result.append(
                ArtifactStatTotalSnapshot(
                    stat_key=_text(key),
                    value=value,
                    raw_value=_optional_float(value),
                )
            )
    return result


def _first_present(
    primary: Mapping[str, Any],
    secondary: Mapping[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        value = primary.get(key)
        if value is not None and value != "":
            return value
        value = secondary.get(key)
        if value is not None and value != "":
            return value
    return None


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: list[str] | tuple[str, ...]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
