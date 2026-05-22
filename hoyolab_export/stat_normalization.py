from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .artifact_build_snapshot import ArtifactBuildSnapshot, ArtifactStatTotalSnapshot
from .artifact_stats import (
    ANEMO_DAMAGE,
    ATK_FLAT,
    ATK_PERCENT,
    CRIT_DAMAGE,
    CRIT_RATE,
    CRYO_DAMAGE,
    DEF_FLAT,
    DEF_PERCENT,
    DENDRO_DAMAGE,
    ELECTRO_DAMAGE,
    ELEMENTAL_MASTERY,
    ENERGY_RECHARGE,
    GEO_DAMAGE,
    HEALING_BONUS,
    HP_FLAT,
    HP_PERCENT,
    HYDRO_DAMAGE,
    PHYSICAL_DAMAGE,
    PYRO_DAMAGE,
)


NORMALIZED_STAT_SCHEMA_VERSION = 1

STAT_UNIT_FLAT = "flat"
STAT_UNIT_RATIO = "ratio"
STAT_UNIT_UNKNOWN = "unknown"
STAT_UNIT_VIRTUAL = "virtual"

SOURCE_UNIT_FLAT = "flat"
SOURCE_UNIT_PERCENT_POINTS = "percent_points"
SOURCE_UNIT_UNKNOWN = "unknown"

WARNING_STAT_PROPERTY_TYPE_UNKNOWN = "stat_property_type_unknown"
WARNING_STAT_VALUE_MISSING = "stat_value_missing"
WARNING_STAT_VALUE_INVALID = "stat_value_invalid"
WARNING_GCSIM_KEY_MISSING = "gcsim_key_missing"


@dataclass(frozen=True, slots=True)
class StatMapping:
    property_type: int
    normalized_key: str
    gcsim_key: str
    unit: str
    source_unit: str


STAT_MAPPINGS_BY_PROPERTY_TYPE: dict[int, StatMapping] = {
    HP_FLAT: StatMapping(HP_FLAT, "hp_flat", "hp", STAT_UNIT_FLAT, SOURCE_UNIT_FLAT),
    HP_PERCENT: StatMapping(
        HP_PERCENT,
        "hp_percent",
        "hp%",
        STAT_UNIT_RATIO,
        SOURCE_UNIT_PERCENT_POINTS,
    ),
    ATK_FLAT: StatMapping(ATK_FLAT, "atk_flat", "atk", STAT_UNIT_FLAT, SOURCE_UNIT_FLAT),
    ATK_PERCENT: StatMapping(
        ATK_PERCENT,
        "atk_percent",
        "atk%",
        STAT_UNIT_RATIO,
        SOURCE_UNIT_PERCENT_POINTS,
    ),
    DEF_FLAT: StatMapping(DEF_FLAT, "def_flat", "def", STAT_UNIT_FLAT, SOURCE_UNIT_FLAT),
    DEF_PERCENT: StatMapping(
        DEF_PERCENT,
        "def_percent",
        "def%",
        STAT_UNIT_RATIO,
        SOURCE_UNIT_PERCENT_POINTS,
    ),
    CRIT_RATE: StatMapping(
        CRIT_RATE,
        "crit_rate",
        "cr",
        STAT_UNIT_RATIO,
        SOURCE_UNIT_PERCENT_POINTS,
    ),
    CRIT_DAMAGE: StatMapping(
        CRIT_DAMAGE,
        "crit_damage",
        "cd",
        STAT_UNIT_RATIO,
        SOURCE_UNIT_PERCENT_POINTS,
    ),
    ENERGY_RECHARGE: StatMapping(
        ENERGY_RECHARGE,
        "energy_recharge",
        "er",
        STAT_UNIT_RATIO,
        SOURCE_UNIT_PERCENT_POINTS,
    ),
    HEALING_BONUS: StatMapping(
        HEALING_BONUS,
        "healing_bonus",
        "heal",
        STAT_UNIT_RATIO,
        SOURCE_UNIT_PERCENT_POINTS,
    ),
    ELEMENTAL_MASTERY: StatMapping(
        ELEMENTAL_MASTERY,
        "elemental_mastery",
        "em",
        STAT_UNIT_FLAT,
        SOURCE_UNIT_FLAT,
    ),
    PHYSICAL_DAMAGE: StatMapping(
        PHYSICAL_DAMAGE,
        "physical_dmg_bonus",
        "phys%",
        STAT_UNIT_RATIO,
        SOURCE_UNIT_PERCENT_POINTS,
    ),
    PYRO_DAMAGE: StatMapping(
        PYRO_DAMAGE,
        "pyro_dmg_bonus",
        "pyro%",
        STAT_UNIT_RATIO,
        SOURCE_UNIT_PERCENT_POINTS,
    ),
    ELECTRO_DAMAGE: StatMapping(
        ELECTRO_DAMAGE,
        "electro_dmg_bonus",
        "electro%",
        STAT_UNIT_RATIO,
        SOURCE_UNIT_PERCENT_POINTS,
    ),
    HYDRO_DAMAGE: StatMapping(
        HYDRO_DAMAGE,
        "hydro_dmg_bonus",
        "hydro%",
        STAT_UNIT_RATIO,
        SOURCE_UNIT_PERCENT_POINTS,
    ),
    DENDRO_DAMAGE: StatMapping(
        DENDRO_DAMAGE,
        "dendro_dmg_bonus",
        "dendro%",
        STAT_UNIT_RATIO,
        SOURCE_UNIT_PERCENT_POINTS,
    ),
    ANEMO_DAMAGE: StatMapping(
        ANEMO_DAMAGE,
        "anemo_dmg_bonus",
        "anemo%",
        STAT_UNIT_RATIO,
        SOURCE_UNIT_PERCENT_POINTS,
    ),
    GEO_DAMAGE: StatMapping(
        GEO_DAMAGE,
        "geo_dmg_bonus",
        "geo%",
        STAT_UNIT_RATIO,
        SOURCE_UNIT_PERCENT_POINTS,
    ),
    CRYO_DAMAGE: StatMapping(
        CRYO_DAMAGE,
        "cryo_dmg_bonus",
        "cryo%",
        STAT_UNIT_RATIO,
        SOURCE_UNIT_PERCENT_POINTS,
    ),
}

