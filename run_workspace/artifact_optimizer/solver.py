from __future__ import annotations

import heapq
import math
from collections import Counter, defaultdict
from dataclasses import replace
from typing import Iterable, Mapping, Protocol, Sequence

from .models import (
    ARTIFACT_POSITIONS,
    ArtifactBuildCandidate,
    ArtifactOptimizationDiagnostics,
    ArtifactOptimizationReport,
    ArtifactOptimizationRequest,
    ArtifactSetCount,
    OptimizerArtifact,
)


class FinalBuildEvaluator(Protocol):
    """Expensive optional evaluator used only after proxy candidate search."""

    def __call__(
        self,
        candidate: ArtifactBuildCandidate,
        artifacts_by_id: Mapping[int, OptimizerArtifact],
    ) -> float: ...


def optimize_artifacts(
    artifacts: Iterable[OptimizerArtifact],
    request: ArtifactOptimizationRequest,
    *,
    final_evaluator: FinalBuildEvaluator | None = None,
) -> ArtifactOptimizationReport:
    artifact_list = tuple(artifacts)
    artifacts_by_id = _validate_artifacts(artifact_list)
    weights = _clean_numeric_mapping(request.weights, "weights")
    minimum_stats = _clean_numeric_mapping(
        request.minimum_stats,
        "minimum_stats",
    )
    fixed_by_pos = _validate_request(request, artifacts_by_id)

    filtered = [
        artifact
        for artifact in artifact_list
        if _artifact_passes_filters(artifact, request, fixed_by_pos)
    ]
    pools_before = _group_candidate_pools(filtered)
    _validate_candidate_pools(pools_before, fixed_by_pos)

    proxy_scores = {
        artifact.artifact_id: _weighted_artifact_score(artifact, weights)
        for artifact in filtered
    }
    pools_after, pool_truncated = _shortlist_candidate_pools(
        pools_before,
        proxy_scores,
        request,
    )

    position_order = tuple(
        sorted(
            ARTIFACT_POSITIONS,
            key=lambda pos: (
                0 if pos in fixed_by_pos else 1,
                len(pools_after[pos]),
                pos,
            ),
        )
    )
    pools = {
        pos: tuple(
            sorted(
                pools_after[pos],
                key=lambda artifact: (
                    -proxy_scores[artifact.artifact_id],
                    artifact.artifact_id,
                ),
            )
        )
        for pos in position_order
    }

    heap_size = int(request.rerank_pool_size or request.top_k)
    optimistic_score_suffix = _score_upper_bound_suffix(
        position_order,
        pools,
        proxy_scores,
    )
    minimum_stat_suffix = _minimum_stat_upper_bound_suffix(
        position_order,
        pools,
        minimum_stats,
    )
    required_counts = _merged_set_requirements(request)
    set_availability_suffix = _set_availability_suffix(
        position_order,
        pools,
        required_counts,
    )

    selected: dict[int, OptimizerArtifact] = {}
    selected_ids: set[int] = set()
    stat_totals: defaultdict[int, float] = defaultdict(float)
    set_counts: Counter[str] = Counter()
    best_heap: list[
        tuple[
            float,
            tuple[int, ...],
            ArtifactBuildCandidate,
        ]
    ] = []
    counters = {
        "complete": 0,
        "feasible": 0,
        "upper": 0,
        "minimum": 0,
        "set": 0,
        "duplicate": 0,
    }
    stopped_by_limit = False

    def visit(depth: int, current_score: float) -> bool:
        nonlocal stopped_by_limit
        if request.max_combinations is not None:
            if counters["complete"] >= int(request.max_combinations):
                stopped_by_limit = True
                return False

        if _cannot_meet_minimum_stats(
            stat_totals,
            minimum_stats,
            minimum_stat_suffix[depth],
        ):
            counters["minimum"] += 1
            return True
        if _cannot_meet_set_requirements(
            set_counts,
            required_counts,
            set_availability_suffix[depth],
        ):
            counters["set"] += 1
            return True
        if len(best_heap) >= heap_size:
            optimistic_score = current_score + optimistic_score_suffix[depth]
            if optimistic_score < best_heap[0][0]:
                counters["upper"] += 1
                return True

        if depth == len(position_order):
            counters["complete"] += 1
            if not _meets_minimum_stats(stat_totals, minimum_stats):
                return True
            if not _meets_set_requirements(set_counts, required_counts):
                return True
            counters["feasible"] += 1
            candidate = _build_candidate(selected, stat_totals, current_score)
            _keep_candidate(best_heap, candidate, heap_size)
            return True

        pos = position_order[depth]
        for artifact in pools[pos]:
            if artifact.artifact_id in selected_ids:
                counters["duplicate"] += 1
                continue
            selected[pos] = artifact
            selected_ids.add(artifact.artifact_id)
            set_counts[artifact.set_key] += 1
            for property_type, value in artifact.stats:
                stat_totals[property_type] += value

            should_continue = visit(
                depth + 1,
                current_score + proxy_scores[artifact.artifact_id],
            )

            for property_type, value in artifact.stats:
                stat_totals[property_type] -= value
                if math.isclose(stat_totals[property_type], 0.0, abs_tol=1e-12):
                    del stat_totals[property_type]
            set_counts[artifact.set_key] -= 1
            if set_counts[artifact.set_key] == 0:
                del set_counts[artifact.set_key]
            selected_ids.remove(artifact.artifact_id)
            del selected[pos]

            if not should_continue:
                return False
        return True

    visit(0, 0.0)
    proxy_candidates = _sorted_heap_candidates(best_heap)
    reranked_count = 0
    if final_evaluator is not None:
        reranked = []
        for candidate in proxy_candidates:
            score = _finite_score(final_evaluator(candidate, artifacts_by_id))
            reranked.append(replace(candidate, score=score))
            reranked_count += 1
        candidates = tuple(
            sorted(
                reranked,
                key=lambda item: (-item.score, item.artifact_ids()),
            )[: request.top_k]
        )
    else:
        candidates = proxy_candidates[: request.top_k]

    proxy_search_complete = not pool_truncated and not stopped_by_limit
    search_complete = proxy_search_complete
    if final_evaluator is not None:
        search_complete = (
            proxy_search_complete
            and counters["upper"] == 0
            and counters["feasible"] <= heap_size
        )
    warnings: list[str] = []
    if pool_truncated:
        warnings.append("candidate_pool_shortlisted")
    if stopped_by_limit:
        warnings.append("combination_limit_reached")
    warnings.append("proxy_artifact_set_bonus_effects_not_scored")
    if final_evaluator is not None:
        warnings.append("final_evaluator_reranked_proxy_candidate_pool")

    diagnostics = ArtifactOptimizationDiagnostics(
        input_artifact_count=len(artifact_list),
        filtered_artifact_count=len(filtered),
        candidate_counts_before_shortlist=tuple(
            (pos, len(pools_before[pos])) for pos in ARTIFACT_POSITIONS
        ),
        candidate_counts_after_shortlist=tuple(
            (pos, len(pools_after[pos])) for pos in ARTIFACT_POSITIONS
        ),
        estimated_combinations_before_shortlist=_combination_count(pools_before),
        estimated_combinations_after_shortlist=_combination_count(pools_after),
        complete_builds_considered=counters["complete"],
        feasible_builds_evaluated=counters["feasible"],
        reranked_builds=reranked_count,
        upper_bound_pruned_branches=counters["upper"],
        minimum_stat_pruned_branches=counters["minimum"],
        set_requirement_pruned_branches=counters["set"],
        duplicate_artifact_pruned_branches=counters["duplicate"],
        candidate_pool_truncated=pool_truncated,
        stopped_by_combination_limit=stopped_by_limit,
        search_complete=search_complete,
        quality="exact" if search_complete else "best_found",
    )
    return ArtifactOptimizationReport(
        candidates=tuple(candidates),
        diagnostics=diagnostics,
        warnings=tuple(warnings),
    )


