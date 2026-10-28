"""Render a saved Theory candidate for bounded, ordinary GCSIM verification.

The allocation is a relaxed theoretical stat vector. This module does not
assign rolls to five physical artifacts or establish inventory feasibility.
The caller must bind the input config and, for set verification, supply the
active engine's set registry through ``known_sets``.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from decimal import Decimal
import math
import re
from typing import Any

from run_workspace.gcsim.artifact_investment_rules import (
    ARTIFACT_MAIN_STAT_SLOTS,
    FIVE_STAR_MAIN_STAT_VALUES,
    FIVE_STAR_MAX_ROLL_UNITS_PER_WEARER,
    FIVE_STAR_SUBSTAT_ROLL_RULES,
    LEGAL_FIVE_STAR_MAIN_STATS_BY_SLOT,
    five_star_substat_coordinate_cap,
)


# Inverse of optimizer_go_inputs._STAT_KEY; also matches finalists/render.go.
# Keep this research-only renderer independent of the production input loader.
_GCSIM_STAT_TOKEN = {
    "hp": "hp",
    "atk": "atk",
    "def": "def",
    "hp_percent": "hp%",
    "atk_percent": "atk%",
    "def_percent": "def%",
    "em": "em",
    "energy_recharge": "er",
    "crit_rate": "cr",
    "crit_damage": "cd",
    "healing_bonus": "heal",
    "pyro_damage_bonus": "pyro%",
    "hydro_damage_bonus": "hydro%",
    "electro_damage_bonus": "electro%",
    "cryo_damage_bonus": "cryo%",
    "anemo_damage_bonus": "anemo%",
    "geo_damage_bonus": "geo%",
    "dendro_damage_bonus": "dendro%",
    "physical_damage_bonus": "phys%",
}
_STAT_ORDER = tuple(_GCSIM_STAT_TOKEN)
_KNOWN_TOKENS = frozenset(_GCSIM_STAT_TOKEN.values())
_ACTOR = r"[a-z][a-z0-9_]*"
_SET_UID = re.compile(r"[a-z][a-z0-9_]*\Z")
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_CHAR_HINT = re.compile(r"^\s*\S+\s+char\b", re.IGNORECASE)
_ARTIFACT_HINT = re.compile(r"^\s*\S+\s+add\s+(?:stats|set)\b", re.IGNORECASE)
_CHAR_ROW = re.compile(rf"({_ACTOR}) char [^;\r\n]+;\Z")
_STATS_ROW = re.compile(rf"({_ACTOR}) add stats ([^;\r\n]+);\Z")
_SET_ROW = re.compile(rf'{_ACTOR} add set="([a-z][a-z0-9_]*)" count=([1-5]);\Z')
_LABEL = "# GTT Theory relaxed theoretical artifact vector; five-piece physical feasibility unverified."


def _number(value: Any, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite nonnegative number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be a finite nonnegative number") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return number


def _rows(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _wearer_rows(value: Any, name: str, actors: tuple[str, ...]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for row in _rows(value, name):
        if not isinstance(row, Mapping):
            raise ValueError(f"{name} contains a non-object row")
        wearer = row.get("wearer_key")
        if wearer not in actors or wearer in result:
            raise ValueError(f"{name} has a foreign or duplicate wearer: {wearer!r}")
        result[wearer] = row
    if set(result) != set(actors):
        raise ValueError(f"{name} must cover every declared wearer exactly once")
    return result


def _validate_package(
    package: Mapping[str, Any], wearer: str, known_sets: frozenset[str] | None
) -> tuple[tuple[str, int], ...]:
    if "sets" not in package:
        raise ValueError(f"{wearer} package is missing its sets field")
    source = package.get("sets")
    if source is None:
        return ()
    rows = _rows(source, f"{wearer} sets")
    sets: list[tuple[str, int]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError(f"{wearer} set must be an object")
        uid, count = row.get("set_uid"), row.get("count")
        if not isinstance(uid, str) or _SET_UID.fullmatch(uid) is None:
            raise ValueError(f"{wearer} has a noncanonical set key")
        if known_sets is not None and uid not in known_sets:
            raise ValueError(f"{wearer} set is absent from the bound registry: {uid}")
        if type(count) is not int:
            raise ValueError(f"{wearer} set count must be an integer")
        sets.append((uid, count))
    counts = sorted(count for _, count in sets)
    if counts not in ([], [2], [4], [2, 2]) or len({uid for uid, _ in sets}) != len(sets):
        raise ValueError(f"{wearer} package must be no bonus, one 2p, one 4p, or distinct 2+2")
    return tuple(sets)


def _validate_allocation(
    allocation: Mapping[str, Any], wearer: str, roll_budget: float
) -> dict[str, Decimal]:
    mains = allocation.get("main_stats")
    if not isinstance(mains, Mapping) or set(mains) != set(ARTIFACT_MAIN_STAT_SLOTS):
        raise ValueError(f"{wearer} requires exactly five named main stats")
    main_tokens: list[str] = []
    totals: dict[str, Decimal] = {}
    for slot in ARTIFACT_MAIN_STAT_SLOTS:
        key = mains[slot]
        if not isinstance(key, str) or key not in _GCSIM_STAT_TOKEN:
            raise ValueError(f"{wearer} has an unknown main stat at {slot}")
        token = _GCSIM_STAT_TOKEN[key]
        if token not in LEGAL_FIVE_STAR_MAIN_STATS_BY_SLOT[slot]:
            raise ValueError(f"{wearer} has an illegal main stat at {slot}: {key}")
        main_tokens.append(token)
        totals[token] = totals.get(token, Decimal(0)) + Decimal(FIVE_STAR_MAIN_STAT_VALUES[token])

    substats = _rows(allocation.get("substats"), f"{wearer} substats")
    seen: set[str] = set()
    units_total = 0.0
    for row in substats:
        if not isinstance(row, Mapping):
            raise ValueError(f"{wearer} substat must be an object")
        key = row.get("stat_key")
        if not isinstance(key, str) or key not in _GCSIM_STAT_TOKEN:
            raise ValueError(f"{wearer} has an unknown substat axis")
        token = _GCSIM_STAT_TOKEN[key]
        if token not in FIVE_STAR_SUBSTAT_ROLL_RULES or key in seen:
            raise ValueError(f"{wearer} has an illegal or duplicate substat axis: {key}")
        seen.add(key)
        units = _number(row.get("roll_units"), f"{wearer} {key} roll_units")
        value = _number(row.get("stat_value"), f"{wearer} {key} stat_value")
        cap = five_star_substat_coordinate_cap(token, tuple(main_tokens))
        if units > cap + 1e-9:
            raise ValueError(f"{wearer} {key} exceeds its eligible-piece roll cap")
        expected = units * FIVE_STAR_SUBSTAT_ROLL_RULES[token].maximum
        if not math.isclose(value, expected, rel_tol=1e-10, abs_tol=1e-9):
            raise ValueError(f"{wearer} {key} stat_value does not match maximum-roll units")
        units_total += units
        if value:
            totals[token] = totals.get(token, Decimal(0)) + Decimal(str(row["stat_value"]))

    spent = _number(allocation.get("spent_roll_units"), f"{wearer} spent_roll_units")
    unspent = _number(allocation.get("unspent_roll_units"), f"{wearer} unspent_roll_units")
    if (
        units_total > roll_budget + 1e-9
        or not math.isclose(units_total, spent, rel_tol=1e-10, abs_tol=1e-9)
        or not math.isclose(spent + unspent, roll_budget, rel_tol=1e-10, abs_tol=1e-9)
    ):
        raise ValueError(f"{wearer} roll totals do not match the bounded budget")
    return totals


def _config_rows(config: str) -> tuple[list[str], tuple[str, ...], dict[str, int], set[int]]:
    lines = config.splitlines(keepends=True)
    actors: list[str] = []
    stats_rows: dict[str, int] = {}
    set_rows: set[int] = set()
    old_sets: dict[str, list[tuple[str, int]]] = {}
    for index, line in enumerate(lines):
        body = line.rstrip("\r\n")
        if _CHAR_HINT.match(body):
            match = _CHAR_ROW.fullmatch(body)
            if match is None or match[1] in actors:
                raise ValueError("noncanonical or duplicate character declaration")
            actors.append(match[1])
        if not _ARTIFACT_HINT.match(body):
            continue
        stat_match = _STATS_ROW.fullmatch(body)
        if stat_match is not None:
            actor, stats = stat_match.groups()
            if actor in stats_rows:
                raise ValueError(f"duplicate stats row for {actor}")
            keys: set[str] = set()
            for token in stats.split(" "):
                pair = token.split("=")
                if (
                    len(pair) != 2
                    or pair[0] not in _KNOWN_TOKENS
                    or pair[0] in keys
                    or _NUMBER.fullmatch(pair[1]) is None
                ):
                    raise ValueError(f"noncanonical stats row for {actor}")
                keys.add(pair[0])
            stats_rows[actor] = index
            continue
        set_match = _SET_ROW.fullmatch(body)
        if set_match is None:
            raise ValueError("noncanonical set or stats row")
        actor = body.split(" ", 1)[0]
        old_sets.setdefault(actor, []).append((set_match[1], int(set_match[2])))
        set_rows.add(index)
    if len(actors) != 4 or len(set(actors)) != 4:
        raise ValueError("Theory verification requires exactly four character declarations")
    if set(stats_rows) != set(actors) or set(old_sets) - set(actors):
        raise ValueError("missing or orphan artifact stats/set row")
    for actor, sets in old_sets.items():
        if len(sets) > 2 or len({uid for uid, _ in sets}) != len(sets) or sum(count for _, count in sets) > 5:
            raise ValueError(f"invalid existing set rows for {actor}")
    return lines, tuple(actors), stats_rows, set_rows


def _format_stats(totals: Mapping[str, Decimal], actor: str) -> str:
    tokens = (
        f"{_GCSIM_STAT_TOKEN[key]}={format(totals[_GCSIM_STAT_TOKEN[key]], 'f')}"
        for key in _STAT_ORDER
        if totals.get(_GCSIM_STAT_TOKEN[key], Decimal(0)) != 0
    )
    return f"{actor} add stats {' '.join(tokens)};"


def render_candidate_config(
    neutral_config: str,
    candidate: Mapping[str, Any],
    *,
    roll_budget: float = 45,
    known_sets: Collection[str] | None = None,
) -> str:
    """Replace artifact rows with one validated relaxed Theory vector per actor.

    All nonartifact lines retain their original bytes and order. ``known_sets``
    should come from the active engine registry; omitted registry validation is
    suitable only for inspecting a saved candidate, not a bound verification.
    """
    if not isinstance(neutral_config, str) or not isinstance(candidate, Mapping):
        raise ValueError("a config string and candidate object are required")
    budget = _number(roll_budget, "roll_budget")
    if budget > FIVE_STAR_MAX_ROLL_UNITS_PER_WEARER:
        raise ValueError("roll_budget exceeds the five-artifact maximum")
    if known_sets is not None:
        if isinstance(known_sets, (str, bytes)) or not isinstance(known_sets, Collection):
            raise ValueError("known_sets must be a collection of canonical set keys")
        if any(not isinstance(uid, str) or _SET_UID.fullmatch(uid) is None for uid in known_sets):
            raise ValueError("known_sets contains a noncanonical key")
        registry: frozenset[str] | None = frozenset(known_sets)
    else:
        registry = None

    lines, actors, stats_rows, set_rows = _config_rows(neutral_config)
    allocations = _wearer_rows(candidate.get("allocations"), "allocations", actors)
    packages = _wearer_rows(candidate.get("packages"), "packages", actors)
    totals = {actor: _validate_allocation(allocations[actor], actor, budget) for actor in actors}
    package_rows = {actor: _validate_package(packages[actor], actor, registry) for actor in actors}
    actor_by_stats_line = {index: actor for actor, index in stats_rows.items()}

    result: list[str] = []
    labeled = False
    default_newline = "\r\n" if "\r\n" in neutral_config else "\n"
    for index, line in enumerate(lines):
        if index in set_rows:
            continue
        actor = actor_by_stats_line.get(index)
        if actor is None:
            result.append(line)
            continue
        ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
        insertion_ending = ending or default_newline
        if not labeled:
            result.append(_LABEL + insertion_ending)
            labeled = True
        for uid, count in package_rows[actor]:
            result.append(f'{actor} add set="{uid}" count={count};' + insertion_ending)
        result.append(_format_stats(totals[actor], actor) + ending)
    return "".join(result)


__all__ = ["render_candidate_config"]
