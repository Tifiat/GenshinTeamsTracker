"""Non-authoritative zero-engine replay of observed support-state arithmetic.

The replay keeps the observed schedule fixed.  It only propagates candidate
artifact stat deltas through source templates, health receipts, explicit
numeric events, state slots, and modifier outputs that the V6 trace already
proved structurally.  Every unsupported boundary freezes at its observed value
and is reported; this module never grants hard-pruning authority.
"""

from __future__ import annotations

from collections import ChainMap
from dataclasses import dataclass
import math
from typing import Mapping

from .contracts import TraceContractError
from .health_evidence import HealthOperation, HealthOperationKind
from .source_dependencies import (
    SourceParameterKind,
    SourceSliceStatus,
    evaluate_source_template,
)
from .state_evidence import (
    NumericReference,
    NumericReferenceKind,
    StateEvent,
    StateEventKind,
    StateEvidenceTrace,
)


_REL_TOL = 1e-9
_ABS_TOL = 1e-7
_HEALTH_FIELDS = (
    "input_value",
    "adjusted_input_value",
    "base_amount",
    "source_bonus",
    "heal_bonus_total",
    "raw_amount",
    "event_amount",
    "event_effective_amount",
    "hp_delta_magnitude",
    "overheal",
    "hp_debt_before",
    "hp_debt_after",
    "max_hp_before",
    "max_hp_after",
    "hp_before",
    "hp_after",
    "hp_ratio_before",
    "hp_ratio_after",
)
_REPLAY_EVENT_KINDS = frozenset(
    {
        StateEventKind.STATE_SLOT_REGISTER,
        StateEventKind.STATE_READ,
        StateEventKind.MAX_HP_READ,
        StateEventKind.HEALTH_FIELD_BINDING,
        StateEventKind.HEALTH_CONTEXT_ENTER,
        StateEventKind.NUMERIC_EVAL,
        StateEventKind.STATE_WRITE,
        StateEventKind.STATE_RESYNC,
        StateEventKind.MODIFIER_EVAL,
    }
)


@dataclass(frozen=True, slots=True)
class SupportReplayHealthOperation:
    operation_id: str
    fields: tuple[tuple[str, float], ...]

    @property
    def field_map(self) -> dict[str, float]:
        return dict(self.fields)


@dataclass(frozen=True, slots=True)
class SupportReplayResult:
    evidence_sha256: str
    candidate_stat_deltas: tuple[tuple[str, str, float], ...]
    event_values: tuple[tuple[str, float], ...]
    event_outputs: tuple[tuple[str, tuple[tuple[str, float], ...]], ...]
    health_operations: tuple[SupportReplayHealthOperation, ...]
    state_slot_values: tuple[tuple[str, float], ...]
    changed_event_ids: tuple[str, ...]
    changed_health_operation_ids: tuple[str, ...]
    changed_modifier_event_ids: tuple[str, ...]
    uncertainty_codes: tuple[str, ...]
    replayed_event_count: int
    engine_call_count: int = 0
    authoritative: bool = False
    hard_prune_allowed: bool = False

    def event_value(self, event_id: str) -> float:
        return dict(self.event_values)[event_id]

    def event_output(self, event_id: str) -> dict[str, float]:
        return dict(dict(self.event_outputs)[event_id])

    def health_operation(self, operation_id: str) -> dict[str, float]:
        for operation in self.health_operations:
            if operation.operation_id == operation_id:
                return operation.field_map
        raise KeyError(operation_id)

    def state_slot_value(self, slot_id: str) -> float:
        return dict(self.state_slot_values)[slot_id]


@dataclass(slots=True)
class SupportReplayEvaluation:
    """Ephemeral candidate state used before optional diagnostic serialization."""

    evidence_sha256: str
    candidate_stat_deltas: dict[tuple[str, str], float]
    event_values: Mapping[str, float]
    event_outputs: Mapping[str, Mapping[str, float]]
    health_fields: Mapping[str, Mapping[str, float]]
    state_slot_values: dict[str, float]
    changed_modifier_event_ids: set[str]
    uncertainty_codes: set[str]
    replayed_event_count: int
    engine_call_count: int = 0
    authoritative: bool = False
    hard_prune_allowed: bool = False


@dataclass(frozen=True, slots=True)
class _SupportReplayHitPlan:
    event_id: str
    actor_key: str
    bindings: tuple[tuple[str, tuple[tuple[str, float], ...]], ...]
    bound_modifier_event_ids: tuple[str, ...]
    uncertainty_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _SupportReplayStep:
    event: StateEvent
    dependencies: frozenset[tuple[str, str]]


@dataclass(frozen=True, slots=True)
class SupportReplayPlan:
    """One trace plus its already-computed immutable evidence identity."""

    trace: StateEvidenceTrace
    evidence_sha256: str
    replay_events: tuple[StateEvent, ...]
    replay_steps: tuple[_SupportReplayStep, ...]
    replay_events_by_coordinate: Mapping[
        tuple[str, str], tuple[StateEvent, ...]
    ]
    baseline_event_values: Mapping[str, float]
    baseline_event_outputs: Mapping[str, Mapping[str, float]]
    baseline_health_fields: Mapping[str, Mapping[str, float]]
    max_hp_snapshots: tuple[tuple[str, tuple[tuple[str, float], ...]], ...]
    hit_plans: tuple[_SupportReplayHitPlan, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.trace, StateEvidenceTrace):
            raise TraceContractError("support replay plan requires StateEvidenceTrace")
        if (
            not isinstance(self.evidence_sha256, str)
            or len(self.evidence_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.evidence_sha256)
        ):
            raise TraceContractError("support replay plan evidence identity is invalid")