STAT_MAPPINGS_BY_NORMALIZED_KEY = {
    mapping.normalized_key: mapping
    for mapping in STAT_MAPPINGS_BY_PROPERTY_TYPE.values()
}


@dataclass(frozen=True, slots=True)
class NormalizedStatValue:
    key: str
    value: float | None
    unit: str
    source_value: Any = None
    source_numeric: float | None = None
    source_unit: str = SOURCE_UNIT_UNKNOWN
    property_type: int | None = None
    property_name: str = ""
    gcsim_key: str = ""
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "unit": self.unit,
            "source_value": self.source_value,
            "source_numeric": self.source_numeric,
            "source_unit": self.source_unit,
            "property_type": self.property_type,
            "property_name": self.property_name,
            "gcsim_key": self.gcsim_key,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class NormalizedStatBlock:
    schema_version: int = NORMALIZED_STAT_SCHEMA_VERSION
    source: str = ""
    values: tuple[NormalizedStatValue, ...] = ()
    warnings: tuple[str, ...] = ()
    source_notes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "values": [value.to_dict() for value in self.values],
            "warnings": list(self.warnings),
            "source_notes": dict(self.source_notes),
        }


def normalize_artifact_stat_total(
    stat_total: ArtifactStatTotalSnapshot | Mapping[str, Any],
) -> NormalizedStatValue:
    record = _stat_total_record(stat_total)
    property_type = _optional_int(record.get("property_type"))
    property_name = _text(record.get("property_name"))
    raw_value = _first_present(record, "raw_value", "value")
    source_numeric, value_warning = _optional_float_with_warning(raw_value)
    warnings: list[str] = []
    if value_warning:
        warnings.append(value_warning)

    mapping: StatMapping | None = None
    if property_type is not None:
        mapping = STAT_MAPPINGS_BY_PROPERTY_TYPE.get(property_type)
    if mapping is None:
        stat_key = _text(record.get("stat_key"))
        mapping = STAT_MAPPINGS_BY_NORMALIZED_KEY.get(stat_key)

    if mapping is None:
        if property_type is not None or _text(record.get("stat_key")):
            warnings.append(WARNING_STAT_PROPERTY_TYPE_UNKNOWN)
        return NormalizedStatValue(
            key=_text(record.get("stat_key")) or str(property_type or ""),
            value=source_numeric,
            unit=STAT_UNIT_UNKNOWN,
            source_value=raw_value,
            source_numeric=source_numeric,
            source_unit=SOURCE_UNIT_UNKNOWN,
            property_type=property_type,
            property_name=property_name,
            warnings=tuple(_dedupe(warnings)),
        )

    normalized_value: float | None = None
    if source_numeric is not None:
        normalized_value = (
            source_numeric / 100.0
            if mapping.source_unit == SOURCE_UNIT_PERCENT_POINTS
            else source_numeric
        )

    return NormalizedStatValue(
        key=mapping.normalized_key,
        value=normalized_value,
        unit=mapping.unit,
        source_value=raw_value,
        source_numeric=source_numeric,
        source_unit=mapping.source_unit,
        property_type=property_type or mapping.property_type,
        property_name=property_name,
        gcsim_key=mapping.gcsim_key,
        warnings=tuple(_dedupe(warnings)),
    )


