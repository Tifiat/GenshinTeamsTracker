"""Cheap, capture-free presentation index for an already detached Theory v3 snapshot.

The transport owns snapshot copying and identity validation. This module only
selects complete, legal published builds; it never recombines wearer choices or
changes the optimizer's numerical ranking.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, localcontext
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Iterator, Mapping

from .artifact_investment_rules import (
    ARTIFACT_MAIN_STAT_SLOTS,
    FIVE_STAR_SUBSTAT_ROLL_RULES,
    LEGAL_FIVE_STAR_MAIN_STATS_BY_SLOT,
)


# The order is part of Witness45.Lines: each integer indexes this exact vector.
THEORY_STAT_KEYS = (
    "atk", "atk_percent", "crit_damage", "crit_rate", "def",
    "def_percent", "em", "energy_recharge", "hp", "hp_percent",
)

GO_TO_CONFIG_STAT: Mapping[str, str] = MappingProxyType({
    "hp": "hp", "atk": "atk", "def": "def",
    "hp_percent": "hp%", "atk_percent": "atk%", "def_percent": "def%",
    "em": "em", "energy_recharge": "er",
    "crit_rate": "cr", "crit_damage": "cd",
    "pyro_damage_bonus": "pyro%", "hydro_damage_bonus": "hydro%",
    "electro_damage_bonus": "electro%", "cryo_damage_bonus": "cryo%",
    "anemo_damage_bonus": "anemo%", "geo_damage_bonus": "geo%",
    "dendro_damage_bonus": "dendro%",
    "physical_damage_bonus": "phys%", "healing_bonus": "heal",
})

_PENDING_REASONS = frozenset({
    "below_practical_band", "below_practical_band_not_deeply_refined",
    "below_verified_practical_band",
})
_SNAPSHOT_KIND = "gtt_gcsim_optimizer_theory_result_v3"
_MEASUREMENT_KIND = "theory_witness45_v1"
_COMPLETED_PHASES = frozenset({"first_light", "breadth_light", "deep_baseline"})
_INCOMPLETE_MARKERS = frozenset({"incomplete", "running", "unavailable"})
_STATUS_FIELDS = (
    "status", "state", "result_status", "search_status",
    "allocation_status", "witness_status",
)
_SLOTS = ARTIFACT_MAIN_STAT_SLOTS
_FOUR = range(4)
_FIVE = range(5)
_ZERO = Decimal(0)
_NINETY_FIVE = Decimal(95)
_NINETY_SEVEN = Decimal(97)
_HUNDRED = Decimal(100)
_TENTH = Decimal("0.1")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")

PackageKey = tuple[tuple[str, tuple[tuple[str, int], ...]], ...]
MainsKey = tuple[tuple[str, tuple[str, ...]], ...]


def _number(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _candidate_sha256(frame_sha256: str, identity: Mapping[str, Any]) -> str:
    """Recompute the native canonical full-build key for a receipt identity."""
    payload = {
        "kind": "gtt_gcsim_full_build_candidate_v1",
        "frame_sha256": frame_sha256,
        "build_identity": identity,
    }
    try:
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def theory_measurement(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    measurement = row.get("measurement")
    return measurement if isinstance(measurement, Mapping) else None


def validate_theory_measurement(row: Any) -> bool:
    """Bind one ordinary GCSIM receipt to the exact visible alias and witness."""
    if not isinstance(row, Mapping):
        return False
    measurement = theory_measurement(row)
    aliases = row.get("aliases")
    if measurement is None or not isinstance(aliases, list) or len(aliases) != 1:
        return False
    alias = aliases[0]
    identity = measurement.get("build_identity")
    if not isinstance(alias, Mapping) or not isinstance(identity, Mapping):
        return False
    if (
        set(identity) != {"kind", "packages", "witness45"}
        or identity.get("kind") != _MEASUREMENT_KIND
        or identity.get("packages") != alias.get("packages")
        or identity.get("witness45") != row.get("witness45")
    ):
        return False
    if not isinstance(identity.get("packages"), list) or len(identity["packages"]) != 4:
        return False
    for package in identity["packages"]:
        if not isinstance(package, Mapping) or set(package) != {"wearer_key", "sets"}:
            return False
        if not isinstance(package.get("sets"), list):
            return False
        if any(
            not isinstance(set_row, Mapping)
            or set(set_row) != {"set_uid", "count"}
            for set_row in package["sets"]
        ):
            return False

    candidate = measurement.get("candidate_sha256")
    if not _sha256(candidate) or row.get("family") != candidate:
        return False
    frame_sha256 = measurement.get("frame_sha256")
    if not _sha256(frame_sha256) or candidate != _candidate_sha256(frame_sha256, identity):
        return False
    for field in (
        "config_sha256", "engine_result_sha256", "engine_artifact_sha256",
        "source_manifest_sha256",
    ):
        if not _sha256(measurement.get(field)):
            return False
    if not _number(measurement.get("formula_dps")) or not _number(measurement.get("measured_dps")):
        return False
    if not _number(row.get("formula_dps")) or row["formula_dps"] != measurement["formula_dps"]:
        return False
    iterations = measurement.get("iterations")
    if type(iterations) is not int or iterations < 1:
        return False
    deviation, error = measurement.get("standard_deviation"), measurement.get("standard_error")
    if iterations == 1:
        if deviation is not None or error is not None:
            return False
    elif not _number(deviation) or not _number(error):
        return False
    elif not math.isclose(
        error, deviation / math.sqrt(iterations), rel_tol=1e-9, abs_tol=1e-12,
    ):
        return False
    if type(measurement.get("ignore_burst_energy")) is not bool:
        return False
    origins = measurement.get("origins")
    if not isinstance(origins, list) or not origins:
        return False
    for origin in origins:
        if not isinstance(origin, Mapping):
            return False
        if any(not isinstance(origin.get(field), str) or not origin[field] for field in (
            "kind", "phase", "family", "context_sha256",
        )):
            return False
        if not _sha256(origin.get("context_sha256")):
            return False
        diagnostics = origin.get("diagnostic_codes")
        if "diagnostic_codes" in origin and (
            not isinstance(diagnostics, list)
            or any(not isinstance(value, str) for value in diagnostics)
        ):
            return False
    return True


def _pending_reason(value: Any) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("code")
    return value if isinstance(value, str) else None


def _explicitly_incomplete(row: Mapping[str, Any]) -> bool:
    if any(row.get(flag) is False for flag in ("complete", "completed", "available")):
        return True
    return any(
        isinstance(row.get(field), str)
        and row[field].strip().casefold() in _INCOMPLETE_MARKERS
        for field in _STATUS_FIELDS
    )


def validate_theory_family(row: Any) -> bool:
    """Check one complete legal full45 family, including canonical coordinates.

    This is a presentation gate, not a gameplay score or search certificate.
    Alias/package validity is checked individually when building the index.
    """
    if not isinstance(row, Mapping) or _explicitly_incomplete(row):
        return False
    if not isinstance(row.get("family"), str) or not row["family"]:
        return False
    if not _number(row.get("formula_dps")):
        return False
    refinement = row.get("refinement_level")
    if type(refinement) is not int or refinement < 0:
        return False
    if "reason" in row and _pending_reason(row["reason"]) not in _PENDING_REASONS:
        return False

    allocations, witness = row.get("allocations"), row.get("witness45")
    if not isinstance(allocations, list) or len(allocations) != 4 or not isinstance(witness, Mapping):
        return False
    for field in ("Mains", "Lines", "Upgrades"):
        values = witness.get(field)
        if not isinstance(values, list) or len(values) != 4:
            return False
        if any(not isinstance(actor, list) or len(actor) != 5 for actor in values):
            return False

    wearers: set[str] = set()
    for actor in _FOUR:
        allocation = allocations[actor]
        if not isinstance(allocation, Mapping):
            return False
        wearer = allocation.get("wearer_key")
        mains, substats = allocation.get("main_stats"), allocation.get("substats")
        if not isinstance(wearer, str) or not wearer or wearer in wearers:
            return False
        wearers.add(wearer)
        if not isinstance(mains, Mapping) or set(mains) != set(_SLOTS):
            return False
        if not isinstance(substats, list) or len(substats) != len(THEORY_STAT_KEYS):
            return False
        if any(
            not isinstance(stat, Mapping)
            or stat.get("stat_key") != key
            or not _number(stat.get("roll_units"))
            or not _number(stat.get("stat_value"))
            for stat, key in zip(substats, THEORY_STAT_KEYS)
        ):
            return False
        if (
            not _number(allocation.get("spent_roll_units"))
            or allocation["spent_roll_units"] != 45
            or not _number(allocation.get("unspent_roll_units"))
            or allocation["unspent_roll_units"] != 0
        ):
            return False

        coordinate_units = [0.0] * len(THEORY_STAT_KEYS)
        initial_count = 0
        upgrade_units = 0.0
        for slot_index in _FIVE:
            slot = _SLOTS[slot_index]
            main = witness["Mains"][actor][slot_index]
            lines = witness["Lines"][actor][slot_index]
            upgrades = witness["Upgrades"][actor][slot_index]
            if (
                not isinstance(main, str)
                or mains[slot] != main
                or GO_TO_CONFIG_STAT.get(main) not in LEGAL_FIVE_STAR_MAIN_STATS_BY_SLOT[slot]
            ):
                return False
            if (
                not isinstance(lines, list) or len(lines) != 4
                or any(type(line) is not int or line < 0 or line >= len(THEORY_STAT_KEYS) for line in lines)
                or len(set(lines)) != 4
                or any(THEORY_STAT_KEYS[line] == main for line in lines)
            ):
                return False
            if (
                not isinstance(upgrades, list) or len(upgrades) != 4
                or any(not _number(units) or units > 5 or units * 4 != round(units * 4) for units in upgrades)
                or sum(upgrades) != 5
            ):
                return False
            initial_count += len(lines)
            upgrade_units += sum(upgrades)
            for line, coordinate in enumerate(lines):
                coordinate_units[coordinate] += 1 + upgrades[line]
        if initial_count != 20 or upgrade_units != 25 or sum(coordinate_units) != 45:
            return False
        if any(
            not math.isclose(stat["roll_units"], units, rel_tol=0, abs_tol=1e-7)
            for stat, units in zip(substats, coordinate_units)
        ):
            return False
        if any(
            not math.isclose(
                stat["stat_value"],
                units * FIVE_STAR_SUBSTAT_ROLL_RULES[GO_TO_CONFIG_STAT[key]].maximum,
                rel_tol=1e-10, abs_tol=1e-7,
            )
            for stat, units, key in zip(substats, coordinate_units, THEORY_STAT_KEYS)
        ):
            return False
    return validate_theory_measurement(row)


def noncrit_upgrades(row: Mapping[str, Any], actor: int | str) -> tuple[tuple[str, float], ...]:
    """Return this wearer's noncrit *upgrade* units in canonical wire-key order.

    ``actor`` is an allocation index or wearer_key. Initial line units and the
    allocation's 45-roll totals are deliberately excluded.
    """
    if not validate_theory_family(row):
        raise ValueError("Theory family has no complete legal full45 witness")
    if type(actor) is int and 0 <= actor < 4:
        actor_index = actor
    elif isinstance(actor, str):
        actor_index = next(
            (index for index, allocation in enumerate(row["allocations"])
             if allocation["wearer_key"] == actor),
            -1,
        )
    else:
        actor_index = -1
    if actor_index < 0:
        raise KeyError(actor)
    units_by_key = dict.fromkeys(THEORY_STAT_KEYS, 0.0)
    witness = row["witness45"]
    for lines, upgrades in zip(witness["Lines"][actor_index], witness["Upgrades"][actor_index]):
        for coordinate, units in zip(lines, upgrades):
            key = THEORY_STAT_KEYS[coordinate]
            if key not in {"crit_rate", "crit_damage"}:
                units_by_key[key] += units
    return tuple(
        (key, units_by_key[key])
        for key in THEORY_STAT_KEYS
        if key not in {"crit_rate", "crit_damage"} and units_by_key[key] > 0
    )


def _alias_package_key(alias: Any, wearers: set[str]) -> PackageKey | None:
    if not isinstance(alias, Mapping):
        return None
    if not isinstance(alias.get("tuple_key"), str) or not alias["tuple_key"]:
        return None
    if not _sha256(alias.get("context_sha256")):
        return None
    uncertainty = alias.get("uncertainty", [])
    if not isinstance(uncertainty, list) or any(not isinstance(reason, str) for reason in uncertainty):
        return None
    packages = alias.get("packages")
    if not isinstance(packages, list) or len(packages) != 4:
        return None
    parts: list[tuple[str, tuple[tuple[str, int], ...]]] = []
    seen: set[str] = set()
    for package in packages:
        if not isinstance(package, Mapping):
            return None
        wearer, sets = package.get("wearer_key"), package.get("sets")
        if not isinstance(wearer, str) or wearer not in wearers or wearer in seen:
            return None
        if not isinstance(sets, list):
            return None
        seen.add(wearer)
        set_parts: list[tuple[str, int]] = []
        set_uids: set[str] = set()
        for set_row in sets:
            if not isinstance(set_row, Mapping):
                return None
            uid, count = set_row.get("set_uid"), set_row.get("count")
            if (
                not isinstance(uid, str) or not uid or uid in set_uids
                or type(count) is not int or count not in (2, 4)
            ):
                return None
            set_uids.add(uid)
            set_parts.append((uid, count))
        if sum(count for _, count in set_parts) > 4:
            return None
        parts.append((wearer, tuple(sorted(set_parts))))
    return tuple(sorted(parts)) if seen == wearers else None


def _mains_key(row: Mapping[str, Any]) -> MainsKey:
    return tuple(sorted(
        (allocation["wearer_key"], tuple(allocation["main_stats"][slot] for slot in _SLOTS))
        for allocation in row["allocations"]
    ))


@dataclass(frozen=True, slots=True)
class TheoryEntry:
    family: str
    row: Mapping[str, Any]
    alias: Mapping[str, Any]
    score: float
    refinement_level: int


class TheoryResultIndex:
    """Index verified build aliases in source order against one fixed snapshot R.

    ``rejected_count`` counts omitted candidate aliases, or one malformed row
    when it has no alias list. The snapshot's ``unavailable`` list is not a
    candidate source and is not included in that count.
    """

    def __init__(self, snapshot: Mapping[str, Any]) -> None:
        if not isinstance(snapshot, Mapping):
            raise TypeError("Theory snapshot must be a mapping")
        reference = snapshot.get("reference_score")  # Read the fixed measured R once.
        reference_ok = _number(reference)
        self.reference: float = float(reference) if reference_ok else 0.0
        phase = snapshot.get("phase")
        co_leaders = snapshot.get("co_leaders")
        pending_rows = snapshot.get("pending")
        no_verified = (
            snapshot.get("status") == "no_verified_result"
            and snapshot.get("response_status") == "no_verified_result"
            and isinstance(co_leaders, list) and not co_leaders
            and isinstance(pending_rows, list) and not pending_rows
            and reference_ok and reference == 0
        )
        verified = (
            snapshot.get("status") == "success"
            and snapshot.get("response_status") == "ordinary_verified"
            and reference_ok
        )
        snapshot_ok = (
            type(snapshot.get("schema_version")) is int
            and snapshot["schema_version"] == 3
            and snapshot.get("schema_kind") == _SNAPSHOT_KIND
            and (verified or no_verified)
            and isinstance(phase, str) and phase in _COMPLETED_PHASES
        )
        entries: list[TheoryEntry] = []
        package_keys: list[PackageKey] = []
        mains_keys: list[MainsKey] = []
        groups: dict[PackageKey, list[int]] = {}
        seen_candidates: set[str] = set()
        rejected = 0
        for section in ("co_leaders", "pending"):
            rows = snapshot.get(section, ())
            if not isinstance(rows, (list, tuple)):
                continue
            for row in rows:
                aliases = row.get("aliases") if isinstance(row, Mapping) else None
                candidate_count = len(aliases) if isinstance(aliases, list) and aliases else 1
                measurement = theory_measurement(row) if isinstance(row, Mapping) else None
                score = measurement.get("measured_dps") if measurement is not None else None
                candidate = measurement.get("candidate_sha256") if measurement is not None else None
                if (
                    not snapshot_ok
                    or not validate_theory_family(row)
                    or not _number(score)
                    or score > self.reference
                    or candidate in seen_candidates
                    or (section == "pending" and _pending_reason(row.get("reason")) not in _PENDING_REASONS)
                ):
                    rejected += candidate_count
                    continue
                wearers = {allocation["wearer_key"] for allocation in row["allocations"]}
                if not isinstance(aliases, list) or not aliases:
                    rejected += 1
                    continue
                seen_candidates.add(candidate)
                mains_key = _mains_key(row)
                for alias in aliases:
                    package_key = _alias_package_key(alias, wearers)
                    if package_key is None:
                        rejected += 1
                        continue
                    index = len(entries)
                    entries.append(TheoryEntry(
                        family=row["family"], row=row, alias=alias,
                        score=float(score), refinement_level=row["refinement_level"],
                    ))
                    package_keys.append(package_key)
                    mains_keys.append(mains_key)
                    groups.setdefault(package_key, []).append(index)
        self.entries = tuple(entries)
        self.rejected_count = rejected
        self.package_groups: Mapping[PackageKey, tuple[int, ...]] = MappingProxyType({
            key: tuple(indices) for key, indices in groups.items()
        })
        self._package_keys = tuple(package_keys)
        self._mains_keys = tuple(mains_keys)

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[TheoryEntry]:
        return iter(self.entries)

    def __getitem__(self, index: int) -> TheoryEntry:
        return self.entries[index]

    def replacement_indices(self, index: int) -> tuple[int, ...]:
        """Existing same-package aliases with different whole-team mains.

        Duplicate mains states contribute only their first published entry.
        No single-wearer options are multiplied into imaginary team builds.
        """
        if type(index) is not int or index < 0 or index >= len(self.entries):
            raise IndexError(index)
        current = self._mains_keys[index]
        seen = {current}
        replacements: list[int] = []
        for candidate in self.package_groups[self._package_keys[index]]:
            state = self._mains_keys[candidate]
            if state in seen:
                continue
            seen.add(state)
            replacements.append(candidate)
        return tuple(replacements)


@dataclass(frozen=True, slots=True)
class TheoryScoreDisplay:
    percent: float
    percent_text: str
    deficit_text: str
    nonzero_deficit: bool
    color_band: str
    dps_text: str


def _percent_bucket(value: Decimal) -> int:
    if value == _ZERO:
        return 0
    if value < _NINETY_FIVE:
        return 1
    if value < _NINETY_SEVEN:
        return 2
    if value < _HUNDRED:
        return 3
    return 4


def _percent_text(percent: Decimal) -> str:
    bucket = _percent_bucket(percent)
    # A second or later decimal is needed only when normal rounding would
    # display a different 0/95/97/100 boundary. The tiny-positive case may
    # need more places than ordinary scores.
    max_places = max(40, -percent.adjusted() + 3) if percent else 40
    for places in range(1, max_places + 1):
        with localcontext() as context:
            context.prec = max(80, places + 10)
            rounded = percent.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
        if _percent_bucket(rounded) == bucket:
            return f"{rounded:.{places}f}"
    return format(percent, "f")


def theory_score_display(score: float, reference: float) -> TheoryScoreDisplay | None:
    """Format a score against the snapshot's fixed best-attained reference."""
    if not _number(score) or not _number(reference) or reference <= 0 or score > reference:
        return None
    with localcontext() as context:
        context.prec = 80
        score_decimal = _ZERO if score == 0 else Decimal(str(score))
        reference_decimal = Decimal(str(reference))
        percent = _HUNDRED * score_decimal / reference_decimal
        deficit = _HUNDRED - percent
    rounded_deficit = deficit.quantize(_TENTH, rounding=ROUND_HALF_UP)
    if score == reference:
        deficit_text = "0"
    elif rounded_deficit == _ZERO:
        deficit_text = "<0.1"
    else:
        deficit_text = f"{rounded_deficit:.1f}"
    return TheoryScoreDisplay(
        percent=float(percent), percent_text=_percent_text(percent),
        deficit_text=deficit_text, nonzero_deficit=score < reference,
        color_band="green" if percent >= _NINETY_SEVEN else "orange" if percent >= _NINETY_FIVE else "red",
        dps_text=format(score_decimal.to_integral_value(rounding=ROUND_HALF_UP), "f"),
    )


__all__ = [
    "GO_TO_CONFIG_STAT", "THEORY_STAT_KEYS", "TheoryEntry", "TheoryResultIndex",
    "TheoryScoreDisplay", "noncrit_upgrades", "theory_score_display", "validate_theory_family",
]
