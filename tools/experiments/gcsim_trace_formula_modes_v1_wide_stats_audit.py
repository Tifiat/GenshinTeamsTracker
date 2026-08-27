from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
from time import perf_counter

from run_workspace.gcsim.engine_store import load_engine_manifest
from run_workspace.gcsim.optimizer_engine_context import (
    load_active_gcsim_optimizer_engine_context,
)
from run_workspace.gcsim.trace_equation import (
    ArtifactStatReplacement,
    RotationFormulaMode,
    SourceManifestBinding,
    TraceExtractionRequest,
    TraceObjective,
    canonical_json,
    compile_rotation_formula_filters,
    decode_engine_trace_v6,
    decode_source_manifest_body,
    evaluate_rotation_formula_filter,
)


ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / ".codex_tmp" / "forwarded_attack_v1_store"
TRACE_PATH = ROOT / ".codex_tmp" / "forwarded_attack_v1_run" / "trace.json"


@dataclass(frozen=True, slots=True)
class StressProfile:
    family: str
    profile_id: str
    replacements: tuple[ArtifactStatReplacement, ...]


def main() -> None:
    started = perf_counter()
    trace = _load_trace()
    decoded_at = perf_counter()
    filters = compile_rotation_formula_filters(trace)
    compiled_at = perf_counter()
    profiles = _profiles(filters.standard.relevant_coordinates)
    profiles_at = perf_counter()

    rows = []
    for profile in profiles:
        standard = evaluate_rotation_formula_filter(
            filters, RotationFormulaMode.STANDARD, profile.replacements
        )
        fast = evaluate_rotation_formula_filter(
            filters, RotationFormulaMode.FAST, profile.replacements
        )
        duration = filters.standard.duration_frames
        damage_error = abs(standard.candidate_damage - fast.candidate_damage)
        dps_error = (
            None if duration is None else damage_error * 60.0 / duration
        )
        rows.append(
            {
                "family": profile.family,
                "profile_id": profile.profile_id,
                "replacements": [row.to_dict() for row in profile.replacements],
                "standard_damage": standard.candidate_damage,
                "fast_damage": fast.candidate_damage,
                "standard_delta": standard.expected_delta,
                "fast_delta": fast.expected_delta,
                "damage_error": damage_error,
                "dps_error": dps_error,
                "relative_damage_error": damage_error
                / max(abs(standard.candidate_damage), 1e-12),
                "signs_match": _sign(standard.expected_delta)
                == _sign(fast.expected_delta),
            }
        )
    evaluated_at = perf_counter()

    standard_sorted = sorted(
        rows, key=lambda row: (-row["standard_damage"], row["profile_id"])
    )
    fast_sorted = sorted(
        rows, key=lambda row: (-row["fast_damage"], row["profile_id"])
    )
    standard_rank = {
        row["profile_id"]: index + 1 for index, row in enumerate(standard_sorted)
    }
    fast_rank = {
        row["profile_id"]: index + 1 for index, row in enumerate(fast_sorted)
    }
    for row in rows:
        row["standard_rank"] = standard_rank[row["profile_id"]]
        row["fast_rank"] = fast_rank[row["profile_id"]]

    output = {
        "engine_calls": 0,
        "diagnostic_only": True,
        "trace_decode_seconds": decoded_at - started,
        "both_filters_compile_seconds": compiled_at - decoded_at,
        "profile_construction_seconds": profiles_at - compiled_at,
        "both_modes_evaluation_seconds": evaluated_at - profiles_at,
        "total_seconds": evaluated_at - started,
        "profile_count": len(rows),
        "profile_families": {
            family: _family_summary(
                [row for row in rows if row["family"] == family],
                filters.standard.duration_frames,
            )
            for family in sorted({row["family"] for row in rows})
        },
        "overall": _family_summary(rows, filters.standard.duration_frames),
        "spearman_rank_correlation": _spearman(
            tuple(
                (standard_rank[row["profile_id"]], fast_rank[row["profile_id"]])
                for row in rows
            )
        ),
        "top_recall": {
            str(limit): _top_recall(standard_sorted, fast_sorted, limit)
            for limit in (8, 16, 32, 64, 128)
        },
        "same_leader": standard_sorted[0]["profile_id"]
        == fast_sorted[0]["profile_id"],
        "standard_leader_fast_rank": fast_rank[standard_sorted[0]["profile_id"]],
        "fast_leader_standard_rank": standard_rank[fast_sorted[0]["profile_id"]],
        "sign_disagreement_count": sum(not row["signs_match"] for row in rows),
        "sign_disagreements": sorted(
            (row for row in rows if not row["signs_match"]),
            key=lambda row: (
                min(abs(row["standard_delta"]), abs(row["fast_delta"])),
                row["profile_id"],
            ),
            reverse=True,
        )[:10],
        "worst_dps_errors": sorted(
            rows,
            key=lambda row: (-(row["dps_error"] or 0.0), row["profile_id"]),
        )[:10],
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))


