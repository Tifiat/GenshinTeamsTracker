"""Strict offline audit for forwarded AttackInfo source provenance.

This helper consumes an already captured V6 n=1 trace.  It never starts GCSIM.
It binds the trace to the prepared engine/source manifest, applies one synthetic
artifact HP% delta to Furina, and reports which observed hits can be ranked
without freezing their baseline damage.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path

from run_workspace.gcsim.engine_store import load_engine_manifest
from run_workspace.gcsim.optimizer_engine_context import (
    load_active_gcsim_optimizer_engine_context,
)
from run_workspace.gcsim.trace_equation import (
    ArtifactStatReplacement,
    CandidateStatCoordinate,
    SourceManifestBinding,
    TraceExtractionRequest,
    TraceObjective,
    build_candidate_dependency_slice,
    build_unknown_mechanic_report,
    canonical_json,
    decode_engine_trace_v6,
    decode_source_manifest_body,
    score_with_frozen_boundaries,
)


ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / ".codex_tmp" / "forwarded_attack_v1_store"
TRACE_PATH = ROOT / ".codex_tmp" / "forwarded_attack_v1_run" / "trace.json"
SALON_PREFIX = "Salon Member: "


def main() -> None:
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
    frozen_score = score_with_frozen_boundaries(
        trace,
        (
            ArtifactStatReplacement(
                actor_key="furina",
                stat_key="hp%",
                baseline_artifact_value=0.0,
                candidate_artifact_value=0.0496,
            ),
        ),
    )
    score = frozen_score.observed_score
    hp_slice = build_candidate_dependency_slice(
        trace,
        (CandidateStatCoordinate("furina", "hp%"),),
    )
    unknown_report = build_unknown_mechanic_report(
        trace,
        exact_boundary_budget=0,
        candidate_independent_source_ids=(
            hp_slice.candidate_independent_source_ids
        ),
        candidate_reachable_source_ids=hp_slice.candidate_reachable_source_ids,
        topology_changing_source_ids=frozenset(),
        affected_dimensions_by_source=hp_slice.affected_dimensions_by_source,
        max_boundaries=256,
        max_events_per_boundary=8,
        candidate_independent_boundary_keys=frozenset(
            hp_slice.proven_independent_boundary_keys
        ),
        candidate_reachable_boundary_keys=frozenset(
            hp_slice.reachable_boundary_keys
        ),
    )

    by_ability: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "hits": 0,
            "modeled_hits": 0,
            "frozen_hits": 0,
            "baseline_score": 0.0,
            "candidate_score": 0.0,
            "uncertainty_codes": Counter(),
        }
    )
    for hit, estimate in zip(trace.terminal_trace.hits, score.ranking.hits, strict=True):
        if not hit.ability.startswith(SALON_PREFIX):
            continue
        row = by_ability[hit.ability]
        row["hits"] += 1
        if estimate.support.value == "MODELED_EXPECTATION":
            row["modeled_hits"] += 1
        else:
            row["frozen_hits"] += 1
        row["baseline_score"] += estimate.baseline_score
        row["candidate_score"] += estimate.candidate_score
        row["uncertainty_codes"].update(estimate.uncertainty_codes)

    salon_rows = []
    for ability, row in sorted(by_ability.items()):
        baseline = float(row["baseline_score"])
        candidate = float(row["candidate_score"])
        salon_rows.append(
            {
                "ability": ability,
                "hits": row["hits"],
                "modeled_hits": row["modeled_hits"],
                "frozen_hits": row["frozen_hits"],
                "baseline_score": baseline,
                "candidate_score": candidate,
                "delta": candidate - baseline,
                "uncertainty_codes": dict(row["uncertainty_codes"]),
            }
        )

    output = {
        "engine_calls_during_audit": 0,
        "strict_decode": "PASS",
        "trace_hit_count": score.ranking.total_hit_count,
        "formula_group_count": len(score.groups),
        "modeled_hit_count": score.ranking.modeled_hit_count,
        "frozen_hit_count": (
            score.ranking.total_hit_count - score.ranking.modeled_hit_count
        ),
        "modeled_baseline_share": score.modeled_baseline_share,
        "frozen_baseline_share": score.frozen_baseline_share,
        "baseline_expected_dps": score.baseline_expected_dps,
        "candidate_expected_dps": score.candidate_expected_dps,
        "expected_dps_delta": (
            None
            if score.baseline_expected_dps is None
            or score.candidate_expected_dps is None
            else score.candidate_expected_dps - score.baseline_expected_dps
        ),
        "ranking_support": score.ranking.support.value,
        "ranking_uncertainty_codes": list(score.ranking.uncertainty_codes),
        "frozen_boundary_scoring": {
            "engine_calls": frozen_score.engine_call_count,
            "orderable": frozen_score.orderable,
            "baseline_reconciled": frozen_score.coverage.baseline_reconciled,
            "baseline_reconciliation_error": (
                frozen_score.coverage.baseline_reconciliation_error
            ),
            "whole_frozen_damage_share": (
                frozen_score.coverage.whole_frozen_share
            ),
            "frozen_input_exposure_share": (
                frozen_score.coverage.frozen_input_exposure_share
            ),
            "topology_exposure_share": (
                frozen_score.coverage.topology_exposure_share
            ),
            "modeled_hit_count": frozen_score.coverage.modeled_hit_count,
            "whole_frozen_hit_count": (
                frozen_score.coverage.whole_frozen_hit_count
            ),
            "frozen_input_exposed_hit_count": (
                frozen_score.coverage.frozen_input_exposed_hit_count
            ),
            "topology_exposed_hit_count": (
                frozen_score.coverage.topology_exposed_hit_count
            ),
            "candidate_affected_hit_count": (
                frozen_score.coverage.candidate_affected_hit_count
            ),
            "candidate_reachable_whole_frozen_share": (
                frozen_score.coverage.candidate_reachable_whole_frozen_share
            ),
            "candidate_reachable_frozen_input_share": (
                frozen_score.coverage.candidate_reachable_frozen_input_share
            ),
            "candidate_reachable_topology_share": (
                frozen_score.coverage.candidate_reachable_topology_share
            ),
            "candidate_reachable_boundary_count": (
                frozen_score.coverage.candidate_reachable_boundary_count
            ),
            "candidate_unresolved_boundary_count": (
                frozen_score.coverage.candidate_unresolved_boundary_count
            ),
            "candidate_dependency_gap_codes": list(
                frozen_score.coverage.candidate_dependency_gap_codes
            ),
            "global_input_uncertainty_codes": list(
                frozen_score.coverage.global_input_uncertainty_codes
            ),
            "global_topology_uncertainty_codes": list(
                frozen_score.coverage.global_topology_uncertainty_codes
            ),
            "majority_whole_frozen": (
                frozen_score.coverage.majority_whole_frozen
            ),
        },
        "unknown_mechanic_preflight": {
            "executed_boundary_count": unknown_report.boundary_count_total,
            "exact_boundary_required": unknown_report.exact_boundary_required,
            "zero_budget_overflow": unknown_report.exact_boundary_overflow,
            "report_truncated": unknown_report.truncated,
            "candidate_reachable_source_count": len(
                hp_slice.candidate_reachable_source_ids
            ),
            "furina_hp_candidate_slice": {
                "affected_hit_count": len(hp_slice.affected_hit_event_ids),
                "reachable_boundary_count": len(
                    hp_slice.reachable_boundary_keys
                ),
                "proven_independent_boundary_count": len(
                    hp_slice.proven_independent_boundary_keys
                ),
                "unresolved_boundary_count": len(
                    hp_slice.unresolved_boundary_keys
                ),
                "dependency_proof_complete": (
                    hp_slice.dependency_proof_complete
                ),
                "coverage_gap_codes": list(hp_slice.coverage_gap_codes),
            },
        },
        "salon": salon_rows,
        "engine_artifact_sha256": context.artifact_sha256,
        "engine_binding_sha256": context.binding_sha256,
        "source_manifest_body_sha256": binding.manifest_body_sha256,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