def _validate_artifacts(
    artifacts: Sequence[OptimizerArtifact],
) -> dict[int, OptimizerArtifact]:
    result: dict[int, OptimizerArtifact] = {}
    for artifact in artifacts:
        if artifact.pos not in ARTIFACT_POSITIONS:
            raise ValueError(
                f"Artifact {artifact.artifact_id} has invalid position {artifact.pos}"
            )
        if artifact.artifact_id in result:
            raise ValueError(f"Duplicate artifact id: {artifact.artifact_id}")
        if not str(artifact.set_key).strip():
            raise ValueError(f"Artifact {artifact.artifact_id} has no set_key")
        seen_stat_types: set[int] = set()
        for property_type, value in artifact.stats:
            property_type = int(property_type)
            if property_type in seen_stat_types:
                raise ValueError(
                    f"Artifact {artifact.artifact_id} repeats stat {property_type}"
                )
            if not math.isfinite(float(value)):
                raise ValueError(
                    f"Artifact {artifact.artifact_id} has non-finite stat "
                    f"{property_type}"
                )
            seen_stat_types.add(property_type)
        result[artifact.artifact_id] = artifact
    return result


def _validate_request(
    request: ArtifactOptimizationRequest,
    artifacts_by_id: Mapping[int, OptimizerArtifact],
) -> dict[int, int]:
    fixed_by_pos = {
        int(pos): int(artifact_id)
        for pos, artifact_id in request.fixed_artifact_ids_by_pos.items()
    }
    for pos, artifact_id in fixed_by_pos.items():
        if pos not in ARTIFACT_POSITIONS:
            raise ValueError(f"Invalid fixed artifact position: {pos}")
        artifact = artifacts_by_id.get(artifact_id)
        if artifact is None:
            raise ValueError(f"Unknown fixed artifact id: {artifact_id}")
        if artifact.pos != pos:
            raise ValueError(
                f"Fixed artifact {artifact_id} belongs to position {artifact.pos}, not {pos}"
            )
        if artifact_id in request.excluded_artifact_ids:
            raise ValueError(f"Fixed artifact {artifact_id} is also excluded")

    for pos in request.allowed_main_stats_by_pos:
        if int(pos) not in ARTIFACT_POSITIONS:
            raise ValueError(f"Invalid main-stat filter position: {pos}")
    return fixed_by_pos