def _profiles(coordinates) -> tuple[StressProfile, ...]:
    by_actor: dict[str, list[str]] = {}
    for actor, stat in coordinates:
        by_actor.setdefault(actor, []).append(stat)
    result: list[StressProfile] = [StressProfile("baseline", "baseline", ())]
    seen = {()}

    def add(family, profile_id, values):
        normalized = tuple(
            sorted(
                (actor, stat, round(float(delta), 9))
                for (actor, stat), delta in values.items()
                if not math.isclose(delta, 0.0, abs_tol=1e-12)
            )
        )
        if normalized in seen:
            return
        seen.add(normalized)
        result.append(
            StressProfile(
                family,
                profile_id,
                tuple(
                    ArtifactStatReplacement(actor, stat, 0.0, delta)
                    for actor, stat, delta in normalized
                ),
            )
        )

    for actor, stats in sorted(by_actor.items()):
        for stat in sorted(stats):
            for index, delta in enumerate(_axis(stat)):
                add("axis", f"axis:{actor}:{stat}:{index}", {(actor, stat): delta})

        crit_stats = set(stats) & {"cr", "cd"}
        if crit_stats == {"cr", "cd"}:
            crit_pairs = (
                (-0.30, 0.80),
                (0.30, -0.40),
                (0.70, -0.60),
                (1.00, 1.50),
                (-0.40, 2.00),
            )
            for index, (cr, cd) in enumerate(crit_pairs):
                add(
                    "crit_balance",
                    f"crit:{actor}:{index}",
                    {(actor, "cr"): cr, (actor, "cd"): cd},
                )

        scaling = [stat for stat in stats if stat in {"atk%", "hp%", "def%"}]
        bonuses = [
            stat
            for stat in stats
            if stat == "dmg%" or stat in {
                "anemo%", "cryo%", "dendro%", "electro%", "geo%",
                "hydro%", "phys%", "pyro%",
            }
        ]
        for scaling_stat in scaling:
            for bonus_stat in bonuses:
                add(
                    "main_stat_swap",
                    f"swap:{actor}:{scaling_stat}:{bonus_stat}:to_bonus",
                    {(actor, scaling_stat): -0.466, (actor, bonus_stat): 0.466},
                )
                add(
                    "main_stat_swap",
                    f"swap:{actor}:{scaling_stat}:{bonus_stat}:to_scaling",
                    {(actor, scaling_stat): 0.466, (actor, bonus_stat): -0.466},
                )
        typed_bonuses = sorted(stat for stat in bonuses if stat != "dmg%")
        for left_index, left_stat in enumerate(typed_bonuses):
            for right_stat in typed_bonuses[left_index + 1 :]:
                add(
                    "modifier_type_swap",
                    f"type-swap:{actor}:{left_stat}:{right_stat}:to_right",
                    {(actor, left_stat): -0.466, (actor, right_stat): 0.466},
                )
                add(
                    "modifier_type_swap",
                    f"type-swap:{actor}:{left_stat}:{right_stat}:to_left",
                    {(actor, left_stat): 0.466, (actor, right_stat): -0.466},
                )
        if "em" in stats:
            for other in sorted(set(scaling + bonuses)):
                add(
                    "main_stat_swap",
                    f"swap:{actor}:em:{other}:to_em",
                    {(actor, "em"): 187.0, (actor, other): -0.466},
                )
                add(
                    "main_stat_swap",
                    f"swap:{actor}:em:{other}:from_em",
                    {(actor, "em"): -187.0, (actor, other): 0.466},
                )

    rng = random.Random(20260825)
    for family, count, extreme, team_wide in (
        ("plausible_multi", 768, False, False),
        ("extreme_multi", 512, True, False),
        ("team_wide", 256, False, True),
    ):
        actors = tuple(sorted(by_actor))
        for index in range(count):
            chosen_actors = (
                rng.sample(actors, k=rng.randint(2, len(actors)))
                if team_wide
                else [rng.choice(actors)]
            )
            values = {}
            for actor in chosen_actors:
                stats = by_actor[actor]
                chosen_stats = rng.sample(
                    stats,
                    k=rng.randint(1, min(len(stats), 7 if extreme else 5)),
                )
                for stat in chosen_stats:
                    low, high = _range(stat, extreme=extreme)
                    values[(actor, stat)] = rng.uniform(low, high)
            add(family, f"{family}:{index}", values)
    return tuple(result)