@dataclass(frozen=True, slots=True)
class SupportReplayHitProjection:
    event_id: str
    actor_key: str
    stat_deltas: tuple[tuple[str, float], ...]
    bound_modifier_event_ids: tuple[str, ...]
    uncertainty_codes: tuple[str, ...]

    @property
    def stat_delta_map(self) -> dict[str, float]:
        return dict(self.stat_deltas)


@dataclass(frozen=True, slots=True)
class SupportReplayHitProjectionSet:
    evidence_sha256: str
    projections: tuple[SupportReplayHitProjection, ...]
    uncertainty_codes: tuple[str, ...]
    engine_call_count: int = 0
    authoritative: bool = False
    hard_prune_allowed: bool = False

    def projection(self, event_id: str) -> SupportReplayHitProjection:
        for row in self.projections:
            if row.event_id == event_id:
                return row
        raise KeyError(event_id)


def compile_support_replay_plan(
    trace: StateEvidenceTrace,
    *,
    evidence_sha256: str | None = None,
) -> SupportReplayPlan:
    """Freeze one validated trace identity for repeated candidate replay."""

    if not isinstance(trace, StateEvidenceTrace):
        raise TraceContractError("support replay requires StateEvidenceTrace")
    hit_plans = _compile_hit_plans(trace)
    hit_ancestor_event_ids = _compile_hit_ancestor_event_ids(trace, hit_plans)
    replay_steps = tuple(
        step
        for step in _compile_replay_steps(trace)
        if step.event.event_id in hit_ancestor_event_ids
    )
    return SupportReplayPlan(
        trace=trace,
        evidence_sha256=(trace.evidence_sha256 if evidence_sha256 is None else evidence_sha256),
        replay_events=tuple(
            event for event in trace.state_events if event.kind in _REPLAY_EVENT_KINDS
        ),
        replay_steps=replay_steps,
        replay_events_by_coordinate=_index_replay_events(replay_steps),
        baseline_event_values={
            event.event_id: event.value
            for event in trace.state_events
            if event.value is not None
        },
        baseline_event_outputs={
            event.event_id: event.output_map
            for event in trace.state_events
            if event.output
        },
        baseline_health_fields={
            operation.operation_id: _observed_health_fields(operation)
            for operation in trace.health_operations
        },
        max_hp_snapshots=tuple(
            (actor, tuple(sorted(values.items())))
            for actor, values in sorted(_max_hp_snapshots(trace).items())
        ),
        hit_plans=hit_plans,
    )


def replay_support_state(
    trace: StateEvidenceTrace,
    candidate_stat_deltas: Mapping[tuple[str, str], float],
) -> SupportReplayResult:
    """Replay one artifact-stat delta vector without invoking the engine."""

    return replay_support_plan(
        compile_support_replay_plan(trace),
        candidate_stat_deltas,
    )


def replay_support_plan(
    plan: SupportReplayPlan,
    candidate_stat_deltas: Mapping[tuple[str, str], float],
) -> SupportReplayResult:
    """Replay one candidate while reusing the plan's immutable trace identity."""

    evaluation = _evaluate_support_plan(
        plan,
        candidate_stat_deltas,
        replay_events=plan.replay_events,
    )
    return _materialize_support_replay_result(plan.trace, evaluation)


def replay_support_plan_sliced(
    plan: SupportReplayPlan,
    candidate_stat_deltas: Mapping[tuple[str, str], float],
) -> SupportReplayResult:
    """Replay only the stat-reachable event slice; retains no prune authority."""

    if not isinstance(plan, SupportReplayPlan):
        raise TraceContractError("support replay requires SupportReplayPlan")
    deltas = _normalize_deltas(candidate_stat_deltas)
    replay_events = _select_replay_events(plan, frozenset(deltas))
    evaluation = _evaluate_support_plan(
        plan,
        deltas,
        replay_events=replay_events,
    )
    return _materialize_support_replay_result(plan.trace, evaluation)


def evaluate_support_plan_sliced(
    plan: SupportReplayPlan,
    candidate_stat_deltas: Mapping[tuple[str, str], float],
) -> SupportReplayEvaluation:
    """Return the compact stat-reachable evaluation without diagnostic packing."""

    if not isinstance(plan, SupportReplayPlan):
        raise TraceContractError("support replay requires SupportReplayPlan")
    deltas = _normalize_deltas(candidate_stat_deltas)
    replay_events = _select_replay_events(plan, frozenset(deltas))
    return _evaluate_support_plan(
        plan,
        deltas,
        replay_events=replay_events,
    )