def _clean_numeric_mapping(
    values: Mapping[int, float],
    name: str,
) -> dict[int, float]:
    result: dict[int, float] = {}
    for key, value in values.items():
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError(f"{name}[{key}] must be finite")
        result[int(key)] = numeric
    return result


def _artifact_passes_filters(
    artifact: OptimizerArtifact,
    request: ArtifactOptimizationRequest,
    fixed_by_pos: Mapping[int, int],
) -> bool:
    if artifact.artifact_id in request.excluded_artifact_ids:
        return False
    fixed_id = fixed_by_pos.get(artifact.pos)
    if fixed_id is not None and artifact.artifact_id != fixed_id:
        return False
    allowed_main_stats = request.allowed_main_stats_by_pos.get(artifact.pos)
    if allowed_main_stats:
        if artifact.main_property_type not in allowed_main_stats:
            return False
    if request.minimum_rarity is not None:
        if artifact.rarity is None or artifact.rarity < request.minimum_rarity:
            return False
    if request.minimum_level is not None:
        if artifact.level is None or artifact.level < request.minimum_level:
            return False
    if not request.allow_equipped_artifacts and artifact.equipped_character_ids:
        target_id = request.target_character_id
        if target_id is None or any(
            owner_id != target_id for owner_id in artifact.equipped_character_ids
        ):
            return False
    return True


def _group_candidate_pools(
    artifacts: Iterable[OptimizerArtifact],
) -> dict[int, list[OptimizerArtifact]]:
    pools = {pos: [] for pos in ARTIFACT_POSITIONS}
    for artifact in artifacts:
        pools[artifact.pos].append(artifact)
    for pos in ARTIFACT_POSITIONS:
        pools[pos].sort(key=lambda artifact: artifact.artifact_id)
    return pools


