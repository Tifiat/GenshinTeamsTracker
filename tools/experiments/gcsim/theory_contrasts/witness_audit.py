"""Fail-closed validation for quarter-grid theory receipt witnesses.

The domain constants mirror ``native/gcsim_optimizer/internal/theory/solver.go``
(``legalMainStats`` and ``substatValues``).  Line indices follow the pinned
theory prototype's ``StatKeys`` order in
``tools/experiments/gcsim/theory_feasible/kernel/kernel.go``.  This validates
the idealized theory domain; it does not claim physical roll-tier realizability
or infer artifact rarity from set identifiers.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


STAT_KEYS = (
    "atk",
    "atk_percent",
    "crit_damage",
    "crit_rate",
    "def",
    "def_percent",
    "em",
    "energy_recharge",
    "hp",
    "hp_percent",
)

# Maximum-value roll equivalents from native/gcsim_optimizer/internal/theory/solver.go.
SUBSTAT_VALUES = {
    "atk": 19.45,
    "atk_percent": 0.0583,
    "crit_damage": 0.0777,
    "crit_rate": 0.0389,
    "def": 23.15,
    "def_percent": 0.0729,
    "em": 23.31,
    "energy_recharge": 0.0648,
    "hp": 298.75,
    "hp_percent": 0.0583,
}

SLOTS = ("flower", "plume", "sands", "goblet", "circlet")
MAIN_CHOICES = {
    "flower": {"hp"},
    "plume": {"atk"},
    "sands": {"atk_percent", "def_percent", "em", "energy_recharge", "hp_percent"},
    "goblet": {
        "anemo_damage_bonus",
        "atk_percent",
        "cryo_damage_bonus",
        "def_percent",
        "dendro_damage_bonus",
        "electro_damage_bonus",
        "em",
        "geo_damage_bonus",
        "hp_percent",
        "hydro_damage_bonus",
        "physical_damage_bonus",
        "pyro_damage_bonus",
    },
    "circlet": {"atk_percent", "crit_damage", "crit_rate", "def_percent", "em", "healing_bonus", "hp_percent"},
}

_STATE_KEYS = frozenset(("Mains", "Lines", "Upgrades"))
_TOL = 1e-8


def _fail(path: str, message: str) -> ValueError:
    return ValueError(f"{path}: {message}")


def _seq(value: Any, path: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise _fail(path, "expected a sequence")
    return value


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _fail(path, "expected a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise _fail(path, "expected a finite number")
    return number


def _state_signature(state: Mapping[str, Any], path: str) -> tuple[Any, ...]:
    """Validate one Mains/Lines/Upgrades object and return its canonical key."""
    if not isinstance(state, Mapping) or not _STATE_KEYS.issubset(state):
        raise _fail(path, "expected Mains, Lines, and Upgrades")

    mains = _seq(state["Mains"], f"{path}.Mains")
    lines = _seq(state["Lines"], f"{path}.Lines")
    upgrades = _seq(state["Upgrades"], f"{path}.Upgrades")
    if not (len(mains) == len(lines) == len(upgrades) == 4):
        raise _fail(path, "expected exactly four wearers")

    canonical_mains: list[tuple[str, ...]] = []
    canonical_lines: list[tuple[tuple[int, ...], ...]] = []
    canonical_upgrades: list[tuple[tuple[float, ...], ...]] = []

    for actor in range(4):
        actor_mains = _seq(mains[actor], f"{path}.Mains[{actor}]")
        actor_lines = _seq(lines[actor], f"{path}.Lines[{actor}]")
        actor_upgrades = _seq(upgrades[actor], f"{path}.Upgrades[{actor}]")
        if not (len(actor_mains) == len(actor_lines) == len(actor_upgrades) == 5):
            raise _fail(path, f"wearer {actor} must have five artifacts")

        mains_row: list[str] = []
        lines_row: list[tuple[int, ...]] = []
        upgrades_row: list[tuple[float, ...]] = []
        actor_extra = 0.0

        for slot, slot_name in enumerate(SLOTS):
            main = actor_mains[slot]
            if not isinstance(main, str) or main not in MAIN_CHOICES[slot_name]:
                raise _fail(path, f"wearer {actor} has illegal {slot_name} main {main!r}")
            slot_lines = _seq(actor_lines[slot], f"{path}.Lines[{actor}][{slot}]")
            slot_upgrades = _seq(actor_upgrades[slot], f"{path}.Upgrades[{actor}][{slot}]")
            if len(slot_lines) != 4 or len(slot_upgrades) != 4:
                raise _fail(path, f"wearer {actor} {slot_name} needs four substat lines")

            indices: list[int] = []
            for line, index in enumerate(slot_lines):
                if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(STAT_KEYS):
                    raise _fail(path, f"wearer {actor} {slot_name} has invalid substat index {index!r}")
                indices.append(index)
            if len(set(indices)) != 4:
                raise _fail(path, f"wearer {actor} {slot_name} repeats a substat line")
            if any(STAT_KEYS[index] == main for index in indices):
                raise _fail(path, f"wearer {actor} {slot_name} has a substat matching its main")

            extra_values: list[float] = []
            slot_extra = 0.0
            for line, raw_extra in enumerate(slot_upgrades):
                extra = _number(raw_extra, f"{path}.Upgrades[{actor}][{slot}][{line}]")
                if extra < -1e-9:
                    raise _fail(path, f"wearer {actor} {slot_name} has a negative upgrade")
                if abs(extra * 4 - round(extra * 4)) > _TOL:
                    raise _fail(path, f"wearer {actor} {slot_name} has an off-quarter upgrade")
                extra_values.append(extra)
                slot_extra += extra
            if slot_extra > 5 + _TOL:
                raise _fail(path, f"wearer {actor} {slot_name} exceeds five upgrade units")

            mains_row.append(main)
            lines_row.append(tuple(indices))
            upgrades_row.append(tuple(extra_values))
            actor_extra += slot_extra

        # Each artifact starts with four base lines: 20 base + exactly 25
        # quarter-grid upgrades is the requested 45-unit allocation.
        if abs(actor_extra - 25) > _TOL:
            raise _fail(path, f"wearer {actor} has {20 + actor_extra:g} total roll units, expected 45")
        canonical_mains.append(tuple(mains_row))
        canonical_lines.append(tuple(lines_row))
        canonical_upgrades.append(tuple(upgrades_row))

    return (tuple(canonical_mains), tuple(canonical_lines), tuple(canonical_upgrades))


def _validate_package(row: Any, path: str) -> tuple[str, tuple[tuple[str, int], ...]]:
    if not isinstance(row, Mapping):
        raise _fail(path, "package row must be an object")
    wearer = row.get("wearer_key")
    if not isinstance(wearer, str) or not wearer:
        raise _fail(path, "package row is missing wearer_key")
    sets = _seq(row.get("sets"), f"{path}.sets")
    if len(sets) > 2:
        raise _fail(path, "package has more than two selected sets")

    normalized: list[tuple[str, int]] = []
    seen: set[str] = set()
    counts: list[int] = []
    for index, selected in enumerate(sets):
        item_path = f"{path}.sets[{index}]"
        if not isinstance(selected, Mapping):
            raise _fail(item_path, "selected set must be an object")
        uid = selected.get("set_uid")
        count = selected.get("count")
        if not isinstance(uid, str) or not uid:
            raise _fail(item_path, "selected set is missing set_uid")
        if uid in seen:
            raise _fail(item_path, "selected set UID is duplicated")
        if isinstance(count, bool) or not isinstance(count, int) or count not in (2, 4):
            raise _fail(item_path, "set count must be 2 or 4")
        if "rarity" in selected and selected["rarity"] != 5:
            raise _fail(item_path, "explicitly reported set rarity is not five-star")
        seen.add(uid)
        counts.append(count)
        normalized.append((uid, count))

    if counts not in ([], [2], [4], [2, 2]):
        raise _fail(path, "package must be none, 2-piece, 4-piece, or two distinct 2-piece sets")
    return wearer, tuple(sorted(normalized))


def _validate_candidate(candidate: Mapping[str, Any], path: str) -> tuple[tuple[Any, ...], tuple[Any, ...], str]:
    score = _number(candidate.get("formula_dps"), f"{path}.formula_dps")
    if score <= 0:
        raise _fail(path, "formula_dps must be positive")
    witness = candidate.get("feasibility_witness")
    state_sig = _state_signature(witness, f"{path}.feasibility_witness")

    allocations = _seq(candidate.get("allocations"), f"{path}.allocations")
    packages = _seq(candidate.get("packages"), f"{path}.packages")
    if len(allocations) != 4 or len(packages) != 4:
        raise _fail(path, "candidate must include four allocations and four package rows")

    package_signature: list[Any] = []
    wearer_order: list[str] = []
    mains = witness["Mains"]
    lines = witness["Lines"]
    upgrades = witness["Upgrades"]
    for actor in range(4):
        allocation = allocations[actor]
        if not isinstance(allocation, Mapping):
            raise _fail(path, f"allocation row {actor} must be an object")
        wearer = allocation.get("wearer_key")
        if not isinstance(wearer, str) or not wearer:
            raise _fail(path, f"allocation row {actor} is missing wearer_key")
        if wearer in wearer_order:
            raise _fail(path, "wearer_key is duplicated")
        wearer_order.append(wearer)

        package_wearer, normalized_sets = _validate_package(packages[actor], f"{path}.packages[{actor}]")
        if package_wearer != wearer:
            raise _fail(path, f"package/allocation wearer order differs at row {actor}")
        package_signature.append((wearer, normalized_sets))

        main_stats = allocation.get("main_stats")
        if not isinstance(main_stats, Mapping) or set(main_stats) != set(SLOTS):
            raise _fail(path, f"allocation row {actor} must export all five main_stats")
        expected_mains = {slot: mains[actor][index] for index, slot in enumerate(SLOTS)}
        if dict(main_stats) != expected_mains:
            raise _fail(path, f"allocation row {actor} main_stats differ from its witness")

        if abs(_number(allocation.get("spent_roll_units"), f"{path}.allocations[{actor}].spent_roll_units") - 45) > _TOL:
            raise _fail(path, f"allocation row {actor} does not report 45 spent roll units")
        if abs(_number(allocation.get("unspent_roll_units"), f"{path}.allocations[{actor}].unspent_roll_units")) > _TOL:
            raise _fail(path, f"allocation row {actor} does not report zero unspent roll units")
        stats = _seq(allocation.get("substats"), f"{path}.allocations[{actor}].substats")
        if len(stats) != len(STAT_KEYS):
            raise _fail(path, f"allocation row {actor} must export all ten substats")

        expected_rolls = [0.0] * len(STAT_KEYS)
        for slot in range(5):
            for line, stat_index in enumerate(lines[actor][slot]):
                expected_rolls[stat_index] += 1 + float(upgrades[actor][slot][line])

        actual_by_key: dict[str, Mapping[str, Any]] = {}
        for stat in stats:
            if not isinstance(stat, Mapping):
                raise _fail(path, f"allocation row {actor} substat must be an object")
            key = stat.get("stat_key")
            if not isinstance(key, str) or key not in SUBSTAT_VALUES or key in actual_by_key:
                raise _fail(path, f"allocation row {actor} has invalid or duplicate stat_key {key!r}")
            actual_by_key[key] = stat
        if set(actual_by_key) != set(STAT_KEYS):
            raise _fail(path, f"allocation row {actor} substat keys differ from the domain")

        for index, key in enumerate(STAT_KEYS):
            row = actual_by_key[key]
            reported_rolls = _number(row.get("roll_units"), f"{path}.allocations[{actor}].{key}.roll_units")
            expected_value = expected_rolls[index] * SUBSTAT_VALUES[key]
            reported_value = _number(row.get("stat_value"), f"{path}.allocations[{actor}].{key}.stat_value")
            if not math.isclose(reported_rolls, expected_rolls[index], rel_tol=1e-10, abs_tol=_TOL):
                raise _fail(path, f"allocation row {actor} {key} roll_units differ from its witness")
            if not math.isclose(reported_value, expected_value, rel_tol=1e-10, abs_tol=_TOL):
                raise _fail(path, f"allocation row {actor} {key} stat_value differs from its witness")

    return state_sig, tuple(package_signature), "rarity_not_inferred"


def audit_records(records: Any) -> dict[str, Any]:
    """Recursively validate all candidate witnesses and standalone start states.

    ``occurrences`` counts every candidate witness location, including repeated
    checkpoint and ``top_witnesses`` entries. ``distinct_states`` deduplicates
    only allocation states. ``distinct_signatures`` deduplicates allocation
    states together with the ordered four-wearer package assignments. Package
    rarity is deliberately reported as unknown unless explicit non-five-star
    metadata makes a candidate invalid; it is never inferred from a set UID.
    """
    if isinstance(records, (str, bytes, Mapping)) or not isinstance(records, Sequence):
        raise ValueError("records: expected a sequence")

    occurrence_count = 0
    standalone_state_count = 0
    candidate_states: set[tuple[Any, ...]] = set()
    candidate_signatures: set[tuple[Any, ...]] = set()
    all_standalone_states: set[tuple[Any, ...]] = set()
    package_profiles = {"none": 0, "2p": 0, "4p": 0, "2+2": 0}

    def visit(node: Any, path: str) -> None:
        nonlocal occurrence_count, standalone_state_count
        if isinstance(node, Mapping):
            present_state_keys = _STATE_KEYS.intersection(node)
            if present_state_keys and present_state_keys != _STATE_KEYS:
                raise _fail(path, "partial standalone state: expected Mains, Lines, and Upgrades together")

            if "feasibility_witness" in node:
                if not isinstance(node, Mapping):
                    raise _fail(path, "candidate container must be an object")
                state_sig, package_sig, _ = _validate_candidate(node, path)
                occurrence_count += 1
                candidate_states.add(state_sig)
                candidate_signatures.add((state_sig, package_sig))
                # Accumulate structural package mix without asserting rarity.
                for _, sets in package_sig:
                    counts = [count for _, count in sets]
                    profile = "none" if not counts else "2p" if counts == [2] else "4p" if counts == [4] else "2+2"
                    package_profiles[profile] += 1
            elif present_state_keys == _STATE_KEYS:
                state_sig = _state_signature(node, path)
                standalone_state_count += 1
                all_standalone_states.add(state_sig)

            for key, child in node.items():
                if key in _STATE_KEYS or key == "feasibility_witness":
                    continue
                if key in ("candidate", "best") and isinstance(child, Mapping):
                    if "feasibility_witness" not in child:
                        raise _fail(f"{path}.{key}", "candidate is missing feasibility_witness")
                if key == "top_witnesses":
                    witnesses = _seq(child, f"{path}.top_witnesses")
                    for index, item in enumerate(witnesses):
                        if not isinstance(item, Mapping) or "feasibility_witness" not in item:
                            raise _fail(f"{path}.top_witnesses[{index}]", "top witness is missing feasibility_witness")
                visit(child, f"{path}.{key}")
        elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
            for index, child in enumerate(node):
                visit(child, f"{path}[{index}]")

    visit(records, "records")
    return {
        "occurrences": occurrence_count,
        "distinct_states": len(candidate_states),
        "distinct_signatures": len(candidate_signatures),
        "standalone_state_occurrences": standalone_state_count,
        "standalone_distinct_states": len(all_standalone_states),
        "package_profile_rows": package_profiles,
        "package_rarity": "unknown",
        "package_rarity_inferred": False,
    }