def _evaluate_support_plan(
    plan: SupportReplayPlan,
    candidate_stat_deltas: Mapping[tuple[str, str], float],
    *,
    replay_events: tuple[StateEvent, ...],
) -> SupportReplayEvaluation:
    if not isinstance(plan, SupportReplayPlan):
        raise TraceContractError("support replay requires SupportReplayPlan")
    trace = plan.trace
    deltas = _normalize_deltas(candidate_stat_deltas)
    event_values = ChainMap({}, plan.baseline_event_values)
    event_outputs = ChainMap({}, plan.baseline_event_outputs)
    health_fields = ChainMap({}, plan.baseline_health_fields)
    slot_values = {slot.slot_id: slot.initial_value for slot in trace.state_slots}
    for event in trace.state_events:
        if event.kind in {StateEventKind.STATE_WRITE, StateEventKind.STATE_RESYNC}:
            if event.slot_id is not None and event.after is not None:
                slot_values[event.slot_id] = event.after

    if not deltas:
        return SupportReplayEvaluation(
            evidence_sha256=plan.evidence_sha256,
            candidate_stat_deltas=deltas,
            event_values=event_values,
            event_outputs=event_outputs,
            health_fields=health_fields,
            state_slot_values=slot_values,
            changed_modifier_event_ids=set(),
            uncertainty_codes=set(),
            replayed_event_count=0,
        )

    slot_values = {slot.slot_id: slot.initial_value for slot in trace.state_slots}
    operations = {row.operation_id: row for row in trace.health_operations}
    bindings: dict[str, dict[str, float]] = {}
    hp_delta_by_target: dict[int, float] = {}
    snapshots = {
        actor: dict(values) for actor, values in plan.max_hp_snapshots
    }
    uncertainties: set[str] = set()
    changed_modifiers: set[str] = set()

    for event in replay_events:
        baseline_value = event.value
        baseline_output = event.output_map

        if event.kind is StateEventKind.STATE_SLOT_REGISTER:
            if event.slot_id is not None and event.slot_id not in slot_values:
                slot_values[event.slot_id] = event.value or 0.0

        elif event.kind is StateEventKind.STATE_READ:
            if event.slot_id is not None and event.slot_id in slot_values:
                event_values[event.event_id] = slot_values[event.slot_id]

        elif event.kind is StateEventKind.MAX_HP_READ:
            event_outputs[event.event_id] = _candidate_max_hp_output(
                trace, event, baseline_output, deltas, event_outputs
            )

        elif event.kind is StateEventKind.HEALTH_FIELD_BINDING:
            assert event.health_operation_id is not None
            assert event.key is not None and event.bound_event_id is not None
            bindings.setdefault(event.health_operation_id, {})[event.key] = (
                _bound_event_value(
                    event.key,
                    event.bound_event_id,
                    event_values,
                    event_outputs,
                )
            )

        elif event.kind is StateEventKind.HEALTH_CONTEXT_ENTER:
            assert event.health_operation_id is not None
            operation = operations[event.health_operation_id]
            candidate, operation_uncertainties = _replay_health_operation(
                operation,
                bindings.get(operation.operation_id, {}),
                hp_delta_by_target,
            )
            health_fields[operation.operation_id] = candidate
            uncertainties.update(operation_uncertainties)

        elif event.kind is StateEventKind.NUMERIC_EVAL:
            assert event.operation is not None and event.value is not None
            candidate = _replay_numeric_event(
                trace,
                event,
                deltas,
                snapshots,
                event_values,
                event_outputs,
                health_fields,
                uncertainties,
            )
            event_values[event.event_id] = candidate

        elif event.kind is StateEventKind.STATE_WRITE:
            assert event.slot_id is not None and event.after is not None
            if event.inputs:
                candidate = _resolve_reference(
                    event.inputs[-1], event_values, event_outputs, health_fields
                )
                slot_values[event.slot_id] = candidate
            else:
                before = slot_values.get(event.slot_id, event.before)
                if before is not None and event.before is not None and not _close(before, event.before):
                    uncertainties.add(f"frozen_state_write:{event.event_id}")
                slot_values[event.slot_id] = event.after

        elif event.kind is StateEventKind.STATE_RESYNC:
            assert event.slot_id is not None and event.after is not None
            before = slot_values.get(event.slot_id, event.before)
            if before is not None and event.before is not None and not _close(before, event.before):
                uncertainties.add(f"frozen_state_resync:{event.event_id}")
            slot_values[event.slot_id] = event.after

        elif event.kind is StateEventKind.MODIFIER_EVAL and baseline_output:
            candidate_output = dict(baseline_output)
            for key, observed in baseline_output.items():
                matches: list[float] = []
                for reference in event.inputs:
                    baseline = _resolve_observed_reference(reference, trace)
                    if _close(baseline, observed):
                        matches.append(
                            _resolve_reference(
                                reference, event_values, event_outputs, health_fields
                            )
                        )
                if len(matches) == 1:
                    candidate_output[key] = matches[0]
                elif event.inputs and any(
                    _reference_changed(
                        reference, trace, event_values, event_outputs, health_fields
                    )
                    for reference in event.inputs
                ):
                    uncertainties.add(f"frozen_modifier_output:{event.event_id}:{key}")
            event_outputs[event.event_id] = candidate_output
            if any(
                not _close(candidate_output[key], baseline_output[key])
                for key in baseline_output
            ):
                changed_modifiers.add(event.event_id)

    return SupportReplayEvaluation(
        evidence_sha256=plan.evidence_sha256,
        candidate_stat_deltas=deltas,
        event_values=event_values,
        event_outputs=event_outputs,
        health_fields=health_fields,
        state_slot_values=slot_values,
        changed_modifier_event_ids=changed_modifiers,
        uncertainty_codes=uncertainties,
        replayed_event_count=len(replay_events),
    )


def project_support_replay_to_hits(
    trace: StateEvidenceTrace,
    replay: SupportReplayResult,
) -> SupportReplayHitProjectionSet:
    """Bind replayed modifier outputs to the exact hit rows that consumed them."""

    return project_support_replay_plan_to_hits(
        compile_support_replay_plan(trace),
        replay,
    )


def project_support_replay_plan_to_hits(
    plan: SupportReplayPlan,
    replay: SupportReplayResult,
) -> SupportReplayHitProjectionSet:
    """Project a replay while reusing the plan's immutable trace identity."""

    if not isinstance(plan, SupportReplayPlan):
        raise TraceContractError("support hit projection requires SupportReplayPlan")
    if not isinstance(replay, SupportReplayResult):
        raise TraceContractError("support hit projection requires SupportReplayResult")
    if replay.evidence_sha256 != plan.evidence_sha256:
        raise TraceContractError("support replay evidence does not match trace")
    replayed_outputs = {
        event_id: dict(output)
        for event_id, output in replay.event_outputs
    }
    return _project_support_outputs_to_hits(
        plan,
        replayed_outputs,
        set(replay.uncertainty_codes),
    )