def _validate_candidate_pools(
    pools: Mapping[int, Sequence[OptimizerArtifact]],
    fixed_by_pos: Mapping[int, int],
) -> None:
    for pos in ARTIFACT_POSITIONS:
        if pools[pos]:
            continue
        fixed = fixed_by_pos.get(pos)
        if fixed is not None:
            raise ValueError(
                f"Fixed artifact {fixed} for position {pos} was removed by filters"
            )
        raise ValueError(f"No optimizer candidates for artifact position {pos}")


def _weighted_artifact_score(
    artifact: OptimizerArtifact,
    weights: Mapping[int, float],
) -> float:
    return sum(
        float(value) * weights.get(int(property_type), 0.0)
        for property_type, value in artifact.stats
    )


def _shortlist_candidate_pools(
    pools: Mapping[int, Sequence[OptimizerArtifact]],
    proxy_scores: Mapping[int, float],
    request: ArtifactOptimizationRequest,
) -> tuple[dict[int, list[OptimizerArtifact]], bool]:
    if request.per_slot_limit is None and request.per_set_limit is None:
        return {pos: list(pools[pos]) for pos in ARTIFACT_POSITIONS}, False

    result: dict[int, list[OptimizerArtifact]] = {}
    truncated = False
    for pos in ARTIFACT_POSITIONS:
        ranked = sorted(
            pools[pos],
            key=lambda artifact: (
                -proxy_scores[artifact.artifact_id],
                artifact.artifact_id,
            ),
        )
        selected_ids: set[int] = set()
        if request.per_slot_limit is not None:
            selected_ids.update(
                artifact.artifact_id
                for artifact in ranked[: int(request.per_slot_limit)]
            )

        if request.per_set_limit is not None:
            by_set: defaultdict[str, list[OptimizerArtifact]] = defaultdict(list)
            for artifact in ranked:
                by_set[artifact.set_key].append(artifact)
            for set_candidates in by_set.values():
                selected_ids.update(
                    artifact.artifact_id
                    for artifact in set_candidates[: int(request.per_set_limit)]
                )

        shortlisted = [
            artifact for artifact in ranked if artifact.artifact_id in selected_ids
        ]
        result[pos] = shortlisted
        truncated = truncated or len(shortlisted) < len(ranked)
    return result, truncated


def _score_upper_bound_suffix(
    position_order: Sequence[int],
    pools: Mapping[int, Sequence[OptimizerArtifact]],
    scores: Mapping[int, float],
) -> list[float]:
    suffix = [0.0] * (len(position_order) + 1)
    for depth in range(len(position_order) - 1, -1, -1):
        pos = position_order[depth]
        suffix[depth] = suffix[depth + 1] + max(
            scores[artifact.artifact_id] for artifact in pools[pos]
        )
    return suffix


def _minimum_stat_upper_bound_suffix(
    position_order: Sequence[int],
    pools: Mapping[int, Sequence[OptimizerArtifact]],
    minimum_stats: Mapping[int, float],
) -> list[dict[int, float]]:
    suffix: list[dict[int, float]] = [
        {property_type: 0.0 for property_type in minimum_stats}
        for _ in range(len(position_order) + 1)
    ]
    for depth in range(len(position_order) - 1, -1, -1):
        pos = position_order[depth]
        suffix[depth] = dict(suffix[depth + 1])
        for property_type in minimum_stats:
            suffix[depth][property_type] += max(
                artifact.stat_value(property_type) for artifact in pools[pos]
            )
    return suffix


def _merged_set_requirements(
    request: ArtifactOptimizationRequest,
) -> dict[str, int]:
    result: dict[str, int] = {}
    for requirement in request.set_requirements:
        result[requirement.set_key] = max(
            result.get(requirement.set_key, 0),
            int(requirement.minimum_count),
        )
    if sum(result.values()) > len(ARTIFACT_POSITIONS):
        raise ValueError("Set requirements need more than five artifacts")
    return result


