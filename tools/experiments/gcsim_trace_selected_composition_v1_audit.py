"""Reduced real complete-assignment audit for the isolated Selected scorer.

The experiment reuses one saved exact-context trace and the current read-only
artifact database.  It builds a deliberately small binary physical domain from
legal single-swap alternatives, exhausts that domain only as a development
oracle, and never launches GCSIM or grants pruning/product authority.
"""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from run_workspace.gcsim.optimizer_artifact_database import (
    load_gcsim_optimizer_artifact_database_input,
)
from run_workspace.gcsim.optimizer_engine_context import (
    load_active_gcsim_optimizer_engine_context,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GcsimOptimizerWearerArtifactAssignment,
)
from run_workspace.gcsim.optimizer_trace_search import (
    build_selected_complete_assignment,
    compile_selected_composition_scoring_session,
    score_selected_complete_assignments,
)
from run_workspace.gcsim.trace_equation import (
    TraceContractError,
    compile_support_aware_fast_objective,
)
from tools.experiments.gcsim_trace_support_objective_v1_audit import (
    DATABASE_PATH,
    STORE,
    _load_incumbent_and_corpus,
    _load_trace,
)


ROOT = Path(__file__).resolve().parents[2]
MAX_VARIABLE_SLOTS = 8
MAX_COMPLETE_CANDIDATES = 1 << MAX_VARIABLE_SLOTS


def main() -> None:
    started = perf_counter()
    trace = _load_trace()
    incumbent_vector, single_swap_corpus = _load_incumbent_and_corpus(trace)
    context = load_active_gcsim_optimizer_engine_context(store_dir=STORE)
    loaded = load_gcsim_optimizer_artifact_database_input(
        DATABASE_PATH,
        engine_context=context,
    )
    if not loaded.ready or loaded.database_input is None:
        raise RuntimeError("artifact database input not ready")
    database = loaded.database_input
    snapshot = single_swap_corpus.snapshot
    prepared_at = perf_counter()

    objective = compile_support_aware_fast_objective(trace, incumbent_vector)
    session = compile_selected_composition_scoring_session(
        database,
        snapshot=snapshot,
        objective=objective,
    )
    compiled_at = perf_counter()

    support_coordinates = set(objective.support_coordinates)
    alternatives: dict[tuple[int, str], tuple[bool, int, str]] = {}
    for row in single_swap_corpus.candidates:
        if row.is_incumbent:
            continue
        wearer_index = next(
            index
            for index, selected in enumerate(snapshot.wearers)
            if selected.wearer.gcsim_character_key == row.changed_wearer_key
        )
        artifact_id = row.representative_assignments[
            wearer_index
        ].artifact_ids_by_slot[row.changed_slot]
        key = (wearer_index, row.changed_slot)
        touches_support = any(
            (replacement.actor_key, replacement.stat_key) in support_coordinates
            and replacement.baseline_artifact_value
            != replacement.candidate_artifact_value
            for replacement in row.replacements
        )
        choice = (touches_support, artifact_id, row.physical_assignment_sha256)
        current = alternatives.get(key)
        if current is None or (
            (not current[0] and choice[0])
            or (current[0] == choice[0] and choice[2] < current[2])
        ):
            alternatives[key] = choice
    selected_alternatives = tuple(
        sorted(
            alternatives.items(),
            key=lambda row: (not row[1][0], row[0], row[1][2]),
        )[:MAX_VARIABLE_SLOTS]
    )
    if not selected_alternatives:
        raise RuntimeError("reduced complete-assignment audit has no alternatives")

    incumbent_assignments = tuple(row.assignment for row in snapshot.wearers)
    candidates_by_id = {}
    rejected_invalid = 0
    for mask in range(1 << len(selected_alternatives)):
        slot_maps = [dict(row.artifact_ids_by_slot) for row in incumbent_assignments]
        for bit, (
            (wearer_index, slot),
            (_touches_support, artifact_id, _identity),
        ) in enumerate(selected_alternatives):
            if mask & (1 << bit):
                slot_maps[wearer_index][slot] = artifact_id
        assignments = tuple(
            GcsimOptimizerWearerArtifactAssignment(
                wearer=incumbent.wearer,
                artifact_ids_by_slot=slot_maps[index],
            )
            for index, incumbent in enumerate(incumbent_assignments)
        )
        try:
            candidate = build_selected_complete_assignment(
                database,
                snapshot=snapshot,
                assignments=assignments,
            )
        except TraceContractError:
            rejected_invalid += 1
            continue
        candidates_by_id[candidate.physical_assignment_sha256] = candidate
    candidates = tuple(
        candidates_by_id[key] for key in sorted(candidates_by_id)
    )
    generated_at = perf_counter()
    batch = score_selected_complete_assignments(
        session,
        candidates,
        candidate_limit=MAX_COMPLETE_CANDIDATES,
    )
    finished = perf_counter()

    incumbent_score = next(row for row in batch.scores if row.candidate.is_incumbent)
    max_changed_artifacts = max(
        sum(
            left != right
            for left, right in zip(
                row.candidate.artifact_ids,
                tuple(
                    artifact_id
                    for assignment in incumbent_assignments
                    for artifact_id in assignment.artifact_ids
                ),
                strict=True,
            )
        )
        for row in batch.scores
    )
    output = {
        "diagnostic_only": True,
        "authoritative": batch.authoritative,
        "prune_authority": batch.prune_authority,
        "engine_calls": batch.engine_call_count,
        "trace_evidence_sha256": trace.evidence_sha256,
        "objective_sha256": batch.objective_sha256,
        "variable_slot_count": len(selected_alternatives),
        "support_variable_slot_count": sum(
            1 for _key, value in selected_alternatives if value[0]
        ),
        "binary_domain_size": 1 << len(selected_alternatives),
        "valid_complete_assignment_count": len(batch.scores),
        "rejected_invalid_assignment_count": rejected_invalid,
        "max_changed_artifact_count": max_changed_artifacts,
        "incumbent_preserved": any(row.candidate.is_incumbent for row in batch.scores),
        "incumbent_damage_delta": (
            incumbent_score.score.candidate_damage
            - objective.direct_fast.baseline_damage
        ),
        "support_cache": {
            "entries": batch.support_cache_entries,
            "hits": batch.support_cache_hits,
            "misses": batch.support_cache_misses,
        },
        "timing_seconds": {
            "load": prepared_at - started,
            "compile": compiled_at - prepared_at,
            "generate_reduced_complete_domain": generated_at - compiled_at,
            "score_complete_assignments": finished - generated_at,
            "total": finished - started,
        },
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