def project_support_evaluation_plan_to_hits(
    plan: SupportReplayPlan,
    evaluation: SupportReplayEvaluation,
) -> SupportReplayHitProjectionSet:
    """Project an ephemeral sliced evaluation without packing the full trace."""

    if not isinstance(plan, SupportReplayPlan):
        raise TraceContractError("support hit projection requires SupportReplayPlan")
    if not isinstance(evaluation, SupportReplayEvaluation):
        raise TraceContractError(
            "support hit projection requires SupportReplayEvaluation"
        )
    if evaluation.evidence_sha256 != plan.evidence_sha256:
        raise TraceContractError("support evaluation evidence does not match trace")
    return _project_support_outputs_to_hits(
        plan,
        evaluation.event_outputs,
        set(evaluation.uncertainty_codes),
    )


def _project_support_outputs_to_hits(
    plan: SupportReplayPlan,
    replayed_outputs: Mapping[str, Mapping[str, float]],
    all_uncertainties: set[str],
) -> SupportReplayHitProjectionSet:
    projections: list[SupportReplayHitProjection] = []
    for hit_plan in plan.hit_plans:
        deltas: dict[str, float] = {}
        for event_id, observed_items in hit_plan.bindings:
            observed_output = dict(observed_items)
            candidate_output = replayed_outputs.get(event_id, observed_output)
            if set(candidate_output) != set(observed_output):
                raise TraceContractError(
                    f"replayed modifier output shape changed for {event_id!r}"
                )
            for stat_key, observed in observed_items:
                delta = candidate_output[stat_key] - observed
                if not _close(delta, 0.0):
                    deltas[stat_key] = deltas.get(stat_key, 0.0) + delta
        all_uncertainties.update(hit_plan.uncertainty_codes)
        projections.append(
            SupportReplayHitProjection(
                event_id=hit_plan.event_id,
                actor_key=hit_plan.actor_key,
                stat_deltas=tuple(
                    (key, value)
                    for key, value in sorted(deltas.items())
                    if not _close(value, 0.0)
                ),
                bound_modifier_event_ids=hit_plan.bound_modifier_event_ids,
                uncertainty_codes=hit_plan.uncertainty_codes,
            )
        )
    return SupportReplayHitProjectionSet(
        evidence_sha256=plan.evidence_sha256,
        projections=tuple(projections),
        uncertainty_codes=tuple(sorted(all_uncertainties)),
    )


def _compile_hit_plans(
    trace: StateEvidenceTrace,
) -> tuple[_SupportReplayHitPlan, ...]:
    terminal_hits = trace.terminal_trace.hits
    provider_hits = trace.reaction_evidence.provider_evidence.hit_evidence
    if tuple(row.event_id for row in terminal_hits) != tuple(
        row.event_id for row in provider_hits
    ):
        raise TraceContractError("provider hit evidence is not aligned with terminal hits")
    event_by_id = {event.event_id: event for event in trace.state_events}
    plans: list[_SupportReplayHitPlan] = []
    for hit, provider_hit in zip(terminal_hits, provider_hits, strict=True):
        bindings: list[tuple[str, tuple[tuple[str, float], ...]]] = []
        bound_ids: list[str] = []
        uncertainties: set[str] = set()
        for channel, contributions in (
            ("stat", provider_hit.stat_contributions),
            ("attack", provider_hit.attack_mods),
        ):
            for contribution in contributions:
                event_id = contribution.modifier_eval_event_id
                if event_id is None:
                    uncertainties.add(
                        f"frozen_hit_modifier_binding:{hit.event_id}:{channel}:"
                        f"{contribution.sequence_index}"
                    )
                    continue
                event = event_by_id.get(event_id)
                if event is None:
                    raise TraceContractError(
                        f"hit modifier binding references unknown event {event_id!r}"
                    )
                _validate_hit_modifier_binding(hit, contribution, channel, event)
                bindings.append((event_id, event.output))
                bound_ids.append(event_id)
        plans.append(
            _SupportReplayHitPlan(
                event_id=hit.event_id,
                actor_key=hit.actor_key,
                bindings=tuple(bindings),
                bound_modifier_event_ids=tuple(bound_ids),
                uncertainty_codes=tuple(sorted(uncertainties)),
            )
        )
    return tuple(plans)