def normalize_artifact_build_snapshot_stats(
    artifact_build_snapshot: ArtifactBuildSnapshot | Mapping[str, Any],
) -> NormalizedStatBlock:
    snapshot = _snapshot_record(artifact_build_snapshot)
    stat_totals = _stat_totals_from_snapshot(artifact_build_snapshot)
    values = tuple(
        normalize_artifact_stat_total(stat_total)
        for stat_total in stat_totals
    )
    warnings = [
        warning
        for value in values
        for warning in value.warnings
    ]
    return NormalizedStatBlock(
        source="artifact_build_snapshot",
        values=values,
        warnings=tuple(_dedupe(warnings)),
        source_notes={
            "build_id": snapshot.get("build_id"),
            "build_name": snapshot.get("build_name") or "",
            "crit_value_is_virtual": snapshot.get("crit_value") is not None,
            "proc_count_is_virtual": snapshot.get("proc_count") is not None,
        },
    )


def normalized_stats_to_gcsim_add_stats(
    stats: NormalizedStatBlock | Iterable[NormalizedStatValue],
) -> dict[str, float]:
    values = stats.values if isinstance(stats, NormalizedStatBlock) else tuple(stats)
    result: dict[str, float] = {}
    for value in values:
        if not value.gcsim_key or value.value is None:
            continue
        if value.unit == STAT_UNIT_VIRTUAL:
            continue
        result[value.gcsim_key] = result.get(value.gcsim_key, 0.0) + float(value.value)
    return result


def _stat_total_record(
    stat_total: ArtifactStatTotalSnapshot | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(stat_total, ArtifactStatTotalSnapshot):
        return stat_total.to_dict()
    return dict(stat_total)


def _snapshot_record(snapshot: ArtifactBuildSnapshot | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(snapshot, ArtifactBuildSnapshot):
        return snapshot.to_dict()
    return dict(snapshot)


def _stat_totals_from_snapshot(
    snapshot: ArtifactBuildSnapshot | Mapping[str, Any],
) -> tuple[ArtifactStatTotalSnapshot | Mapping[str, Any], ...]:
    if isinstance(snapshot, ArtifactBuildSnapshot):
        return snapshot.stat_totals
    raw = snapshot.get("stat_totals") if isinstance(snapshot, Mapping) else None
    if isinstance(raw, list):
        return tuple(item for item in raw if isinstance(item, Mapping))
    return ()


def _first_present(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
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


def _optional_float_with_warning(value: Any) -> tuple[float | None, str | None]:
    if value is None or value == "":
        return None, WARNING_STAT_VALUE_MISSING
    text = str(value).strip().replace("%", "")
    try:
        return float(text), None
    except (TypeError, ValueError):
        return None, WARNING_STAT_VALUE_INVALID


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
