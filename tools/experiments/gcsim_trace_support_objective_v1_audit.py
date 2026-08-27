"""Real saved-trace audit for the isolated support-aware control objective.

This reads one already captured trace plus the equipped artifact rows.  It
does not launch GCSIM, modify equipment, import UI, or write account data.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import combinations
import json
from pathlib import Path
from time import perf_counter

from run_workspace.gcsim.engine_store import load_engine_manifest
from run_workspace.gcsim.optimizer_artifact_database import (
    load_gcsim_optimizer_artifact_database_input,
)
from run_workspace.gcsim.optimizer_artifact_materializer import (
    materialize_gcsim_optimizer_artifact_stat_vector,
)
from run_workspace.gcsim.optimizer_engine_context import (
    load_active_gcsim_optimizer_engine_context,
)
from run_workspace.gcsim.optimizer_trace_selected_candidates import (
    build_selected_single_swap_corpus,
    load_selected_equipped_team_snapshot,
)
from run_workspace.gcsim.trace_equation import (
    ArtifactStatValue,
    ArtifactStatVector,
    SourceManifestBinding,
    TraceExtractionRequest,
    TraceObjective,
    artifact_replacements_between,
    build_support_projection_cache,
    canonical_json,
    compile_support_aware_control_objective,
    compile_support_aware_fast_objective_from_control,
    decode_engine_trace_v6,
    decode_source_manifest_body,
    evaluate_rotation_objective,
    evaluate_support_aware_control_objective,
    evaluate_support_aware_fast_objective,
    evaluate_support_aware_sliced_control_objective,
)


ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / ".codex_tmp" / "support_replay_0021_fresh_absolute"
TRACE_PATH = (
    ROOT
    / ".codex_tmp"
    / "same_context_trace_diagnostic_20260826_hit_binding_v11"
    / "trace.json"
)
DATABASE_PATH = ROOT / "data" / "artifacts.db"


def main() -> None:
    started = perf_counter()
    trace = _load_trace()
    incumbent, corpus = _load_incumbent_and_corpus(trace)
    prepared_at = perf_counter()
    objective = compile_support_aware_control_objective(trace, incumbent)
    compiled_at = perf_counter()
    fast_objective = compile_support_aware_fast_objective_from_control(objective)
    fast_compiled_at = perf_counter()
    support_cache = build_support_projection_cache(fast_objective)

    incumbent_values = {
        (row.actor_key, row.stat_key): row.value for row in incumbent.values
    }
    candidate_coordinate = ("bennett", "hp%")
    observed_hp_percent = incumbent_values.get(candidate_coordinate, 0.0)
    if observed_hp_percent < 0.20:
        raise RuntimeError(
            "real audit requires at least 0.20 Bennett artifact hp%"
        )
    incumbent_values[candidate_coordinate] = observed_hp_percent - 0.20
    candidate = ArtifactStatVector.build(
        tuple(
            ArtifactStatValue(actor, stat, value)
            for (actor, stat), value in incumbent_values.items()
            if value > 0.0
        )
    )
    replacements = artifact_replacements_between(incumbent, candidate)
    direct_only = evaluate_rotation_objective(objective.standard, replacements)
    direct_done_at = perf_counter()
    support_aware = evaluate_support_aware_control_objective(objective, candidate)
    full_done_at = perf_counter()
    sliced = evaluate_support_aware_sliced_control_objective(objective, candidate)
    sliced_done_at = perf_counter()
    support_fast_first = evaluate_support_aware_fast_objective(
        fast_objective,
        candidate,
        cache=support_cache,
    )
    fast_miss_done_at = perf_counter()
    support_fast_cached = evaluate_support_aware_fast_objective(
        fast_objective,
        candidate,
        cache=support_cache,
    )
    fast_cached_done_at = perf_counter()
    matrix_started_at = perf_counter()
    matrix_errors: list[float] = []
    matrix_mismatches: list[str] = []
    for actor, stat in fast_objective.support_coordinates:
        values = {
            (row.actor_key, row.stat_key): row.value for row in incumbent.values
        }
        step = 100.0 if stat in {"atk", "hp", "def", "em"} else 0.05
        values[(actor, stat)] = values.get((actor, stat), 0.0) + step
        matrix_candidate = ArtifactStatVector.build(
            tuple(
                ArtifactStatValue(key_actor, key_stat, value)
                for (key_actor, key_stat), value in values.items()
                if value > 0.0
            )
        )
        matrix_control = evaluate_support_aware_control_objective(
            objective,
            matrix_candidate,
        )
        matrix_replacements = artifact_replacements_between(
            incumbent,
            matrix_candidate,
        )
        matrix_direct_standard = evaluate_rotation_objective(
            objective.standard,
            matrix_replacements,
        )
        matrix_fast = evaluate_support_aware_fast_objective(
            fast_objective,
            matrix_candidate,
            cache=support_cache,
        )
        control_support_correction = (
            matrix_control.candidate_damage
            - matrix_direct_standard.candidate_damage
        )
        error = (
            matrix_fast.support_correction_damage
            - control_support_correction
        )
        matrix_errors.append(error)
        if abs(error) > 1e-7:
            matrix_mismatches.append(f"{actor}:{stat}:{error}")
    corpus_started_at = perf_counter()
    corpus_cache = build_support_projection_cache(fast_objective)
    incumbent_map = {
        (row.actor_key, row.stat_key): row.value for row in incumbent.values
    }
    for row in corpus.candidates:
        values = dict(incumbent_map)
        for replacement in row.replacements:
            key = (replacement.actor_key, replacement.stat_key)
            values[key] = values.get(key, 0.0) + replacement.delta
            if abs(values[key]) <= 1e-12:
                values.pop(key)
            elif values[key] < 0.0:
                raise RuntimeError(
                    f"candidate {row.candidate_input_sha256} has negative {key}"
                )
        corpus_candidate = ArtifactStatVector.build(
            tuple(
                ArtifactStatValue(actor, stat, value)
                for (actor, stat), value in values.items()
                if value > 0.0
            )
        )
        evaluate_support_aware_fast_objective(
            fast_objective,
            corpus_candidate,
            cache=corpus_cache,
        )
    boundary_started_at = perf_counter()
    support_coordinate_set = set(fast_objective.support_coordinates)
    bounds = {
        coordinate: [0.0, 0.0]
        for coordinate in fast_objective.support_coordinates
    }
    for row in corpus.candidates:
        replacement_map = {
            (replacement.actor_key, replacement.stat_key): replacement.delta
            for replacement in row.replacements
        }
        for coordinate in support_coordinate_set:
            value = replacement_map.get(coordinate, 0.0)
            bounds[coordinate][0] = min(bounds[coordinate][0], value)
            bounds[coordinate][1] = max(bounds[coordinate][1], value)
    boundary_profiles: list[tuple[str, dict[tuple[str, str], float]]] = []
    for coordinate, (lower, upper) in sorted(bounds.items()):
        if lower != 0.0:
            boundary_profiles.append((f"min:{coordinate}", {coordinate: lower}))
        if upper != 0.0:
            boundary_profiles.append((f"max:{coordinate}", {coordinate: upper}))
    lower_profile = {
        coordinate: values[0]
        for coordinate, values in bounds.items()
        if values[0] != 0.0
    }
    upper_profile = {
        coordinate: values[1]
        for coordinate, values in bounds.items()
        if values[1] != 0.0
    }
    if lower_profile:
        boundary_profiles.append(("all-min", lower_profile))
    if upper_profile:
        boundary_profiles.append(("all-max", upper_profile))
    for left, right in combinations(sorted(support_coordinate_set), 2):
        pair = {}
        if bounds[left][1] != 0.0:
            pair[left] = bounds[left][1]
        if bounds[right][1] != 0.0:
            pair[right] = bounds[right][1]
        if len(pair) == 2:
            boundary_profiles.append((f"pair-max:{left}:{right}", pair))

    boundary_errors: list[float] = []
    boundary_mismatches: list[str] = []
    boundary_cache = build_support_projection_cache(fast_objective)
    for label, delta_map in boundary_profiles:
        values = dict(incumbent_map)
        for coordinate, delta in delta_map.items():
            values[coordinate] = values.get(coordinate, 0.0) + delta
            if values[coordinate] < -1e-12:
                raise RuntimeError(f"boundary profile {label} is negative")
            if abs(values[coordinate]) <= 1e-12:
                values.pop(coordinate, None)
        boundary_candidate = ArtifactStatVector.build(
            tuple(
                ArtifactStatValue(actor, stat, value)
                for (actor, stat), value in values.items()
                if value > 0.0
            )
        )
        boundary_replacements = artifact_replacements_between(
            incumbent,
            boundary_candidate,
        )
        boundary_direct = evaluate_rotation_objective(
            objective.standard,
            boundary_replacements,
        )
        boundary_control = evaluate_support_aware_control_objective(
            objective,
            boundary_candidate,
        )
        boundary_fast = evaluate_support_aware_fast_objective(
            fast_objective,
            boundary_candidate,
            cache=boundary_cache,
        )
        control_correction = (
            boundary_control.candidate_damage
            - boundary_direct.candidate_damage
        )
        error = boundary_fast.support_correction_damage - control_correction
        boundary_errors.append(error)
        if abs(error) > 1e-7:
            boundary_mismatches.append(f"{label}:{error}")
    finished = perf_counter()
    slice_damage_matches = abs(
        sliced.candidate_damage - support_aware.candidate_damage
    ) <= 1e-7
    slice_projection_matches = (
        sliced.support_changed_hit_count == support_aware.support_changed_hit_count
        and sliced.candidate_damage_by_actor
        == support_aware.candidate_damage_by_actor
    )
    full_uncertainties = set(support_aware.uncertainty_codes)
    sliced_uncertainties = set(sliced.uncertainty_codes)

    direct_by_actor = dict(direct_only.candidate_damage_by_actor)
    support_by_actor = dict(support_aware.candidate_damage_by_actor)
    output = {
        "diagnostic_only": True,
        "authoritative": support_aware.authoritative,
        "hard_prune_allowed": support_aware.hard_prune_allowed,
        "engine_calls": support_aware.engine_call_count,
        "trace_evidence_sha256": trace.evidence_sha256,
        "objective_sha256": objective.objective_sha256,
        "candidate_delta": {
            "actor": candidate_coordinate[0],
            "stat": candidate_coordinate[1],
            "value": -0.20,
        },
        "baseline_damage": objective.baseline_damage,
        "baseline_dps": support_aware.baseline_dps,
        "direct_only_damage": direct_only.candidate_damage,
        "direct_only_delta": direct_only.expected_delta,
        "support_aware_damage": support_aware.candidate_damage,
        "support_aware_delta": support_aware.expected_delta,
        "support_only_delta_beyond_direct": (
            support_aware.candidate_damage - direct_only.candidate_damage
        ),
        "support_changed_hit_count": support_aware.support_changed_hit_count,
        "support_fast": {
            "candidate_damage": support_fast_first.candidate_damage,
            "control_damage_delta": (
                support_fast_first.candidate_damage
                - support_aware.candidate_damage
            ),
            "support_correction_damage": (
                support_fast_first.support_correction_damage
            ),
            "changed_hit_count": support_fast_first.support_changed_hit_count,
            "first_cache_hit": support_fast_first.support_cache_hit,
            "second_cache_hit": support_fast_cached.support_cache_hit,
            "cache_entry_count": support_fast_cached.support_cache_entry_count,
            "support_coordinate_count": len(
                fast_objective.support_coordinates
            ),
            "single_coordinate_matrix_mismatches": matrix_mismatches,
            "single_coordinate_matrix_max_abs_error": max(
                (abs(value) for value in matrix_errors),
                default=0.0,
            ),
            "real_single_swap_corpus": {
                "stat_candidate_count": corpus.stat_candidate_count,
                "physical_candidate_count": (
                    corpus.enumerated_physical_candidate_count
                ),
                "cache_entries": len(corpus_cache.entries),
                "cache_hits": corpus_cache.hit_count,
                "cache_misses": corpus_cache.miss_count,
            },
            "support_boundary_matrix": {
                "profile_count": len(boundary_profiles),
                "mismatches": boundary_mismatches,
                "max_abs_error": max(
                    (abs(value) for value in boundary_errors),
                    default=0.0,
                ),
                "cache_entries": len(boundary_cache.entries),
            },
        },
        "slice_parity": {
            "exact_score_object": sliced == support_aware,
            "damage_matches": slice_damage_matches,
            "projection_matches": slice_projection_matches,
            "candidate_damage_delta": (
                sliced.candidate_damage - support_aware.candidate_damage
            ),
            "changed_hit_count": sliced.support_changed_hit_count,
            "full_replayed_event_count": (
                support_aware.support_replayed_event_count
            ),
            "sliced_replayed_event_count": sliced.support_replayed_event_count,
            "uncertainties_missing_from_slice": len(
                full_uncertainties - sliced_uncertainties
            ),
            "uncertainties_extra_in_slice": len(
                sliced_uncertainties - full_uncertainties
            ),
        },
        "fallback_group_count": support_aware.fallback_group_count,
        "fallback_hit_count": support_aware.fallback_hit_count,
        "uncertainty_count": len(support_aware.uncertainty_codes),
        "actor_damage_delta_beyond_direct": {
            actor: support_by_actor.get(actor, 0.0) - direct_by_actor.get(actor, 0.0)
            for actor in objective.character_keys
        },
        "timing_seconds": {
            "load_trace_and_artifacts": prepared_at - started,
            "compile_control": compiled_at - prepared_at,
            "compile_support_fast": fast_compiled_at - compiled_at,
            "direct_only_evaluate": direct_done_at - fast_compiled_at,
            "support_aware_evaluate": fast_cached_done_at - direct_done_at,
            "full_support_evaluate": full_done_at - direct_done_at,
            "sliced_support_evaluate": sliced_done_at - full_done_at,
            "support_fast_cache_miss_evaluate": (
                fast_miss_done_at - sliced_done_at
            ),
            "support_fast_cache_hit_evaluate": (
                fast_cached_done_at - fast_miss_done_at
            ),
            "support_coordinate_matrix": corpus_started_at - matrix_started_at,
            "real_single_swap_corpus": boundary_started_at - corpus_started_at,
            "support_boundary_matrix": finished - boundary_started_at,
            "total": finished - started,
        },
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))


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
        canonical_json(raw),
        request=request,
        source_manifest_binding=binding,
    )


def _load_incumbent_and_corpus(trace):
    context = load_active_gcsim_optimizer_engine_context(store_dir=STORE)
    loaded = load_gcsim_optimizer_artifact_database_input(
        DATABASE_PATH,
        engine_context=context,
    )
    if not loaded.ready or loaded.database_input is None:
        raise RuntimeError("artifact database input not ready")
    database = loaded.database_input
    snapshot = load_selected_equipped_team_snapshot(
        DATABASE_PATH,
        artifact_database=database,
        character_keys=trace.terminal_trace.request.character_keys,
    )
    corpus = build_selected_single_swap_corpus(
        database,
        snapshot=snapshot,
        candidate_limit=4096,
    )
    totals: dict[tuple[str, str], Decimal] = {}
    for selected in snapshot.wearers:
        actor = selected.wearer.gcsim_character_key
        for artifact_id in selected.assignment.artifact_ids_by_slot.values():
            artifact = database.artifact_by_id(artifact_id)
            if artifact is None:
                raise RuntimeError(f"equipped artifact {artifact_id} is missing")
            materialized = materialize_gcsim_optimizer_artifact_stat_vector(
                artifact,
                wearer=selected.wearer,
            )
            if not materialized.ready or materialized.stat_vector is None:
                raise RuntimeError(f"artifact {artifact_id} did not materialize")
            for stat_key, value in materialized.stat_vector.normalized_stats:
                key = (actor, stat_key)
                totals[key] = totals.get(key, Decimal(0)) + Decimal(value)
    incumbent = ArtifactStatVector.build(
        tuple(
            ArtifactStatValue(actor, stat, float(value))
            for (actor, stat), value in totals.items()
            if value > 0
        )
    )
    return incumbent, corpus


if __name__ == "__main__":
    main()
