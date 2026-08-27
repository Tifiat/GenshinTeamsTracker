from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from run_workspace.gcsim.engine_store import load_engine_manifest
from run_workspace.gcsim.optimizer_artifact_database import (
    load_gcsim_optimizer_artifact_database_input,
)
from run_workspace.gcsim.optimizer_engine_context import (
    load_active_gcsim_optimizer_engine_context,
)
from run_workspace.gcsim.optimizer_trace_selected_candidates import (
    build_selected_single_swap_corpus,
    load_selected_equipped_team_snapshot,
)
from run_workspace.gcsim.trace_equation import (
    CompactTermKind,
    SourceManifestBinding,
    TraceExtractionRequest,
    TraceObjective,
    canonical_json,
    compile_rotation_objective,
    decode_engine_trace_v6,
    decode_source_manifest_body,
    evaluate_rotation_objective,
    score_observed_artifact_replacement,
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
    decoded_at = perf_counter()

    objective = compile_rotation_objective(trace)
    compiled_at = perf_counter()

    loaded = load_gcsim_optimizer_artifact_database_input(
        DATABASE_PATH,
        engine_context=context,
    )
    if not loaded.ready or loaded.database_input is None:
        raise RuntimeError(
            "artifact database input not ready: "
            + ",".join(issue.code for issue in loaded.issues)
        )
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
    corpus_at = perf_counter()

    compact_scores = tuple(
        (candidate, evaluate_rotation_objective(objective, candidate.replacements))
        for candidate in corpus.candidates
    )
    evaluated_at = perf_counter()

    parity_candidates = _parity_candidates(corpus.candidates)
    parity_rows = []
    for candidate in parity_candidates:
        compact = evaluate_rotation_objective(objective, candidate.replacements)
        detailed = score_observed_artifact_replacement(trace, candidate.replacements)
        assert detailed.ranking.candidate_score is not None
        parity_rows.append(
            {
                "candidate_input_sha256": candidate.candidate_input_sha256,
                "wearer": candidate.changed_wearer_key,
                "slot": candidate.changed_slot,
                "absolute_error": abs(
                    compact.candidate_damage - detailed.ranking.candidate_score
                ),
            }
        )
    finished = perf_counter()

    top = sorted(
        compact_scores,
        key=lambda row: (-row[1].candidate_damage, row[0].candidate_input_sha256),
    )[:10]
    output = {
        "engine_calls": 0,
        "diagnostic_only": True,
        "trace_decode_seconds": decoded_at - started,
        "objective_compile_seconds": compiled_at - decoded_at,
        "database_snapshot_corpus_seconds": corpus_at - compiled_at,
        "all_candidate_evaluation_seconds": evaluated_at - corpus_at,
        "parity_sample_seconds": finished - evaluated_at,
        "total_seconds": finished - started,
        "source_hit_count": objective.source_hit_count,
        "compact_group_count": objective.group_count,
        "compression_ratio": objective.compression_ratio,
        "groups_by_kind": {
            kind.value: sum(1 for row in objective.groups if row.kind is kind)
            for kind in CompactTermKind
        },
        "groups_by_actor": {
            actor: sum(1 for row in objective.groups if row.actor_key == actor)
            for actor in objective.character_keys
        },
        "relevant_coordinates": [
            {"actor_key": actor, "stat_key": stat}
            for actor, stat in objective.relevant_coordinates
        ],
        "compilation_preserves_baseline": objective.compilation_preserves_baseline,
        "baseline_absolute_error": abs(
            objective.baseline_damage - objective.detailed_baseline_damage
        ),
        "physical_single_swap_candidate_count": (
            corpus.enumerated_physical_candidate_count
        ),
        "stat_candidate_count": corpus.stat_candidate_count,
        "evaluated_candidate_count": len(compact_scores),
        "candidate_evaluations_per_second": (
            len(compact_scores) / max(evaluated_at - corpus_at, 1e-12)
        ),
        "parity_sample_count": len(parity_rows),
        "parity_max_absolute_error": max(
            (row["absolute_error"] for row in parity_rows),
            default=0.0,
        ),
        "parity_rows": parity_rows,
        "top_candidates": [
            {
                "candidate_input_sha256": candidate.candidate_input_sha256,
                "wearer": candidate.changed_wearer_key,
                "slot": candidate.changed_slot,
                "estimated_delta": score.expected_delta,
                "fallback_hit_count": score.fallback_hit_count,
            }
            for candidate, score in top
        ],
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))


def _parity_candidates(candidates):
    incumbent = next(row for row in candidates if row.is_incumbent)
    selected = [incumbent]
    selected_ids = {incumbent.candidate_input_sha256}
    for actor in ("chasca", "ororon", "furina", "bennett"):
        candidate = next(
            row
            for row in candidates
            if row.changed_wearer_key == actor
            and row.candidate_input_sha256 not in selected_ids
        )
        selected.append(candidate)
        selected_ids.add(candidate.candidate_input_sha256)
    for actor, stat in (("furina", "hp%"), ("chasca", "cr"), ("ororon", "em")):
        candidate = next(
            (
                row
                for row in candidates
                if row.changed_wearer_key == actor
                and any(
                    replacement.actor_key == actor
                    and replacement.stat_key == stat
                    and replacement.delta != 0.0
                    for replacement in row.replacements
                )
                and row.candidate_input_sha256 not in selected_ids
            ),
            None,
        )
        if candidate is not None:
            selected.append(candidate)
            selected_ids.add(candidate.candidate_input_sha256)
    return tuple(selected)


if __name__ == "__main__":
    main()