def _compile_hit_ancestor_event_ids(
    trace: StateEvidenceTrace,
    hit_plans: tuple[_SupportReplayHitPlan, ...],
) -> frozenset[str]:
    """Find the observed event subgraph that can reach a consumed hit modifier."""

    parents: dict[str, set[str]] = {}
    last_slot_event: dict[str, str] = {}
    binding_events: dict[str, list[str]] = {}
    health_context_event: dict[str, str] = {}
    previous_health_event_by_target: dict[int, str] = {}
    operations = {row.operation_id: row for row in trace.health_operations}

    def add_reference_parent(event_id: str, reference: NumericReference) -> None:
        if reference.kind is NumericReferenceKind.EVENT:
            assert reference.event_id is not None
            parents.setdefault(event_id, set()).add(reference.event_id)
        elif reference.kind is NumericReferenceKind.HEALTH_FIELD:
            assert reference.health_operation_id is not None
            health_event = health_context_event.get(reference.health_operation_id)
            if health_event is not None:
                parents.setdefault(event_id, set()).add(health_event)

    for event in trace.state_events:
        event_parents = parents.setdefault(event.event_id, set())
        if event.kind is StateEventKind.STATE_SLOT_REGISTER:
            if event.slot_id is not None:
                last_slot_event[event.slot_id] = event.event_id

        elif event.kind is StateEventKind.STATE_READ:
            if event.slot_id is not None and event.slot_id in last_slot_event:
                event_parents.add(last_slot_event[event.slot_id])

        elif event.kind is StateEventKind.MAX_HP_READ:
            event_parents.update(event.modifier_eval_ids)

        elif event.kind is StateEventKind.HEALTH_FIELD_BINDING:
            assert event.health_operation_id is not None
            assert event.bound_event_id is not None
            event_parents.add(event.bound_event_id)
            binding_events.setdefault(event.health_operation_id, []).append(
                event.event_id
            )

        elif event.kind is StateEventKind.HEALTH_CONTEXT_ENTER:
            assert event.health_operation_id is not None
            operation = operations[event.health_operation_id]
            event_parents.update(binding_events.get(operation.operation_id, ()))
            previous = previous_health_event_by_target.get(operation.target_index)
            if previous is not None:
                event_parents.add(previous)
            health_context_event[operation.operation_id] = event.event_id
            previous_health_event_by_target[operation.target_index] = event.event_id

        elif event.kind in {
            StateEventKind.NUMERIC_EVAL,
            StateEventKind.MODIFIER_EVAL,
        }:
            for reference in event.inputs:
                add_reference_parent(event.event_id, reference)

        elif event.kind is StateEventKind.STATE_WRITE:
            assert event.slot_id is not None
            for reference in event.inputs:
                add_reference_parent(event.event_id, reference)
            last_slot_event[event.slot_id] = event.event_id

        elif event.kind is StateEventKind.STATE_RESYNC:
            assert event.slot_id is not None
            last_slot_event[event.slot_id] = event.event_id

    pending = [
        event_id
        for hit_plan in hit_plans
        for event_id in hit_plan.bound_modifier_event_ids
    ]
    ancestors: set[str] = set()
    while pending:
        event_id = pending.pop()
        if event_id in ancestors:
            continue
        ancestors.add(event_id)
        pending.extend(parents.get(event_id, ()))
    return frozenset(ancestors)


def _compile_replay_steps(
    trace: StateEvidenceTrace,
) -> tuple[_SupportReplayStep, ...]:
    """Propagate candidate-coordinate reachability through the observed ledger."""

    event_dependencies: dict[str, frozenset[tuple[str, str]]] = {}
    health_dependencies: dict[str, frozenset[tuple[str, str]]] = {}
    binding_dependencies: dict[
        str, dict[str, frozenset[tuple[str, str]]]
    ] = {}
    slot_dependencies: dict[str, frozenset[tuple[str, str]]] = {}
    hp_dependencies_by_target: dict[int, frozenset[tuple[str, str]]] = {}
    operations = {row.operation_id: row for row in trace.health_operations}
    steps: list[_SupportReplayStep] = []

    def reference_dependencies(
        reference: NumericReference,
    ) -> frozenset[tuple[str, str]]:
        if reference.kind is NumericReferenceKind.LITERAL:
            return frozenset()
        if reference.kind is NumericReferenceKind.EVENT:
            assert reference.event_id is not None
            return event_dependencies.get(reference.event_id, frozenset())
        assert reference.health_operation_id is not None
        return health_dependencies.get(reference.health_operation_id, frozenset())

    for event in trace.state_events:
        dependencies: set[tuple[str, str]] = set()
        if event.kind is StateEventKind.STATE_SLOT_REGISTER:
            if event.slot_id is not None:
                slot_dependencies[event.slot_id] = frozenset()

        elif event.kind is StateEventKind.STATE_READ:
            if event.slot_id is not None:
                dependencies.update(
                    slot_dependencies.get(event.slot_id, frozenset())
                )

        elif event.kind is StateEventKind.MAX_HP_READ:
            actor = event.provider.key
            if actor:
                dependencies.update(
                    {
                        (actor, "hp%"),
                        (actor, "hp"),
                        (actor, "max_hp"),
                    }
                )
            for modifier_event_id in event.modifier_eval_ids:
                dependencies.update(
                    event_dependencies.get(modifier_event_id, frozenset())
                )

        elif event.kind is StateEventKind.HEALTH_FIELD_BINDING:
            assert event.health_operation_id is not None
            assert event.key is not None and event.bound_event_id is not None
            dependencies.update(
                event_dependencies.get(event.bound_event_id, frozenset())
            )
            binding_dependencies.setdefault(event.health_operation_id, {})[
                event.key
            ] = frozenset(dependencies)

        elif event.kind is StateEventKind.HEALTH_CONTEXT_ENTER:
            assert event.health_operation_id is not None
            operation = operations[event.health_operation_id]
            for rows in binding_dependencies.get(
                operation.operation_id, {}
            ).values():
                dependencies.update(rows)
            dependencies.update(
                hp_dependencies_by_target.get(operation.target_index, frozenset())
            )
            frozen = frozenset(dependencies)
            health_dependencies[operation.operation_id] = frozen
            hp_dependencies_by_target[operation.target_index] = frozen

        elif event.kind is StateEventKind.NUMERIC_EVAL:
            for reference in event.inputs:
                dependencies.update(reference_dependencies(reference))
            for parameter in event.parameters:
                if parameter.kind is not SourceParameterKind.CANDIDATE_STAT:
                    continue
                assert parameter.actor_key is not None
                assert parameter.stat_key is not None
                if parameter.stat_key == "max_hp":
                    dependencies.update(
                        {
                            (parameter.actor_key, "hp%"),
                            (parameter.actor_key, "hp"),
                            (parameter.actor_key, "max_hp"),
                        }
                    )
                else:
                    dependencies.add(
                        (parameter.actor_key, parameter.stat_key)
                    )

        elif event.kind is StateEventKind.STATE_WRITE:
            assert event.slot_id is not None
            if event.inputs:
                dependencies.update(reference_dependencies(event.inputs[-1]))
                slot_dependencies[event.slot_id] = frozenset(dependencies)
            else:
                dependencies.update(
                    slot_dependencies.get(event.slot_id, frozenset())
                )
                slot_dependencies[event.slot_id] = frozenset()

        elif event.kind is StateEventKind.STATE_RESYNC:
            assert event.slot_id is not None
            dependencies.update(
                slot_dependencies.get(event.slot_id, frozenset())
            )
            slot_dependencies[event.slot_id] = frozenset()

        elif event.kind is StateEventKind.MODIFIER_EVAL:
            for reference in event.inputs:
                dependencies.update(reference_dependencies(reference))

        frozen = frozenset(dependencies)
        event_dependencies[event.event_id] = frozen
        if event.kind in _REPLAY_EVENT_KINDS:
            steps.append(_SupportReplayStep(event=event, dependencies=frozen))
    return tuple(steps)


