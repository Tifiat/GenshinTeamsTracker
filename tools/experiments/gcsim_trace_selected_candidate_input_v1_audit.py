"""Offline real-DB audit for the first Selected trace candidate slice."""

from __future__ import annotations

import argparse
from dataclasses import replace
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
    score_selected_candidate_corpus,
)
from run_workspace.gcsim.trace_equation import (
    SourceManifestBinding,
    TraceExtractionRequest,
    TraceObjective,
    UncertaintyShortlistPolicy,
    canonical_json,
    canonical_sha256,
    compile_candidate_dependency_index,
    decode_engine_trace_v6,
    decode_source_manifest_body,
)


ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / ".codex_tmp" / "forwarded_attack_v1_store"
TRACE_PATH = ROOT / ".codex_tmp" / "forwarded_attack_v1_run" / "trace.json"
DATABASE_PATH = ROOT / "data" / "artifacts.db"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-score-candidates", type=int, default=0)
    args = parser.parse_args()
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
    full_physical_count = corpus.enumerated_physical_candidate_count
    full_stat_count = corpus.stat_candidate_count
    if args.max_score_candidates > 0:
        chosen = corpus.candidates[: args.max_score_candidates]
        corpus = replace(
            corpus,
            enumerated_physical_candidate_count=sum(
                row.equivalent_physical_assignment_count for row in chosen
            ),
            candidates=chosen,
        )
    corpus_at = perf_counter()

    dependency_index = compile_candidate_dependency_index(trace)
    dependency_index_at = perf_counter()
    scored = score_selected_candidate_corpus(
        trace,
        corpus,
        policy=UncertaintyShortlistPolicy(
            finalist_limit=16,
            numeric_leader_limit=8,
            reachable_representative_limit=4,
            unresolved_representative_limit=4,
        ),
        fidelity_sha256=canonical_sha256(
            {"kind": "diagnostic-only-selected-v1-fidelity"}
        ),
        seed_panel_sha256=canonical_sha256(
            {"kind": "diagnostic-only-selected-v1-seed-panel"}
        ),
        dependency_index=dependency_index,
    )
    finished = perf_counter()

    candidate_by_score = {
        row.score.candidate_sha256: row for row in scored.scored_candidates
    }
    top_rows = sorted(
        scored.scored_candidates,
        key=lambda row: (-row.score.candidate_estimate, row.score.candidate_sha256),
    )[:10]
    incumbent_score = next(
        row.score.observed_score
        for row in scored.scored_candidates
        if row.candidate_input.is_incumbent
    )
    output = {
        "engine_calls": 0,
        "diagnostic_only": True,
        "trace_decode_seconds": decoded_at - started,
        "database_snapshot_corpus_seconds": corpus_at - decoded_at,
        "score_and_plan_seconds": finished - corpus_at,
        "dependency_index_seconds": dependency_index_at - corpus_at,
        "candidate_ranking_and_plan_seconds": finished - dependency_index_at,
        "total_seconds": finished - started,
        "artifact_row_count": len(database.artifacts),
        "equipped_set_schemes": [
            {
                "wearer": row.wearer.gcsim_character_key,
                "target_set_uid": row.target_set_uid,
                "target_set_count": row.target_set_count,
                "set_counts": dict(row.set_counts),
            }
            for row in snapshot.wearers
        ],
        "physical_single_swap_candidate_count": full_physical_count,
        "stat_equivalent_candidate_count": full_stat_count,
        "scored_candidate_count": corpus.stat_candidate_count,
        "dependency_slice_count": scored.dependency_slice_count,
        "baseline_hit_count": len(incumbent_score.ranking.hits),
        "baseline_formula_group_count": len(incumbent_score.groups),
        "baseline_formula_groups_by_actor": {
            actor: sum(
                1 for group in incumbent_score.groups if group.actor_key == actor
            )
            for actor in trace.terminal_trace.request.character_keys
        },
        "shortlist_request_count": scored.shortlist_plan.selected_candidate_count,
        "shortlist_plan_sha256": scored.shortlist_plan.plan_sha256,
        "top_candidates": [
            {
                "candidate_input_sha256": row.candidate_input.candidate_input_sha256,
                "score_candidate_sha256": row.score.candidate_sha256,
                "estimated_delta": row.score.estimated_delta,
                "changed_wearer_key": row.candidate_input.changed_wearer_key,
                "changed_slot": row.candidate_input.changed_slot,
                "is_incumbent": row.candidate_input.is_incumbent,
                "equivalent_physical_assignment_count": (
                    row.candidate_input.equivalent_physical_assignment_count
                ),
            }
            for row in top_rows
        ],
        "shortlist": [
            {
                "candidate_input_sha256": (
                    candidate_by_score[row.candidate_sha256]
                    .candidate_input.candidate_input_sha256
                ),
                "score_candidate_sha256": row.candidate_sha256,
                "reasons": [reason.value for reason in row.reasons],
            }
            for row in scored.shortlist_plan.requests
        ],
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
