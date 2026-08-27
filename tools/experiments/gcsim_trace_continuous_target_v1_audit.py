"""Offline real-context audit for isolated continuous_target_v1.

The script reads the accepted saved trace and current equipped artifact rows.
It never launches GCSIM, changes equipment, imports UI, or writes account data.
"""

from __future__ import annotations

from decimal import Decimal
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
from run_workspace.gcsim.optimizer_trace_search import (
    ContinuousMainStatLane,
    ContinuousTargetConfig,
    MainStatSelection,
    solve_continuous_target,
)
from run_workspace.gcsim.optimizer_trace_selected_candidates import (
    load_selected_equipped_team_snapshot,
)
from run_workspace.gcsim.trace_equation import (
    ArtifactStatValue,
    ArtifactStatVector,
    SourceManifestBinding,
    TraceExtractionRequest,
    TraceObjective,
    canonical_json,
    compile_artifact_variable_objective,
    compile_rotation_formula_filters,
    decode_engine_trace_v6,
    decode_source_manifest_body,
)


ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / ".codex_tmp" / "forwarded_attack_v1_store"
TRACE_PATH = ROOT / ".codex_tmp" / "forwarded_attack_v1_run" / "trace.json"
DATABASE_PATH = ROOT / "data" / "artifacts.db"


def main() -> None:
    started = perf_counter()
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
    trace = decode_engine_trace_v6(
        canonical_json(raw),
        request=request,
        source_manifest_binding=binding,
    )
    filters = compile_rotation_formula_filters(trace)
    decoded_at = perf_counter()

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

    incumbent_totals: dict[tuple[str, str], Decimal] = {}
    main_selections: list[MainStatSelection] = []
    for selected in snapshot.wearers:
        actor = selected.wearer.gcsim_character_key
        for slot, artifact_id in selected.assignment.artifact_ids_by_slot.items():
            artifact = database.artifact_by_id(artifact_id)
            if artifact is None:
                raise RuntimeError(f"equipped artifact {artifact_id} is missing")
            materialized = materialize_gcsim_optimizer_artifact_stat_vector(
                artifact,
                wearer=selected.wearer,
            )
            if not materialized.ready or materialized.stat_vector is None:
                raise RuntimeError(f"artifact {artifact_id} did not materialize")
            main_rows = tuple(
                row
                for row in materialized.stat_vector.contributions
                if row.source_kind == "main"
            )
            if len(main_rows) != 1:
                raise RuntimeError(f"artifact {artifact_id} has invalid main stat")
            main_selections.append(
                MainStatSelection(actor, slot, main_rows[0].gcsim_key)
            )
            for stat_key, value in materialized.stat_vector.normalized_stats:
                coordinate = (actor, stat_key)
                incumbent_totals[coordinate] = (
                    incumbent_totals.get(coordinate, Decimal(0)) + Decimal(value)
                )

    incumbent = ArtifactStatVector.build(
        tuple(
            ArtifactStatValue(actor, stat, float(value))
            for (actor, stat), value in incumbent_totals.items()
            if value > 0
        )
    )
    objective = compile_artifact_variable_objective(filters.fast, incumbent)
    lane = ContinuousMainStatLane.build(
        "current-selected-main-stats",
        tuple(main_selections),
    )
    prepared_at = perf_counter()
    result = solve_continuous_target(
        objective,
        lane,
        ContinuousTargetConfig(roll_units_per_wearer=38.25),
    )
    finished = perf_counter()

    output = {
        "diagnostic_only": True,
        "engine_calls": 0,
        "trace_decode_and_fast_compile_seconds": decoded_at - started,
        "database_snapshot_and_objective_seconds": prepared_at - decoded_at,
        "continuous_target_seconds": finished - prepared_at,
        "total_seconds": finished - started,
        "character_keys": list(objective.character_keys),
        "fast_channel_count": filters.fast.coarse_channel_count,
        "requested_roll_units": result.requested_roll_units,
        "requested_roll_units_per_wearer": (
            result.requested_roll_units_per_wearer
        ),
        "spent_roll_units": result.spent_roll_units,
        "unspent_roll_units": result.unspent_roll_units,
        "evaluation_count": result.evaluation_count,
        "exchange_iterations": result.exchange_iterations,
        "stop_reason": result.stop_reason,
        "baseline_damage": objective.baseline_damage,
        "target_damage": result.target_score.candidate_damage,
        "target_delta": result.target_score.expected_delta,
        "authoritative": result.authoritative,
        "prune_authority": result.prune_authority,
        "allocations": [
            {
                "actor": row.actor_key,
                "stat": row.stat_key,
                "roll_units": row.roll_units,
                "stat_value": row.stat_value,
            }
            for row in result.allocations
        ],
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