def _index_replay_events(
    steps: tuple[_SupportReplayStep, ...],
) -> dict[tuple[str, str], tuple[StateEvent, ...]]:
    rows: dict[tuple[str, str], list[StateEvent]] = {}
    for step in steps:
        for coordinate in step.dependencies:
            rows.setdefault(coordinate, []).append(step.event)
    return {coordinate: tuple(events) for coordinate, events in rows.items()}


def _select_replay_events(
    plan: SupportReplayPlan,
    coordinates: frozenset[tuple[str, str]],
) -> tuple[StateEvent, ...]:
    if not coordinates:
        return ()
    if len(coordinates) == 1:
        return plan.replay_events_by_coordinate.get(next(iter(coordinates)), ())
    by_sequence: dict[int, StateEvent] = {}
    for coordinate in coordinates:
        for event in plan.replay_events_by_coordinate.get(coordinate, ()):
            by_sequence[event.sequence_index] = event
    return tuple(by_sequence[index] for index in sorted(by_sequence))


def _validate_hit_modifier_binding(hit, contribution, channel, event: StateEvent) -> None:
    if event.kind is not StateEventKind.MODIFIER_EVAL:
        raise TraceContractError("hit modifier binding must reference modifier_eval")
    if event.channel != channel or event.key != contribution.modifier_key:
        raise TraceContractError("hit modifier binding channel/key mismatch")
    expected_frame = hit.snapshot_frame if channel == "stat" else hit.frame
    if event.frame != expected_frame or event.owner_index != hit.actor_index:
        raise TraceContractError(
            "hit modifier binding snapshot/recipient mismatch: "
            f"hit={hit.event_id!r}/{expected_frame}/{hit.actor_index}, "
            f"event={event.event_id!r}/{event.frame}/{event.owner_index}"
        )
    if event.provider != contribution.provider:
        raise TraceContractError("hit modifier binding provider mismatch")
    if event.accepted is not contribution.accepted:
        raise TraceContractError("hit modifier binding acceptance mismatch")
    observed = (
        {row.stat_key: row.value for row in contribution.values}
        if channel == "stat"
        else {row.stat_key: row.value for row in contribution.delta}
    )
    if set(observed) != set(event.output_map) or any(
        not _close(value, event.output_map[key])
        for key, value in observed.items()
    ):
        raise TraceContractError("hit modifier binding output mismatch")


def _replay_numeric_event(
    trace: StateEvidenceTrace,
    event: StateEvent,
    deltas: Mapping[tuple[str, str], float],
    snapshots: Mapping[str, Mapping[str, float]],
    event_values: Mapping[str, float],
    event_outputs: Mapping[str, Mapping[str, float]],
    health_fields: Mapping[str, Mapping[str, float]],
    uncertainties: set[str],
) -> float:
    assert event.operation is not None and event.value is not None
    operation = event.operation
    if operation == "health_input":
        if event.inputs:
            if len(event.inputs) == 1:
                return _resolve_reference(
                    event.inputs[0], event_values, event_outputs, health_fields
                )
            uncertainties.add(f"frozen_health_input_arity:{event.event_id}")
            return event.value
        if event.source_id is None or event.template_sha256 is None:
            uncertainties.add(f"frozen_health_input_source:{event.event_id}")
            return event.value
        entry = trace.source_manifest_binding.manifest_body.entry_by_id(event.source_id)
        if (
            entry is None
            or entry.template.status is not SourceSliceStatus.SUPPORTED
            or entry.template.template_sha256 != event.template_sha256
        ):
            uncertainties.add(f"frozen_health_input_template:{event.event_id}")
            return event.value
        values: dict[str, float] = {}
        for parameter in event.parameters:
            value = parameter.observed_value
            if parameter.kind is SourceParameterKind.CANDIDATE_STAT:
                assert parameter.actor_key is not None and parameter.stat_key is not None
                value = _candidate_parameter_value(
                    parameter.observed_value,
                    parameter.actor_key,
                    parameter.stat_key,
                    deltas,
                    snapshots,
                )
            elif (
                parameter.kind is SourceParameterKind.FROZEN_RUNTIME_STATE
                and deltas
            ):
                uncertainties.add(
                    f"frozen_runtime_health_parameter:{event.event_id}:{parameter.parameter_key}"
                )
            values[parameter.parameter_key] = value
        try:
            return evaluate_source_template(entry.template, values)
        except (TraceContractError, ZeroDivisionError):
            uncertainties.add(f"frozen_health_input_evaluation:{event.event_id}")
            return event.value

    if operation in {"source_expression", "state_transition"}:
        if any(
            _reference_changed(reference, trace, event_values, event_outputs, health_fields)
            for reference in event.inputs
        ):
            uncertainties.add(f"frozen_numeric_{operation}:{event.event_id}")
        return event.value

    values = tuple(
        _resolve_reference(reference, event_values, event_outputs, health_fields)
        for reference in event.inputs
    )
    if operation == "literal":
        return event.value
    if operation in {"identity", "task_payload"}:
        if len(values) == 1:
            return values[0]
    elif operation == "negate" and len(values) == 1:
        return -values[0]
    elif operation == "add" and values:
        return sum(values)
    elif operation == "multiply" and values:
        result = 1.0
        for value in values:
            result *= value
        if math.isfinite(result):
            return result
    elif operation == "min" and values:
        return min(values)
    elif operation == "max" and values:
        return max(values)
    elif operation == "subtract" and len(values) == 2:
        return values[0] - values[1]
    elif operation == "divide" and len(values) == 2 and values[1] != 0:
        result = values[0] / values[1]
        if math.isfinite(result):
            return result
    uncertainties.add(f"frozen_numeric_evaluation:{event.event_id}")
    return event.value