def _set_availability_suffix(
    position_order: Sequence[int],
    pools: Mapping[int, Sequence[OptimizerArtifact]],
    required_counts: Mapping[str, int],
) -> list[dict[str, int]]:
    suffix: list[dict[str, int]] = [
        {set_key: 0 for set_key in required_counts}
        for _ in range(len(position_order) + 1)
    ]
    for depth in range(len(position_order) - 1, -1, -1):
        pos = position_order[depth]
        suffix[depth] = dict(suffix[depth + 1])
        available_sets = {artifact.set_key for artifact in pools[pos]}
        for set_key in required_counts:
            if set_key in available_sets:
                suffix[depth][set_key] += 1
    return suffix


def _cannot_meet_minimum_stats(
    current: Mapping[int, float],
    minimums: Mapping[int, float],
    remaining_maximums: Mapping[int, float],
) -> bool:
    return any(
        current.get(property_type, 0.0)
        + remaining_maximums.get(property_type, 0.0)
        < minimum
        for property_type, minimum in minimums.items()
    )


def _cannot_meet_set_requirements(
    current: Mapping[str, int],
    required: Mapping[str, int],
    remaining_positions: Mapping[str, int],
) -> bool:
    return any(
        current.get(set_key, 0) + remaining_positions.get(set_key, 0) < minimum
        for set_key, minimum in required.items()
    )


def _meets_minimum_stats(
    current: Mapping[int, float],
    minimums: Mapping[int, float],
) -> bool:
    return all(
        current.get(property_type, 0.0) >= minimum
        for property_type, minimum in minimums.items()
    )


def _meets_set_requirements(
    current: Mapping[str, int],
    required: Mapping[str, int],
) -> bool:
    return all(
        current.get(set_key, 0) >= minimum
        for set_key, minimum in required.items()
    )


def _build_candidate(
    selected: Mapping[int, OptimizerArtifact],
    stat_totals: Mapping[int, float],
    proxy_score: float,
) -> ArtifactBuildCandidate:
    set_records: dict[str, dict[str, object]] = {}
    for artifact in selected.values():
        record = set_records.setdefault(
            artifact.set_key,
            {
                "set_uid": artifact.set_uid,
                "set_name": artifact.set_name,
                "count": 0,
            },
        )
        record["count"] = int(record["count"]) + 1
    set_counts = tuple(
        ArtifactSetCount(
            set_key=set_key,
            set_uid=str(record["set_uid"]),
            set_name=str(record["set_name"]),
            count=int(record["count"]),
        )
        for set_key, record in sorted(
            set_records.items(),
            key=lambda item: (-int(item[1]["count"]), item[0]),
        )
    )
    return ArtifactBuildCandidate(
        artifact_ids_by_pos=tuple(
            (pos, selected[pos].artifact_id) for pos in ARTIFACT_POSITIONS
        ),
        stat_totals=tuple(
            (property_type, round(float(value), 6))
            for property_type, value in sorted(stat_totals.items())
        ),
        set_counts=set_counts,
        score=float(proxy_score),
        proxy_score=float(proxy_score),
    )


def _keep_candidate(
    heap: list[tuple[float, tuple[int, ...], ArtifactBuildCandidate]],
    candidate: ArtifactBuildCandidate,
    heap_size: int,
) -> None:
    inverse_artifact_ids = tuple(-value for value in candidate.artifact_ids())
    item = (candidate.proxy_score, inverse_artifact_ids, candidate)
    if len(heap) < heap_size:
        heapq.heappush(heap, item)
        return
    if item[:2] > heap[0][:2]:
        heapq.heapreplace(heap, item)


def _sorted_heap_candidates(
    heap: Sequence[tuple[float, tuple[int, ...], ArtifactBuildCandidate]],
) -> tuple[ArtifactBuildCandidate, ...]:
    return tuple(
        sorted(
            (item[2] for item in heap),
            key=lambda candidate: (
                -candidate.proxy_score,
                candidate.artifact_ids(),
            ),
        )
    )


def _combination_count(
    pools: Mapping[int, Sequence[OptimizerArtifact]],
) -> int:
    return math.prod(len(pools[pos]) for pos in ARTIFACT_POSITIONS)


def _finite_score(value: float) -> float:
    score = float(value)
    if not math.isfinite(score):
        raise ValueError("final_evaluator returned a non-finite score")
    return score