def _axis(stat):
    if stat == "cr":
        return (-0.4, -0.2, 0.2, 0.5, 1.0)
    if stat == "cd":
        return (-0.8, -0.4, 0.5, 1.0, 2.0)
    if stat == "em":
        return (-150.0, 187.0, 400.0, 800.0, 1200.0)
    if stat == "atk":
        return (-400.0, 300.0, 600.0, 1000.0)
    if stat == "hp":
        return (-5000.0, 5000.0, 10000.0, 20000.0)
    if stat == "def":
        return (-400.0, 300.0, 600.0, 1000.0)
    return (-0.6, -0.3, 0.3, 0.6, 1.2)


def _range(stat, *, extreme):
    if stat == "cr":
        return (-0.45, 1.1) if extreme else (-0.25, 0.35)
    if stat == "cd":
        return (-0.9, 2.2) if extreme else (-0.5, 0.8)
    if stat == "em":
        return (-200.0, 1400.0) if extreme else (-120.0, 500.0)
    if stat == "atk":
        return (-600.0, 1500.0) if extreme else (-350.0, 700.0)
    if stat == "hp":
        return (-8000.0, 25000.0) if extreme else (-5000.0, 10000.0)
    if stat == "def":
        return (-600.0, 1500.0) if extreme else (-350.0, 700.0)
    return (-0.8, 1.5) if extreme else (-0.466, 0.70)


def _family_summary(rows, duration_frames):
    errors = sorted(row["dps_error"] or 0.0 for row in rows)
    relative = sorted(row["relative_damage_error"] for row in rows)
    return {
        "count": len(rows),
        "sign_agreement": sum(row["signs_match"] for row in rows) / len(rows),
        "mean_dps_error": sum(errors) / len(errors),
        "p95_dps_error": _quantile(errors, 0.95),
        "p99_dps_error": _quantile(errors, 0.99),
        "max_dps_error": max(errors),
        "p95_relative_damage_error": _quantile(relative, 0.95),
        "max_relative_damage_error": max(relative),
    }


def _top_recall(standard, fast, limit):
    standard_ids = {row["profile_id"] for row in standard[:limit]}
    fast_ids = {row["profile_id"] for row in fast[:limit]}
    return len(standard_ids & fast_ids) / limit


def _spearman(pairs):
    count = len(pairs)
    squared = sum((left - right) ** 2 for left, right in pairs)
    return 1.0 - 6.0 * squared / (count * (count * count - 1))


def _quantile(values, quantile):
    position = (len(values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def _sign(value):
    if math.isclose(value, 0.0, rel_tol=1e-12, abs_tol=1e-8):
        return 0
    return 1 if value > 0.0 else -1


def _load_trace():
    context = load_active_gcsim_optimizer_engine_context(store_dir=STORE)
    engine_root = Path(context.engine_root)
    engine_manifest = load_engine_manifest(engine_root)
    manifest_body = decode_source_manifest_body(
        (engine_root / "build" / "gtt-source-manifest-body.json").read_text(
            encoding="utf-8"
        )
    )
    binding = SourceManifestBinding.from_engine_manifest(
        manifest_body=manifest_body,
        engine_manifest=engine_manifest,
        engine_binding_sha256=context.binding_sha256,
    )
    raw = json.loads(TRACE_PATH.read_text(encoding="utf-8"))
    request = TraceExtractionRequest(
        context_sha256=raw["context_sha256"],
        source_config_sha256=raw["source_config_sha256"],
        compiled_action_sha256=raw["compiled_action_sha256"],
        target_sha256=raw["target_sha256"],
        engine_artifact_sha256=context.artifact_sha256,
        engine_binding_sha256=context.binding_sha256,
        formula_version=raw["formula_version"],
        formula_sha256=raw["formula_sha256"],
        seed=int(raw["seed"]),
        objective=TraceObjective.TEAM_DPS,
        character_keys=tuple(raw["character_keys"]),
        required_capabilities=("gtt_trace_equation_v6",),
    )
    return decode_engine_trace_v6(
        canonical_json(raw), request=request, source_manifest_binding=binding
    )


if __name__ == "__main__":
    main()
