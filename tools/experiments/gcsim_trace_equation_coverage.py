"""Decode one GTT trace-equation output and publish a bounded coverage report.

This tool does not run GCSIM and does not search artifacts.  It verifies the
strict Python boundary, measures which frozen-rotation hits the current ranking
kernel can order, and makes collapsed or unsupported dependencies explicit.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from run_workspace.gcsim.trace_equation import (
    ProviderEvidenceTrace,
    ReactionEvidenceTrace,
    RankingSupport,
    TraceExtractionRequest,
    TraceObjective,
    canonical_json,
    canonical_sha256,
    decode_engine_trace,
    estimate_candidate_expected_damage,
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _counter_rows(counter: Counter[Any], names: tuple[str, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
        values = key if isinstance(key, tuple) else (key,)
        row = dict(zip(names, values, strict=True))
        row["count"] = count
        rows.append(row)
    return rows


def _rankable_dimensions(raw_hit: dict[str, Any]) -> set[str]:
    reaction_formula = raw_hit.get("reaction_formula")
    if isinstance(reaction_formula, dict):
        return {"em"}
    if raw_hit["formula_kind"] != "standard":
        return set()
    if raw_hit["reaction_operator_id"] not in {"none", "multiply_parent_hit"}:
        return set()
    dimensions = {"cr", "cd", "dmg%"}
    element = str(raw_hit["element"])
    if element in {
        "anemo",
        "cryo",
        "dendro",
        "electro",
        "geo",
        "hydro",
        "phys",
        "pyro",
    }:
        dimensions.add(f"{element}%")
    if abs(float(raw_hit["mult"])) > 1e-12:
        dimensions.update(
            {
                "atk": {"atk", "atk%"},
                "hp": {"hp", "hp%"},
                "def": {"def", "def%"},
                "em": {"em"},
            }[str(raw_hit["scaling_stat_kind"])]
        )
    if bool(raw_hit["amped"]):
        dimensions.add("em")
    return dimensions


def _iter_providers(raw: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for hit in raw["hits"]:
        yield hit["provider"]
        for field in (
            "stat_contributions",
            "callback_attempts",
            "attack_mods",
            "target_mod_contributions",
            "reaction_bonus_contributions",
        ):
            for row in hit[field]:
                yield row["provider"]
        reaction_formula = hit.get("reaction_formula")
        if isinstance(reaction_formula, dict):
            for row in reaction_formula["reaction_bonus_contributions"]:
                yield row["provider"]
    for transition in raw["provider_transitions"]:
        yield transition["provider"]
        displaced = transition.get("displaced_provider")
        if displaced is not None:
            yield displaced


def build_report(trace_path: Path, engine_path: Path) -> dict[str, Any]:
    raw = json.loads(trace_path.read_text(encoding="utf-8"))
    engine_artifact_sha256 = _sha256_file(engine_path)
    trace_capability = (
        "gtt_trace_equation_v3"
        if int(raw["schema_version"]) == 3
        else "gtt_trace_equation_v2"
    )
    required_capabilities = tuple(
        sorted((trace_capability, "gtt_trace_provenance_v1"))
    )
    engine_binding_sha256 = canonical_sha256(
        {
            "kind": "gtt.experimental_trace_engine_binding.v1",
            "engine_artifact_sha256": engine_artifact_sha256,
            "engine_version": raw["engine_version"],
            "patch_version": raw["patch_version"],
            "formula_version": raw["formula_version"],
            "formula_sha256": raw["formula_sha256"],
            "required_capabilities": list(required_capabilities),
        }
    )
    request = TraceExtractionRequest(
        context_sha256=raw["context_sha256"],
        source_config_sha256=raw["source_config_sha256"],
        compiled_action_sha256=raw["compiled_action_sha256"],
        target_sha256=raw["target_sha256"],
        engine_artifact_sha256=engine_artifact_sha256,
        engine_binding_sha256=engine_binding_sha256,
        formula_version=raw["formula_version"],
        formula_sha256=raw["formula_sha256"],
        seed=int(raw["seed"]),
        objective=TraceObjective.TEAM_DPS,
        character_keys=tuple(raw["character_keys"]),
        required_capabilities=required_capabilities,
    )

    decode_started = time.perf_counter()
    decoded = decode_engine_trace(canonical_json(raw), request=request)
    decode_seconds = time.perf_counter() - decode_started
    if isinstance(decoded, ReactionEvidenceTrace):
        provider_trace = decoded.provider_evidence
        ranking_document = decoded
    elif isinstance(decoded, ProviderEvidenceTrace):
        provider_trace = decoded
        ranking_document = decoded.terminal_trace
    else:
        raise RuntimeError("expected strict provider/reaction evidence trace")

    rank_started = time.perf_counter()
    estimate = estimate_candidate_expected_damage(ranking_document, ())
    rank_seconds = time.perf_counter() - rank_started
    if len(raw["hits"]) != len(estimate.hits):
        raise RuntimeError("raw and decoded hit counts differ")

    character_rows: list[dict[str, Any]] = []
    raw_by_character: dict[str, list[tuple[dict[str, Any], Any]]] = defaultdict(list)
    for raw_hit, hit_estimate in zip(raw["hits"], estimate.hits, strict=True):
        raw_by_character[hit_estimate.actor_key].append((raw_hit, hit_estimate))
    for character_key in request.character_keys:
        rows = raw_by_character[character_key]
        modeled = sum(
            hit_estimate.support is RankingSupport.MODELED_EXPECTATION
            for _, hit_estimate in rows
        )
        dimensions: set[str] = set()
        uncertainty_codes: set[str] = set()
        for raw_hit, hit_estimate in rows:
            dimensions.update(_rankable_dimensions(raw_hit))
            uncertainty_codes.update(hit_estimate.uncertainty_codes)
        character_rows.append(
            {
                "character_key": character_key,
                "hit_count": len(rows),
                "expected_arithmetic_hit_count": modeled,
                "baseline_frozen_hit_count": len(rows) - modeled,
                "nonzero_multiplier_hit_count": sum(
                    abs(float(raw_hit["mult"])) > 1e-12 for raw_hit, _ in rows
                ),
                "collapsed_flat_damage_hit_count": sum(
                    abs(float(raw_hit["flat_dmg"])) > 1e-12 for raw_hit, _ in rows
                ),
                "seeded_reported_damage": sum(
                    float(raw_hit["reported_damage"]) for raw_hit, _ in rows
                ),
                "rankable_dimensions": sorted(dimensions),
                "formula_kinds": dict(
                    sorted(Counter(raw_hit["formula_kind"] for raw_hit, _ in rows).items())
                ),
                "scaling_kinds": dict(
                    sorted(
                        Counter(raw_hit["scaling_stat_kind"] for raw_hit, _ in rows).items()
                    )
                ),
                "reaction_operators": dict(
                    sorted(
                        Counter(raw_hit["reaction_operator_id"] for raw_hit, _ in rows).items()
                    )
                ),
                "uncertainty_codes": sorted(uncertainty_codes),
            }
        )

    provider_counter: Counter[tuple[Any, ...]] = Counter()
    for provider in _iter_providers(raw):
        provider_counter[
            (
                bool(provider["known"]),
                str(provider["kind"]),
                str(provider["key"]),
                int(provider["owner_index"]),
                int(provider["piece_count"]),
            )
        ] += 1

    return {
        "kind": "gtt.trace_equation.coverage_report",
        "schema_version": 1,
        "status": "PASS",
        "scope": "one_fixed_rotation_trace_no_artifact_search",
        "identities": {
            "trace_path": str(trace_path.resolve()),
            "trace_payload_sha256": _sha256_file(trace_path),
            "context_sha256": request.context_sha256,
            "source_config_sha256": request.source_config_sha256,
            "compiled_action_sha256": request.compiled_action_sha256,
            "target_sha256": request.target_sha256,
            "engine_artifact_sha256": engine_artifact_sha256,
            "engine_binding_sha256": engine_binding_sha256,
            "engine_version": raw["engine_version"],
            "patch_version": raw["patch_version"],
            "formula_version": request.formula_version,
            "formula_sha256": request.formula_sha256,
            "seed": request.seed,
            "trace_receipt_sha256": provider_trace.terminal_trace.receipt.receipt_sha256,
            "provider_evidence_sha256": provider_trace.evidence_sha256,
            "reaction_evidence_sha256": (
                decoded.evidence_sha256
                if isinstance(decoded, ReactionEvidenceTrace)
                else None
            ),
        },
        "trace": {
            "duration_frames": int(raw["duration_frames"]),
            "hit_count": len(raw["hits"]),
            "provider_transition_count": len(raw["provider_transitions"]),
            "topology_event_count": len(raw["topology_events"]),
            "guard_summary": raw["guard_summary"],
            "top_level_unsupported": raw["unsupported"],
        },
        "ranking_kernel": {
            "support": estimate.support.value,
            "prune_safety": estimate.prune_safety.value,
            "publishable": estimate.publishable,
            "total_hit_count": estimate.total_hit_count,
            "expected_arithmetic_hit_count": estimate.modeled_hit_count,
            "baseline_frozen_hit_count": (
                estimate.total_hit_count - estimate.modeled_hit_count
            ),
            "baseline_expected_score": estimate.baseline_score,
            "global_uncertainty_codes": list(estimate.uncertainty_codes),
        },
        "characters": character_rows,
        "reaction_evidence": {
            "typed_reaction_hit_count": sum(
                isinstance(hit.get("reaction_formula"), dict)
                for hit in raw["hits"]
            ),
            "modeled_reaction_counts": dict(
                sorted(
                    Counter(
                        str(raw_hit["reaction_formula"]["reaction_type"])
                        for raw_hit, hit_estimate in zip(
                            raw["hits"], estimate.hits, strict=True
                        )
                        if isinstance(raw_hit.get("reaction_formula"), dict)
                        and hit_estimate.support
                        is RankingSupport.MODELED_EXPECTATION
                    ).items()
                )
            ),
            "unsupported_reaction_hits": [
                {
                    "event_id": hit_estimate.event_id,
                    "reaction_type": raw_hit["reaction_formula"]["reaction_type"],
                    "uncertainty_codes": list(hit_estimate.uncertainty_codes),
                }
                for raw_hit, hit_estimate in zip(
                    raw["hits"], estimate.hits, strict=True
                )
                if isinstance(raw_hit.get("reaction_formula"), dict)
                and hit_estimate.support
                is not RankingSupport.MODELED_EXPECTATION
            ],
            "generic_frozen_spawn_hit_count": sum(
                raw_hit["reaction_operator_id"] == "spawn_damage_attack"
                and not isinstance(raw_hit.get("reaction_formula"), dict)
                for raw_hit in raw["hits"]
            ),
            "unresolved_parent_occurrence_count": (
                sum(
                    not row.formula.parent_occurrence_resolved
                    for row in decoded.reaction_hits
                )
                if isinstance(decoded, ReactionEvidenceTrace)
                else 0
            ),
        },
        "provider_evidence": {
            "all_provider_identities_known": provider_trace.all_provider_identities_known,
            "authority_reason_codes": list(provider_trace.authority_reason_codes),
            "provider_rows": _counter_rows(
                provider_counter,
                ("known", "kind", "key", "owner_index", "piece_count"),
            ),
        },
        "timing_seconds": {
            "strict_decode": decode_seconds,
            "baseline_ranking": rank_seconds,
        },
        "acceptance": {
            "strict_schema_decode": True,
            "engine_trace_schema_version": int(raw["schema_version"]),
            "hard_prune_allowed": decoded.hard_prune_allowed,
            "exact_replay_eligible": decoded.exact_replay_eligible,
            "artifact_search_started": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build_report(args.trace, args.engine)
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