def _replay_health_operation(
    operation: HealthOperation,
    bindings: Mapping[str, float],
    hp_delta_by_target: dict[int, float],
) -> tuple[dict[str, float], tuple[str, ...]]:
    observed = _observed_health_fields(operation)
    prior_delta = hp_delta_by_target.get(operation.target_index, 0.0)
    changed_binding = any(
        key in observed and not _close(value, observed[key])
        for key, value in bindings.items()
    )
    if not changed_binding and _close(prior_delta, 0.0):
        hp_delta_by_target[operation.target_index] = 0.0
        return observed, ()
    if operation.hp_debt_before != 0 or operation.hp_debt_after != 0:
        return observed, (f"frozen_health_debt:{operation.operation_id}",)

    max_before = bindings.get("max_hp_before", operation.max_hp_before)
    max_after = bindings.get("max_hp_after", operation.max_hp_after)
    hp_before = min(max_before, max(0.0, operation.hp_before + prior_delta))
    input_value = bindings.get("input_value", operation.input_value)
    adjusted = bindings.get("adjusted_input_value", operation.adjusted_input_value)
    if "adjusted_input_value" not in bindings and not _close(operation.input_value, 0.0):
        adjusted = input_value * operation.adjusted_input_value / operation.input_value

    if operation.kind is HealthOperationKind.HEAL:
        if operation.heal_type == "percent":
            base = adjusted * max_before
        elif operation.heal_type == "absolute":
            base = adjusted
        else:
            return observed, (f"frozen_health_type:{operation.operation_id}",)
        if operation.source_bonus is None or operation.heal_bonus_total is None:
            return observed, (f"frozen_health_bonus:{operation.operation_id}",)
        raw = base * (1.0 + operation.source_bonus + operation.heal_bonus_total)
        event_amount = raw
        effective = min(event_amount, max(0.0, max_after - hp_before))
        hp_after = min(max_after, hp_before + effective)
        overheal = max(0.0, event_amount - effective)
    else:
        base = adjusted
        raw = adjusted
        event_amount = adjusted
        effective = min(event_amount, hp_before)
        hp_after = max(0.0, hp_before - effective)
        overheal = 0.0

    candidate = dict(observed)
    candidate.update(
        input_value=input_value,
        adjusted_input_value=adjusted,
        base_amount=base,
        raw_amount=raw,
        event_amount=event_amount,
        event_effective_amount=effective,
        hp_delta_magnitude=effective,
        overheal=overheal,
        max_hp_before=max_before,
        max_hp_after=max_after,
        hp_before=hp_before,
        hp_after=hp_after,
        hp_ratio_before=hp_before / max_before,
        hp_ratio_after=hp_after / max_after,
    )
    hp_delta_by_target[operation.target_index] = hp_after - operation.hp_after
    return candidate, ()


def _candidate_parameter_value(
    observed: float,
    actor_key: str,
    stat_key: str,
    deltas: Mapping[tuple[str, str], float],
    snapshots: Mapping[str, Mapping[str, float]],
) -> float:
    if stat_key == "max_hp":
        snapshot = snapshots.get(actor_key)
        if snapshot is None:
            return observed
        return (
            observed
            + snapshot["base_hp"] * deltas.get((actor_key, "hp%"), 0.0)
            + deltas.get((actor_key, "hp"), 0.0)
            + deltas.get((actor_key, "max_hp"), 0.0)
        )
    return observed + deltas.get((actor_key, stat_key), 0.0)


