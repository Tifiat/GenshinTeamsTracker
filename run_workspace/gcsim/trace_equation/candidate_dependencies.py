"""Conservative candidate-specific dependency slices for V6 trace evidence.

The slice is intentionally diagnostic.  It follows only typed references that
already exist in the captured trace and never turns a missing edge into a
pruning proof.  In particular, an ``OPAQUE_FROZEN`` source remains unknown
unless a future engine contract proves its candidate dependencies complete.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterable

from .contracts import (
    DamageFormulaKind,
    ReactionOperator,
    ScalingKind,
    TraceContractError,
    canonical_sha256,
)
from .ranking import RANKING_STAT_KEYS
from .source_dependencies import SourceParameterKind, SourceSliceStatus
from .state_evidence import (
    NumericReferenceKind,
    StateEvent,
    StateEventKind,
    StateEvidenceTrace,
)
from .unknown_mechanics import (
    UnknownMechanicBoundaryKey,
    collect_executed_unknown_boundaries,
)


CANDIDATE_DEPENDENCY_SLICE_SCHEMA_VERSION = 1
CANDIDATE_DEPENDENCY_SLICE_KIND = "gtt.trace_equation.candidate_dependency_slice"

_DERIVED_PARAMETER_INPUTS = {
    "max_hp": frozenset({"hp", "hp%"}),
    "total_atk": frozenset({"atk", "atk%"}),
    "total_def": frozenset({"def", "def%"}),
}


@dataclass(frozen=True, order=True, slots=True)
class CandidateStatCoordinate:
    actor_key: str
    stat_key: str

    def __post_init__(self) -> None:
        if not self.actor_key or self.actor_key.strip() != self.actor_key:
            raise TraceContractError("candidate actor_key must be trimmed")
        if self.stat_key not in RANKING_STAT_KEYS:
            raise TraceContractError(
                f"candidate stat {self.stat_key!r} is unsupported"
            )

    @property
    def dimension(self) -> str:
        return f"{self.actor_key}:{self.stat_key}"

    def to_dict(self) -> dict[str, str]:
        return {"actor_key": self.actor_key, "stat_key": self.stat_key}


@dataclass(frozen=True, slots=True)
class CandidateDependencySlice:
    trace_evidence_sha256: str
    coordinates: tuple[CandidateStatCoordinate, ...]
    seed_node_ids: tuple[str, ...]
    reached_node_ids: tuple[str, ...]
    affected_hit_event_ids: tuple[str, ...]
    reachable_boundary_keys: tuple[UnknownMechanicBoundaryKey, ...]
    proven_independent_boundary_keys: tuple[UnknownMechanicBoundaryKey, ...]
    unresolved_boundary_keys: tuple[UnknownMechanicBoundaryKey, ...]
    coverage_gap_codes: tuple[str, ...]
    engine_call_count: int = 0
    schema_version: int = CANDIDATE_DEPENDENCY_SLICE_SCHEMA_VERSION
    kind: str = CANDIDATE_DEPENDENCY_SLICE_KIND

    def __post_init__(self) -> None:
        if self.schema_version != CANDIDATE_DEPENDENCY_SLICE_SCHEMA_VERSION:
            raise TraceContractError("candidate dependency slice schema mismatch")
        if self.kind != CANDIDATE_DEPENDENCY_SLICE_KIND:
            raise TraceContractError("candidate dependency slice kind mismatch")
        if self.engine_call_count != 0:
            raise TraceContractError("candidate dependency slice cannot call engine")
        if tuple(sorted(set(self.coordinates))) != self.coordinates:
            raise TraceContractError("candidate coordinates must be canonical")
        for value, name in (
            (self.seed_node_ids, "seed_node_ids"),
            (self.reached_node_ids, "reached_node_ids"),
            (self.affected_hit_event_ids, "affected_hit_event_ids"),
            (self.coverage_gap_codes, "coverage_gap_codes"),
        ):
            if tuple(sorted(set(value))) != value:
                raise TraceContractError(f"{name} must be sorted unique")
        boundary_groups = (
            self.reachable_boundary_keys,
            self.proven_independent_boundary_keys,
            self.unresolved_boundary_keys,
        )
        for value in boundary_groups:
            if tuple(sorted(set(value))) != value:
                raise TraceContractError("boundary keys must be canonical")
        if set(self.reachable_boundary_keys) & set(
            self.proven_independent_boundary_keys
        ):
            raise TraceContractError("reachable boundary cannot be independent")
        if set(self.unresolved_boundary_keys) & (
            set(self.reachable_boundary_keys)
            | set(self.proven_independent_boundary_keys)
        ):
            raise TraceContractError("unresolved boundary classification overlaps")

    @property
    def dependency_proof_complete(self) -> bool:
        return not self.unresolved_boundary_keys and not self.coverage_gap_codes

    @property
    def hard_prune_allowed(self) -> bool:
        return False

    @property
    def slice_sha256(self) -> str:
        return canonical_sha256(self.to_dict(include_hash=False))

    @property
    def affected_dimensions_by_source(self) -> dict[str, tuple[str, ...]]:
        dimensions = tuple(row.dimension for row in self.coordinates)
        return {
            key.source_id: dimensions
            for key in self.reachable_boundary_keys
            if key.source_id is not None
        }

    @property
    def candidate_reachable_source_ids(self) -> frozenset[str]:
        return frozenset(
            key.source_id
            for key in self.reachable_boundary_keys
            if key.source_id is not None
        )

    @property
    def candidate_independent_source_ids(self) -> frozenset[str]:
        return frozenset(
            key.source_id
            for key in self.proven_independent_boundary_keys
            if key.source_id is not None
        )

    def to_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        row: dict[str, object] = {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "trace_evidence_sha256": self.trace_evidence_sha256,
            "coordinates": [item.to_dict() for item in self.coordinates],
            "seed_node_ids": list(self.seed_node_ids),
            "reached_node_ids": list(self.reached_node_ids),
            "affected_hit_event_ids": list(self.affected_hit_event_ids),
            "reachable_boundary_keys": [
                item.to_dict() for item in self.reachable_boundary_keys
            ],
            "proven_independent_boundary_keys": [
                item.to_dict() for item in self.proven_independent_boundary_keys
            ],
            "unresolved_boundary_keys": [
                item.to_dict() for item in self.unresolved_boundary_keys
            ],
            "coverage_gap_codes": list(self.coverage_gap_codes),
            "dependency_proof_complete": self.dependency_proof_complete,
            "engine_call_count": 0,
            "hard_prune_allowed": False,
        }
        if include_hash:
            row["slice_sha256"] = self.slice_sha256
        return row


class CandidateDependencyIndex:
    """One compiled V6 dependency graph with memoized per-coordinate slices."""

    def __init__(self, trace: StateEvidenceTrace) -> None:
        if not isinstance(trace, StateEvidenceTrace):
            raise TraceContractError("candidate dependency index requires V6 evidence")
        self.trace = trace
        self.trace_evidence_sha256 = trace.evidence_sha256
        self.character_keys = trace.terminal_trace.request.character_keys
        self.graph: dict[str, set[str]] = defaultdict(set)
        self.binding_nodes_by_hit: dict[str, tuple[str, ...]] = {}
        self.occurrence_nodes_by_hit: dict[str, tuple[str, ...]] = {}
        self.boundary_nodes = _boundary_nodes(trace)
        self.reaction_by_event = {
            row.event_id: row.formula
            for row in trace.reaction_evidence.reaction_hits
        }
        self._single_cache: dict[
            CandidateStatCoordinate,
            CandidateDependencySlice,
        ] = {}
        self._build_graph()

    def _build_graph(self) -> None:
        occurrence_nodes_by_hit: dict[str, list[str]] = defaultdict(list)
        terminal_hit_by_occurrence: dict[str, str] = {}
        terminal_hit_frames = {
            hit.event_id: hit.frame for hit in self.trace.terminal_trace.hits
        }
        for occurrence in self.trace.occurrences:
            node = _occurrence_node(occurrence.occurrence_id)
            if occurrence.parent_occurrence_id is not None:
                self.graph[_occurrence_node(occurrence.parent_occurrence_id)].add(
                    node
                )
            if occurrence.terminal_event_id is not None:
                self.graph[node].add(_hit_node(occurrence.terminal_event_id))
                terminal_hit_by_occurrence[
                    occurrence.occurrence_id
                ] = occurrence.terminal_event_id
                occurrence_nodes_by_hit[occurrence.terminal_event_id].append(node)

        binding_nodes_by_hit: dict[str, list[str]] = defaultdict(list)
        for binding in self.trace.value_bindings:
            node = _binding_node(binding.binding_id)
            occurrence_node = _occurrence_node(binding.occurrence_id)
            self.graph[occurrence_node].add(node)
            if binding.terminal_event_id is not None:
                hit_node = _hit_node(binding.terminal_event_id)
                self.graph[node].add(hit_node)
                binding_nodes_by_hit[binding.terminal_event_id].append(node)

        health_nodes = {
            row.operation_id: _health_node(row.operation_id)
            for row in self.trace.health_operations
        }
        last_slot_value_node: dict[str, str] = {}
        task_enqueue_node: dict[str, str] = {}
        for event in self.trace.state_events:
            node = _event_node(event.event_id)
            if event.parent_event_id is not None:
                self.graph[_event_node(event.parent_event_id)].add(node)
            if event.source_occurrence_id is not None:
                self.graph[_occurrence_node(event.source_occurrence_id)].add(node)
                terminal_hit = terminal_hit_by_occurrence.get(
                    event.source_occurrence_id
                )
                if (
                    terminal_hit is not None
                    and event.frame <= terminal_hit_frames[terminal_hit]
                ):
                    # State evidence recorded while evaluating a source that
                    # terminates in this hit is an input to that terminal
                    # result. This is a conservative forward edge only; it
                    # never creates a pruning proof.
                    self.graph[node].add(_hit_node(terminal_hit))
            if event.health_operation_id is not None:
                self.graph[health_nodes[event.health_operation_id]].add(node)
            if event.bound_event_id is not None:
                self.graph[_event_node(event.bound_event_id)].add(node)
            for reference in event.inputs:
                _add_reference_edge(self.graph, reference, node)
            for payload in event.numeric_payload:
                _add_reference_edge(self.graph, payload.reference, node)
            for modifier_id in event.modifier_eval_ids:
                self.graph[_event_node(modifier_id)].add(node)
            if event.slot_id is not None:
                previous = last_slot_value_node.get(event.slot_id)
                if previous is not None:
                    self.graph[previous].add(node)
                if event.kind in {
                    StateEventKind.STATE_SLOT_REGISTER,
                    StateEventKind.STATE_WRITE,
                    StateEventKind.STATE_RESYNC,
                }:
                    last_slot_value_node[event.slot_id] = node
            if event.task_id is not None:
                if event.kind is StateEventKind.TASK_ENQUEUE:
                    task_enqueue_node[event.task_id] = node
                elif event.task_id in task_enqueue_node:
                    self.graph[task_enqueue_node[event.task_id]].add(node)
            if event.kind is StateEventKind.HEALTH_FIELD_BINDING:
                assert event.health_operation_id is not None
                self.graph[node].add(health_nodes[event.health_operation_id])

        self.binding_nodes_by_hit = {
            key: tuple(sorted(value)) for key, value in binding_nodes_by_hit.items()
        }
        self.occurrence_nodes_by_hit = {
            key: tuple(sorted(value)) for key, value in occurrence_nodes_by_hit.items()
        }

    def slice(
        self,
        coordinates: Iterable[CandidateStatCoordinate],
    ) -> CandidateDependencySlice:
        canonical_coordinates = tuple(sorted(set(coordinates)))
        if not canonical_coordinates:
            raise TraceContractError(
                "candidate dependency slice requires coordinates"
            )
        unknown_actors = {
            row.actor_key for row in canonical_coordinates
        } - set(self.character_keys)
        if unknown_actors:
            raise TraceContractError(
                "candidate dependency slice has unknown actors: "
                f"{sorted(unknown_actors)!r}"
            )
        singles = tuple(self._single(coordinate) for coordinate in canonical_coordinates)
        seeds = {node for row in singles for node in row.seed_node_ids}
        reached = {node for row in singles for node in row.reached_node_ids}
        affected_hits = {
            event_id for row in singles for event_id in row.affected_hit_event_ids
        }
        reachable_boundaries = {
            key for row in singles for key in row.reachable_boundary_keys
        }
        all_boundaries = set(self.boundary_nodes)
        unresolved_boundaries = all_boundaries - reachable_boundaries
        coverage_gaps = {
            code for row in singles for code in row.coverage_gap_codes
        }
        if unresolved_boundaries:
            coverage_gaps.add("opaque_or_incomplete_boundary_inputs_not_enumerated")
        else:
            coverage_gaps.discard(
                "opaque_or_incomplete_boundary_inputs_not_enumerated"
            )
        return CandidateDependencySlice(
            trace_evidence_sha256=self.trace_evidence_sha256,
            coordinates=canonical_coordinates,
            seed_node_ids=tuple(sorted(seeds)),
            reached_node_ids=tuple(sorted(reached)),
            affected_hit_event_ids=tuple(sorted(affected_hits)),
            reachable_boundary_keys=tuple(sorted(reachable_boundaries)),
            proven_independent_boundary_keys=(),
            unresolved_boundary_keys=tuple(sorted(unresolved_boundaries)),
            coverage_gap_codes=tuple(sorted(coverage_gaps)),
        )

    def _single(
        self,
        coordinate: CandidateStatCoordinate,
    ) -> CandidateDependencySlice:
        cached = self._single_cache.get(coordinate)
        if cached is not None:
            return cached
        actor_index = self.character_keys.index(coordinate.actor_key)
        seeds: set[str] = set()
        affected_hits: set[str] = set()
        matched_structural_seed = False
        for event in self.trace.state_events:
            if _event_reads_coordinate(event, coordinate, actor_index):
                seeds.add(_event_node(event.event_id))
                matched_structural_seed = True
        for binding in self.trace.value_bindings:
            if any(
                _parameter_reads_coordinate(parameter, coordinate)
                for parameter in binding.parameters
            ):
                seeds.add(_binding_node(binding.binding_id))
                matched_structural_seed = True
                if binding.terminal_event_id is not None:
                    affected_hits.add(binding.terminal_event_id)
        for hit in self.trace.terminal_trace.hits:
            reaction = self.reaction_by_event.get(hit.event_id)
            if _hit_consumes_coordinate(hit, reaction, coordinate):
                seeds.add(_hit_node(hit.event_id))
                affected_hits.add(hit.event_id)
                matched_structural_seed = True
        coverage_gaps: set[str] = set()
        if not matched_structural_seed and coordinate.stat_key in {"er", "heal"}:
            coverage_gaps.add(
                f"candidate_stat_seed_not_traced:{coordinate.dimension}"
            )
        reached = _forward_reachable(self.graph, seeds)
        for hit_id in affected_hits:
            reached.update(self.occurrence_nodes_by_hit.get(hit_id, ()))
            reached.update(self.binding_nodes_by_hit.get(hit_id, ()))
        reachable_boundaries = {
            key
            for key, nodes in self.boundary_nodes.items()
            if nodes & reached
        }
        unresolved_boundaries = set(self.boundary_nodes) - reachable_boundaries
        if unresolved_boundaries:
            coverage_gaps.add("opaque_or_incomplete_boundary_inputs_not_enumerated")
        result = CandidateDependencySlice(
            trace_evidence_sha256=self.trace_evidence_sha256,
            coordinates=(coordinate,),
            seed_node_ids=tuple(sorted(seeds)),
            reached_node_ids=tuple(sorted(reached)),
            affected_hit_event_ids=tuple(sorted(affected_hits)),
            reachable_boundary_keys=tuple(sorted(reachable_boundaries)),
            proven_independent_boundary_keys=(),
            unresolved_boundary_keys=tuple(sorted(unresolved_boundaries)),
            coverage_gap_codes=tuple(sorted(coverage_gaps)),
        )
        self._single_cache[coordinate] = result
        return result


def compile_candidate_dependency_index(
    trace: StateEvidenceTrace,
) -> CandidateDependencyIndex:
    return CandidateDependencyIndex(trace)


def build_candidate_dependency_slice(
    trace: StateEvidenceTrace,
    coordinates: Iterable[CandidateStatCoordinate],
) -> CandidateDependencySlice:
    """Follow explicit V6 references from changed artifact coordinates.

    Disconnected incomplete boundaries remain ``unresolved``.  This distinction
    is the core safety rule: graph absence is not dependency proof while the
    source compiler says that an opaque expression has unknown inputs.
    """

    return compile_candidate_dependency_index(trace).slice(coordinates)


def _boundary_nodes(
    trace: StateEvidenceTrace,
) -> dict[UnknownMechanicBoundaryKey, set[str]]:
    result: dict[UnknownMechanicBoundaryKey, set[str]] = defaultdict(set)
    for key, evidence in collect_executed_unknown_boundaries(trace).items():
        for occurrence_id in evidence.occurrence_ids:
            result[key].add(_occurrence_node(occurrence_id))
        for binding_id in evidence.binding_ids:
            result[key].add(_binding_node(binding_id))
        for event_id in evidence.event_ids:
            result[key].add(_event_node(event_id))
    return result


def _event_reads_coordinate(
    event: StateEvent,
    coordinate: CandidateStatCoordinate,
    actor_index: int,
) -> bool:
    if any(
        _parameter_reads_coordinate(parameter, coordinate)
        for parameter in event.parameters
    ):
        return True
    return (
        event.kind is StateEventKind.MAX_HP_READ
        and coordinate.stat_key in {"hp", "hp%"}
        and event.owner_index == actor_index
    )


def _parameter_reads_coordinate(parameter, coordinate) -> bool:
    if parameter.kind is not SourceParameterKind.CANDIDATE_STAT:
        return False
    if parameter.actor_key != coordinate.actor_key:
        return False
    if parameter.stat_key == coordinate.stat_key:
        return True
    return coordinate.stat_key in _DERIVED_PARAMETER_INPUTS.get(
        parameter.stat_key or "", frozenset()
    )


def _hit_consumes_coordinate(hit, reaction, coordinate) -> bool:
    if reaction is not None:
        return coordinate.stat_key == "em" and reaction.owner_key == coordinate.actor_key
    if hit.actor_key != coordinate.actor_key:
        return False
    inputs = hit.formula_inputs
    if inputs.known_formula_kind is not DamageFormulaKind.NORMAL:
        return False
    stat_key = coordinate.stat_key
    if stat_key in {"cr", "cd", "dmg%"}:
        return True
    if stat_key == _element_bonus_key(hit.element):
        return True
    if inputs.scaling_kind is ScalingKind.ATTACK and stat_key in {"atk", "atk%"}:
        return True
    if inputs.scaling_kind is ScalingKind.HP and stat_key in {"hp", "hp%"}:
        return True
    if inputs.scaling_kind is ScalingKind.DEFENSE and stat_key in {"def", "def%"}:
        return True
    if inputs.scaling_kind is ScalingKind.ELEMENTAL_MASTERY and stat_key == "em":
        return True
    return (
        stat_key == "em"
        and hit.lineage.known_reaction_operator
        is ReactionOperator.MULTIPLY_PARENT_HIT
    )


def _element_bonus_key(raw: str) -> str:
    value = raw.casefold()
    if value.startswith("element:"):
        value = value.split(":", 1)[1]
    value = {"physical": "phys", "phys": "phys"}.get(value, value)
    return f"{value}%"


def _add_reference_edge(graph, reference, consumer: str) -> None:
    if reference.kind is NumericReferenceKind.EVENT:
        assert reference.event_id is not None
        graph[_event_node(reference.event_id)].add(consumer)
    elif reference.kind is NumericReferenceKind.HEALTH_FIELD:
        assert reference.health_operation_id is not None
        graph[_health_node(reference.health_operation_id)].add(consumer)


def _forward_reachable(graph, seeds: set[str]) -> set[str]:
    reached = set(seeds)
    queue = deque(sorted(seeds))
    while queue:
        node = queue.popleft()
        for child in sorted(graph.get(node, ())):
            if child not in reached:
                reached.add(child)
                queue.append(child)
    return reached


def _event_node(value: str) -> str:
    return f"event/{value}"


def _health_node(value: str) -> str:
    return f"health/{value}"


def _occurrence_node(value: str) -> str:
    return f"occurrence/{value}"


def _binding_node(value: str) -> str:
    return f"binding/{value}"


def _hit_node(value: str) -> str:
    return f"hit/{value}"


__all__ = [
    "CANDIDATE_DEPENDENCY_SLICE_KIND",
    "CANDIDATE_DEPENDENCY_SLICE_SCHEMA_VERSION",
    "CandidateDependencySlice",
    "CandidateDependencyIndex",
    "CandidateStatCoordinate",
    "build_candidate_dependency_slice",
    "compile_candidate_dependency_index",
]
