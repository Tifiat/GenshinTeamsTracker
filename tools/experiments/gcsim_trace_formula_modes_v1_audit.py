from __future__ import annotations

import json
import math
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

    filters = compile_rotation_formula_filters(trace)
    compiled_at = perf_counter()

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
    corpus_at = perf_counter()

    standard_rows = tuple(
        (
            candidate,
            evaluate_rotation_formula_filter(
                filters,
                RotationFormulaMode.STANDARD,
                candidate.replacements,
            ),
        )
        for candidate in corpus.candidates
    )
    standard_at = perf_counter()
    fast_rows = tuple(
        (
            candidate,
            evaluate_rotation_formula_filter(
                filters,
                RotationFormulaMode.FAST,
                candidate.replacements,
            ),
        )
        for candidate in corpus.candidates
    )
    fast_at = perf_counter()

    standard_sorted = sorted(
        standard_rows,
        key=lambda row: (-row[1].candidate_damage, row[0].candidate_input_sha256),
    )
    fast_sorted = sorted(
        fast_rows,
        key=lambda row: (-row[1].candidate_damage, row[0].candidate_input_sha256),
    )
    standard_rank = {
        candidate.candidate_input_sha256: index + 1
        for index, (candidate, _) in enumerate(standard_sorted)
    }
    fast_rank = {
        candidate.candidate_input_sha256: index + 1
        for index, (candidate, _) in enumerate(fast_sorted)
    }
    fast_score_by_id = {
        candidate.candidate_input_sha256: score
        for candidate, score in fast_rows
    }
    delta_errors = []
    sign_matches = 0
    comparison_rows = []
    for candidate, standard_score in standard_rows:
        fast_score = fast_score_by_id[candidate.candidate_input_sha256]
        error = abs(standard_score.expected_delta - fast_score.expected_delta)
        delta_errors.append(error)
        signs_match = _sign(standard_score.expected_delta) == _sign(
            fast_score.expected_delta
        )
        if signs_match:
            sign_matches += 1
        comparison_rows.append(
            {
                "candidate_input_sha256": candidate.candidate_input_sha256,
                "wearer": candidate.changed_wearer_key,
                "slot": candidate.changed_slot,
                "replacements": [row.to_dict() for row in candidate.replacements],
                "standard_delta": standard_score.expected_delta,
                "fast_delta": fast_score.expected_delta,
                "absolute_delta_error": error,
                "signs_match": signs_match,
                "standard_rank": standard_rank[candidate.candidate_input_sha256],
                "fast_rank": fast_rank[candidate.candidate_input_sha256],
            }
        )
    rank_pairs = tuple(
        (standard_rank[key], fast_rank[key]) for key in standard_rank
    )
    output = {
        "engine_calls": 0,
        "diagnostic_only": True,
        "trace_decode_seconds": decoded_at - started,
        "both_filters_compile_seconds": compiled_at - decoded_at,
        "database_snapshot_corpus_seconds": corpus_at - compiled_at,
        "standard_all_candidates_seconds": standard_at - corpus_at,
        "fast_all_candidates_seconds": fast_at - standard_at,
        "total_seconds": fast_at - started,
        "candidate_count": len(corpus.candidates),
        "standard_group_count": filters.standard.group_count,
        "fast_channel_count": filters.fast.coarse_channel_count,
        "fast_actor_formulas": [
            {
                "actor_key": actor.actor_key,
                "channel_count": actor.channel_count,
                "frozen_damage": actor.frozen_damage,
                "normal_channels": [
                    {
                        "scaling_kind": channel.scaling_kind.value,
                        "amplifying": channel.amplifying,
                        "event_count": channel.event_count,
                        "activation_rate_per_second": (
                            channel.activation_rate_per_second
                        ),
                        "average_scale_coefficient": (
                            channel.average_scale_coefficient
                        ),
                        "element_bonus_weights": dict(
                            channel.element_bonus_weights
                        ),
                        "unresolved_input_event_count": (
                            channel.unresolved_input_event_count
                        ),
                    }
                    for channel in actor.normal_channels
                ],
                "reaction_channel": (
                    None
                    if actor.reaction_channel is None
                    else {
                        "event_count": actor.reaction_channel.event_count,
                        "activation_rate_per_second": (
                            actor.reaction_channel.activation_rate_per_second
                        ),
                    }
                ),
            }
            for actor in filters.fast.actor_formulas
        ],
        "baseline_absolute_error": abs(
            filters.standard.baseline_damage - filters.fast.baseline_damage
        ),
        "mean_absolute_delta_error": sum(delta_errors) / len(delta_errors),
        "max_absolute_delta_error": max(delta_errors),
        "delta_error_quantiles": {
            str(quantile): _quantile(delta_errors, quantile)
            for quantile in (0.5, 0.9, 0.95, 0.99)
        },
        "delta_sign_agreement": sign_matches / len(corpus.candidates),
        "sign_disagreements": [
            row for row in comparison_rows if not row["signs_match"]
        ],
        "worst_delta_errors": sorted(
            comparison_rows,
            key=lambda row: (
                -row["absolute_delta_error"],
                row["candidate_input_sha256"],
            ),
        )[:5],
        "spearman_rank_correlation": _spearman(rank_pairs),
        "top_recall": {
            str(limit): _top_recall(standard_sorted, fast_sorted, limit)
            for limit in (8, 16, 32, 64)
        },
        "standard_leader_fast_rank": fast_rank[
            standard_sorted[0][0].candidate_input_sha256
        ],
        "fast_leader_standard_rank": standard_rank[
            fast_sorted[0][0].candidate_input_sha256
        ],
        "same_leader": (
            standard_sorted[0][0].candidate_input_sha256
            == fast_sorted[0][0].candidate_input_sha256
        ),
        "standard_top": _top_rows(standard_sorted, fast_rank),
        "fast_top": _top_rows(fast_sorted, standard_rank),
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))


def _top_recall(standard, fast, limit):
    standard_ids = {
        candidate.candidate_input_sha256 for candidate, _ in standard[:limit]
    }
    fast_ids = {candidate.candidate_input_sha256 for candidate, _ in fast[:limit]}
    return len(standard_ids & fast_ids) / limit


def _top_rows(rows, other_rank):
    return [
        {
            "candidate_input_sha256": candidate.candidate_input_sha256,
            "wearer": candidate.changed_wearer_key,
            "slot": candidate.changed_slot,
            "estimated_delta": score.expected_delta,
            "other_mode_rank": other_rank[candidate.candidate_input_sha256],
        }
        for candidate, score in rows[:10]
    ]


def _spearman(pairs):
    count = len(pairs)
    if count < 2:
        return 1.0
    squared = sum((left - right) ** 2 for left, right in pairs)
    return 1.0 - 6.0 * squared / (count * (count * count - 1))


def _sign(value):
    if math.isclose(value, 0.0, rel_tol=1e-12, abs_tol=1e-9):
        return 0
    return 1 if value > 0.0 else -1


def _quantile(values, quantile):
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


if __name__ == "__main__":
    main()