def _candidate_max_hp_output(
    trace: StateEvidenceTrace,
    event: StateEvent,
    baseline: Mapping[str, float],
    deltas: Mapping[tuple[str, str], float],
    event_outputs: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
    output = dict(baseline)
    actor = event.provider.key
    if not actor or not {"base_hp", "hp%", "hp", "max_hp"}.issubset(output):
        return output
    output["hp%"] += deltas.get((actor, "hp%"), 0.0)
    output["hp"] += deltas.get((actor, "hp"), 0.0)
    for modifier_event_id in event.modifier_eval_ids:
        modifier = trace.state_events[int(modifier_event_id.split(":")[1])]
        baseline_modifier = modifier.output_map
        candidate_modifier = event_outputs.get(modifier_event_id, baseline_modifier)
        for stat_key in ("hp%", "hp"):
            if stat_key in baseline_modifier and stat_key in candidate_modifier:
                output[stat_key] += (
                    candidate_modifier[stat_key] - baseline_modifier[stat_key]
                )
    output["max_hp"] = (
        output["base_hp"] * (1.0 + output["hp%"]) + output["hp"]
        + deltas.get((actor, "max_hp"), 0.0)
    )
    return output


def _max_hp_snapshots(trace: StateEvidenceTrace) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for event in trace.state_events:
        if event.kind is not StateEventKind.MAX_HP_READ or not event.provider.key:
            continue
        output = event.output_map
        if {"base_hp", "hp%", "hp", "max_hp"}.issubset(output):
            result.setdefault(event.provider.key, output)
    return result


def _bound_event_value(
    field_key: str,
    event_id: str,
    event_values: Mapping[str, float],
    event_outputs: Mapping[str, Mapping[str, float]],
) -> float:
    output = event_outputs.get(event_id, {})
    if field_key in output:
        return output[field_key]
    for suffix in ("_before", "_after"):
        if field_key.endswith(suffix):
            base_key = field_key[: -len(suffix)]
            if base_key in output:
                return output[base_key]
    if event_id in event_values:
        return event_values[event_id]
    raise TraceContractError(f"bound event {event_id!r} has no replay value")


def _resolve_reference(
    reference: NumericReference,
    event_values: Mapping[str, float],
    event_outputs: Mapping[str, Mapping[str, float]],
    health_fields: Mapping[str, Mapping[str, float]],
) -> float:
    if reference.kind is NumericReferenceKind.LITERAL:
        assert reference.literal_value is not None
        return reference.literal_value
    if reference.kind is NumericReferenceKind.EVENT:
        assert reference.event_id is not None
        if reference.field_key is not None:
            return event_outputs[reference.event_id][reference.field_key]
        return event_values[reference.event_id]
    assert reference.health_operation_id is not None and reference.field_key is not None
    return health_fields[reference.health_operation_id][reference.field_key]


def _resolve_observed_reference(
    reference: NumericReference,
    trace: StateEvidenceTrace,
) -> float:
    if reference.kind is NumericReferenceKind.LITERAL:
        assert reference.literal_value is not None
        return reference.literal_value
    if reference.kind is NumericReferenceKind.HEALTH_FIELD:
        assert reference.health_operation_id is not None and reference.field_key is not None
        operation = trace.health_operations[int(reference.health_operation_id.split(":")[1])]
        return _observed_health_fields(operation)[reference.field_key]
    assert reference.event_id is not None
    event = trace.state_events[int(reference.event_id.split(":")[1])]
    if reference.field_key is not None:
        return event.output_map[reference.field_key]
    assert event.value is not None
    return event.value


def _reference_changed(
    reference: NumericReference,
    trace: StateEvidenceTrace,
    event_values: Mapping[str, float],
    event_outputs: Mapping[str, Mapping[str, float]],
    health_fields: Mapping[str, Mapping[str, float]],
) -> bool:
    return not _close(
        _resolve_reference(reference, event_values, event_outputs, health_fields),
        _resolve_observed_reference(reference, trace),
    )


def _observed_health_fields(operation: HealthOperation) -> dict[str, float]:
    result: dict[str, float] = {}
    for key in _HEALTH_FIELDS:
        value = getattr(operation, key)
        if value is not None:
            result[key] = float(value)
    return result


def _normalize_deltas(
    values: Mapping[tuple[str, str], float],
) -> dict[tuple[str, str], float]:
    if not isinstance(values, Mapping):
        raise TraceContractError("candidate_stat_deltas must be a mapping")
    result: dict[tuple[str, str], float] = {}
    for key, value in values.items():
        if (
            not isinstance(key, tuple)
            or len(key) != 2
            or not all(isinstance(item, str) and item and item == item.strip() for item in key)
        ):
            raise TraceContractError("candidate delta keys must be (actor_key, stat_key)")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise TraceContractError("candidate delta values must be finite numbers")
        if float(value) != 0.0:
            result[key] = float(value)
    return result


def _materialize_support_replay_result(
    trace: StateEvidenceTrace,
    evaluation: SupportReplayEvaluation,
) -> SupportReplayResult:
    return _result(
        trace,
        evaluation.evidence_sha256,
        evaluation.candidate_stat_deltas,
        evaluation.event_values,
        evaluation.event_outputs,
        evaluation.health_fields,
        evaluation.state_slot_values,
        evaluation.uncertainty_codes,
        evaluation.changed_modifier_event_ids,
        evaluation.replayed_event_count,
    )


def _result(
    trace: StateEvidenceTrace,
    evidence_sha256: str,
    deltas: Mapping[tuple[str, str], float],
    event_values: Mapping[str, float],
    event_outputs: Mapping[str, Mapping[str, float]],
    health_fields: Mapping[str, Mapping[str, float]],
    slot_values: Mapping[str, float],
    uncertainties: set[str],
    changed_modifiers: set[str] | None = None,
    replayed_event_count: int = 0,
) -> SupportReplayResult:
    changed_events = tuple(
        event.event_id
        for event in trace.state_events
        if event.value is not None
        and event.event_id in event_values
        and not _close(event.value, event_values[event.event_id])
    )
    changed_health = tuple(
        operation.operation_id
        for operation in trace.health_operations
        if any(
            key in health_fields[operation.operation_id]
            and not _close(value, health_fields[operation.operation_id][key])
            for key, value in _observed_health_fields(operation).items()
        )
    )
    return SupportReplayResult(
        evidence_sha256=evidence_sha256,
        candidate_stat_deltas=tuple(
            (actor, stat, value)
            for (actor, stat), value in sorted(deltas.items())
        ),
        event_values=tuple(sorted(event_values.items())),
        event_outputs=tuple(
            (event_id, tuple(sorted(output.items())))
            for event_id, output in sorted(event_outputs.items())
        ),
        health_operations=tuple(
            SupportReplayHealthOperation(operation_id, tuple(sorted(fields.items())))
            for operation_id, fields in sorted(
                health_fields.items(), key=lambda item: int(item[0].split(":")[1])
            )
        ),
        state_slot_values=tuple(sorted(slot_values.items())),
        changed_event_ids=changed_events,
        changed_health_operation_ids=changed_health,
        changed_modifier_event_ids=tuple(sorted(changed_modifiers or ())),
        uncertainty_codes=tuple(sorted(uncertainties)),
        replayed_event_count=replayed_event_count,
    )


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)
