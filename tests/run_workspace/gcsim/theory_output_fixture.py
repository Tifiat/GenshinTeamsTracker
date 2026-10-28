"""Public, capture-free output oracle for the verified Theory v3 seam."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math


REQUEST_SHA = "synthetic-request-sha"
SESSION_ID = "synthetic-theory-session"
WEARERS = ("wearer-a", "wearer-b", "wearer-c", "wearer-d")
SLOTS = ("flower", "plume", "sands", "goblet", "circlet")
STAT_KEYS = (
    "atk", "atk_percent", "crit_damage", "crit_rate", "def",
    "def_percent", "em", "energy_recharge", "hp", "hp_percent",
)
STAT_VALUES = (19.45, .0583, .0777, .0389, 23.15, .0729, 23.31, .0648, 298.75, .0583)
MAINS = (
    ("hp", "atk", "em", "em", "em"),
    ("hp", "atk", "energy_recharge", "hydro_damage_bonus", "crit_rate"),
    ("hp", "atk", "def_percent", "geo_damage_bonus", "crit_damage"),
    ("hp", "atk", "hp_percent", "hp_percent", "healing_bonus"),
)
GROUP_ROWS = (
    ("edge-3", 970.0, 3.0),
    ("reference", 1000.0, 0.0),
    ("outside-2", 979.999, 2.0001),
    ("inside-1", 990.0, 1.0),
    ("edge-2", 980.0, 2.0),
    ("inside-3", 970.001, 2.9999),
    ("inside-2", 980.001, 1.9999),
)
PENDING_ROWS = (
    ("outside-3", 969.999, 3.0001, "below_practical_band_not_deeply_refined", 0),
    ("far-below", 940.0, 6.0, "below_practical_band", 2),
)
EXPECTED_COUNTS = {
    "found_group_families": 7,
    "found_group_tuples": 7,
    "total_found_families": 9,
    "total_found_tuples": 27,
    "sensitivity_group_families": 4,
    "sensitivity_group_tuples": 4,
    "domain_tuples": "32",
    "unseen_tuples": "3",
}


def _sha256(label: str, value: object = "") -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(f"{label}\0{encoded}".encode("utf-8")).hexdigest()


def full45_witness() -> dict:
    lines = []
    for mains in MAINS:
        actor = []
        for main in mains:
            eligible = [3, 2, 7, 6, 9, 1]
            actor.append([index for index in eligible if STAT_KEYS[index] != main][:4])
        lines.append(actor)
    return {
        "Mains": [list(mains) for mains in MAINS],
        "Lines": lines,
        "Upgrades": [[[1.25, 1.5, 1, 1.25] for _ in SLOTS] for _ in WEARERS],
    }


def _packages(key: str, variant: int) -> list[dict]:
    packages = []
    for actor, wearer in enumerate(WEARERS):
        uid = f"set-{key}-{variant}" if actor == 0 else f"set-{key}-{variant}-{actor}"
        sets = [{"set_uid": uid, "count": 4}]
        if variant == 1:
            sets = [{"set_uid": uid, "count": 2}, {"set_uid": uid + "-pair", "count": 2}]
        if variant == 2 and actor == 3:
            sets = []
        packages.append({"wearer_key": wearer, "sets": sets})
    return packages


def refresh_measurement_identity(row: dict) -> None:
    """Refresh candidate/build binding after a test changes visible build data."""
    alias = row["aliases"][0]
    measurement = row["measurement"]
    identity = {
        "kind": "theory_witness45_v1",
        "packages": deepcopy(alias["packages"]),
        "witness45": deepcopy(row["witness45"]),
    }
    measurement["build_identity"] = identity
    payload = {
        "kind": "gtt_gcsim_full_build_candidate_v1",
        "frame_sha256": measurement["frame_sha256"],
        "build_identity": identity,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    encoded = encoded.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    measurement["candidate_sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    row["family"] = measurement["candidate_sha256"]


def family_row(
    key: str,
    score: float,
    deficit: float,
    *,
    refinement: int = 0,
    alias_variant: int = 0,
    formula_score: float | None = None,
    iterations: int = 500,
) -> dict:
    witness = full45_witness()
    allocations = []
    for actor, wearer in enumerate(WEARERS):
        units = [0.0] * len(STAT_KEYS)
        for slot, slot_lines in enumerate(witness["Lines"][actor]):
            for line, coordinate in enumerate(slot_lines):
                units[coordinate] += 1 + witness["Upgrades"][actor][slot][line]
        allocations.append({
            "wearer_key": wearer,
            "main_stats": dict(zip(SLOTS, witness["Mains"][actor])),
            "substats": [
                {"stat_key": stat, "roll_units": units[index], "stat_value": units[index] * STAT_VALUES[index]}
                for index, stat in enumerate(STAT_KEYS)
            ],
            "spent_roll_units": 45.0,
            "unspent_roll_units": 0.0,
        })
    packages = _packages(key, alias_variant)
    alias = {
        "tuple_key": f"choice-{key}-{alias_variant}",
        "context_sha256": _sha256("context", {"key": key, "variant": alias_variant}),
        "packages": packages,
        "uncertainty": [f"source-boundary-{key}-{alias_variant}"] if alias_variant else [],
        "provenance": {"bound_frame": {"source_family": key, "coordinates": list(STAT_KEYS)}},
    }
    formula = score + 37.25 if formula_score is None else formula_score
    measurement = {
        "candidate_sha256": "0" * 64,
        "frame_sha256": _sha256("frame", list(WEARERS)),
        "build_identity": {},
        "formula_dps": formula,
        "measured_dps": score,
        "iterations": iterations,
        "standard_deviation": None if iterations == 1 else 2.5,
        "standard_error": None if iterations == 1 else 2.5 / math.sqrt(iterations),
        "config_sha256": _sha256("config", key),
        "engine_result_sha256": _sha256("engine-result", key),
        "engine_artifact_sha256": _sha256("engine-artifact", "fixture"),
        "source_manifest_sha256": _sha256("source-manifest", "fixture"),
        "ignore_burst_energy": True,
        "origins": [{
            "kind": "theory_search_candidate",
            "phase": "first_light",
            "family": key,
            "context_sha256": alias["context_sha256"],
            "diagnostic_codes": [],
        }],
    }
    row = {
        "source_key": key,
        "family": "0" * 64,
        "formula_dps": formula,
        "deficit_percent": deficit,
        "refinement_level": refinement,
        "witness45": witness,
        "allocations": allocations,
        "aliases": [alias],
        "measurement": measurement,
    }
    refresh_measurement_identity(row)
    return row


def _recompute_deficits(rows: list[dict], reference: float) -> None:
    for row in rows:
        score = row["measurement"]["measured_dps"]
        row["deficit_percent"] = 0.0 if reference == 0 else 100.0 * (reference - score) / reference


def snapshot_with_rows(
    rows: list[dict], *, version: int = 1, phase: str = "first_light",
    publication_version: int | None = None,
) -> dict:
    frozen_rows = deepcopy(rows)
    reference = max((row["measurement"]["measured_dps"] for row in frozen_rows), default=0.0)
    _recompute_deficits(frozen_rows, reference)
    sensitivity = [
        row for row in frozen_rows
        if reference > 0 and row["measurement"]["measured_dps"] / reference >= 0.98
    ]
    row_count = len(frozen_rows)
    limit = max(7, row_count)
    return {
        "schema_version": 3,
        "schema_kind": "gtt_gcsim_optimizer_theory_result_v3",
        "status": "success" if row_count else "no_verified_result",
        "request_sha256": REQUEST_SHA,
        "session_id": SESSION_ID,
        "snapshot_version": version,
        "publication_version": publication_version if publication_version is not None else version,
        "phase": phase,
        "policy_id": "theory_h_light_common_h_20261010_v1",
        "search_status": "partial",
        "response_status": "ordinary_verified" if row_count else "no_verified_result",
        "finished_early": False,
        "reference_score": reference,
        "practical_band_percent": 3.0,
        "sensitivity_band_percent": 2.0,
        "co_leaders": frozen_rows,
        "pending": [],
        "unavailable": [],
        "total_found_families": row_count,
        "total_found_tuples": row_count,
        "found_group_families": row_count,
        "found_group_tuples": row_count,
        "sensitivity_group_families": len(sensitivity),
        "sensitivity_group_tuples": len(sensitivity),
        "domain_tuples": str(row_count + 3),
        "unseen_tuples": "3",
        "full_cartesian_covered": False,
        "source_upper": "unbounded",
        "outer_upper": "unbounded",
        "active_branch_work": {
            "formula_evaluations": 19, "gradient_evaluations": 7,
            "allocation_attempts": 11, "tuple_alias_hits": 5,
            "completed_catalog_passes": 1, "completed_deep_bundles": 0,
            "completed_catalog_sweeps": 1, "independent_starts": 4,
            "transferred_starts": 2,
        },
        "verification": {
            "policy_id": "theory_ordinary_finalists_v1",
            "limit": limit,
            "iterations": 500,
            "attempted_count": row_count,
            "completed_count": row_count,
            "failed_count": 0,
            "energy_rejected_count": 0,
            "candidate_count": row_count,
            "unverified_count": 0,
            "omitted_count": 0,
            "remaining_budget": limit - row_count,
            "in_progress": False,
            "response_lane_reserve": limit // 3,
            "response_lane_attempted_count": 0,
        },
        "rules": {
            "budget_roll_units_per_wearer": 45, "quarter_grid": True,
            "all_found_aliases": True, "reference_scope": "best_attained_comparable_ordinary",
            "practical_group_rank": "unordered_equivalent_group",
            "full_search_optimality_proved": False, "final_solution_cache_enabled": False,
        },
        "provenance": {
            "engine": {"sha256": _sha256("engine", "fixture"), "source_sha256": _sha256("source", "fixture")},
            "model": {"sha256": _sha256("model", "fixture"), "seeds": [17, 23]},
            "domain": {"wearers": list(WEARERS), "identity": "fixture-domain"},
            "numerical_policy": {"identity": "fixture-policy", "quarter_units": True},
        },
    }


def output_snapshot(
    version: int = 1, *, phase: str = "first_light", finished_early: bool = False,
    publication_version: int | None = None,
) -> dict:
    leaders = [family_row(*row) for row in GROUP_ROWS]
    snapshot = snapshot_with_rows(
        leaders, version=version, phase=phase, publication_version=publication_version,
    )
    pending = []
    for key, score, deficit, reason, refinement in PENDING_ROWS:
        row = family_row(key, score, deficit, refinement=refinement)
        row["reason"] = reason
        pending.append(row)
    snapshot["pending"] = pending
    all_rows = snapshot["co_leaders"] + snapshot["pending"]
    _recompute_deficits(all_rows, snapshot["reference_score"])
    snapshot["unavailable"] = [
        {
            "tuple_key": f"unavailable-choice-{index}",
            "packages": [
                {"wearer_key": wearer, "sets": [{"set_uid": f"unavailable-set-{index}-{actor}", "count": 4}]}
                for actor, wearer in enumerate(WEARERS)
            ],
            "reasons": [f"unavailable-source-{index}"],
        }
        for index in range(2)
    ]
    snapshot.update(EXPECTED_COUNTS)
    snapshot["verification"].update(
        limit=9, attempted_count=9, completed_count=9, candidate_count=9,
        remaining_budget=0, response_lane_reserve=3,
    )
    snapshot["finished_early"] = finished_early
    # The synthetic oracle uses a larger explicit lifetime limit than the
    # production default so transport and paging tests can retain nine rows.
    return snapshot


def no_verified_snapshot(
    version: int = 1, *, phase: str = "first_light", in_progress: bool = False,
) -> dict:
    snapshot = snapshot_with_rows([], version=version, phase=phase)
    snapshot["verification"].update(
        policy_id="theory_ordinary_finalists_v1",
        limit=7, iterations=500, attempted_count=0, completed_count=0,
        failed_count=0, energy_rejected_count=0, candidate_count=0,
        unverified_count=0, omitted_count=0, remaining_budget=7,
        in_progress=in_progress,
        response_lane_reserve=2, response_lane_attempted_count=0,
    )
    return snapshot


EXPECTED_GROUP_TUPLES = tuple(f"choice-{key}-0" for key, _, _ in GROUP_ROWS)
EXPECTED_PENDING_TUPLES = tuple(f"choice-{key}-0" for key, *_ in PENDING_ROWS)
EXPECTED_UNAVAILABLE_TUPLES = ("unavailable-choice-0", "unavailable-choice-1")
