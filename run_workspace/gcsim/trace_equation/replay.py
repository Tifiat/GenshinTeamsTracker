"""Small seeded replay surface for the trace-equation instrumentation spike.

The API deliberately supports only direct changes to canonical snapshot stats
and the audited normal damage formula.  It never guesses through unsupported
hits or a guard/topology boundary: those candidates receive ``NEEDS_EXACT``
and no authoritative team totals.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .contracts import (
    DamageFormulaKind,
    ProvenanceSourceKind,
    ReactionOperator,
    ReplayAssessment,
    ReplayStatus,
    ScalingKind,
    TraceContractError,
    TraceDamageMode,
    TraceDocument,
    TraceHitEvent,
    ValueReadMode,
    canonical_sha256,
)


SUPPORTED_SNAPSHOT_STAT_KEYS = frozenset(
    {
        "atk",
        "atk%",
        "base_atk",
        "hp",
        "hp%",
        "base_hp",
        "def",
        "def%",
        "base_def",
        "em",
        "cr",
        "cd",
    }
)

_ABS_TOLERANCE = 1e-7
_REL_TOLERANCE = 1e-9


@dataclass(frozen=True, slots=True)
class CandidateStatDelta:
    actor_key: str
    stat_key: str
    amount: float

    def __post_init__(self) -> None:
        _require_trimmed(self.actor_key, "actor_key")
        _require_trimmed(self.stat_key, "stat_key")
        _require_finite(self.amount, "amount")
        if self.stat_key not in SUPPORTED_SNAPSHOT_STAT_KEYS:
            raise TraceContractError(
                f"snapshot stat {self.stat_key!r} is unsupported by replay schema v1"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "actor_key": self.actor_key,
            "stat_key": self.stat_key,
            "amount": self.amount,
        }


@dataclass(frozen=True, slots=True)
class ReplayHitDamage:
    event_id: str
    frame: int
    actor_key: str
    target_key: str
    target_index: int
    uncapped_damage: float
    hp_damage_applied: float
    reported_damage: float
    target_hp_before: float
    target_hp_after: float
    crit: bool
    killed: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "frame": self.frame,
            "actor_key": self.actor_key,
            "target_key": self.target_key,
            "target_index": self.target_index,
            "uncapped_damage": self.uncapped_damage,
            "hp_damage_applied": self.hp_damage_applied,
            "reported_damage": self.reported_damage,
            "target_hp_before": self.target_hp_before,
            "target_hp_after": self.target_hp_after,
            "crit": self.crit,
            "killed": self.killed,
        }


@dataclass(frozen=True, slots=True)
class ReplayActorDamage:
    actor_key: str
    uncapped_damage: float
    hp_damage_applied: float
    reported_damage: float

    def to_dict(self) -> dict[str, object]:
        return {
            "actor_key": self.actor_key,
            "uncapped_damage": self.uncapped_damage,
            "hp_damage_applied": self.hp_damage_applied,
            "reported_damage": self.reported_damage,
        }


@dataclass(frozen=True, slots=True)
class CandidateReplayResult:
    assessment: ReplayAssessment
    hits: tuple[ReplayHitDamage, ...]
    actor_damage: tuple[ReplayActorDamage, ...]
    team_uncapped_damage: float | None
    team_hp_damage_applied: float | None
    team_reported_damage: float | None

    @property
    def exact(self) -> bool:
        return self.assessment.status is ReplayStatus.EXACT_IN_CELL

    def to_dict(self) -> dict[str, object]:
        return {
            "assessment": self.assessment.to_dict(),
            "hits": [hit.to_dict() for hit in self.hits],
            "actor_damage": [row.to_dict() for row in self.actor_damage],
            "team_uncapped_damage": self.team_uncapped_damage,
            "team_hp_damage_applied": self.team_hp_damage_applied,
            "team_reported_damage": self.team_reported_damage,
        }


@dataclass(frozen=True, slots=True)
class TerminalHitSliceReplay:
    """Non-authoritative arithmetic replay of the captured terminal hit slice.

    This result is intentionally separate from :class:`CandidateReplayResult`.
    It can demonstrate that the captured scalar formula replays, even when the
    engine has not traced enough providers/topology to authorize candidate
    ranking.  Callers must never treat these totals as an exact optimizer score.
    """

    candidate_sha256: str
    hits: tuple[ReplayHitDamage, ...]
    actor_damage: tuple[ReplayActorDamage, ...]
    team_uncapped_damage: float | None
    team_hp_damage_applied: float | None
    team_reported_damage: float | None
    reason_codes: tuple[str, ...]
    authoritative: bool = False

    def __post_init__(self) -> None:
        _require_sha256(self.candidate_sha256, "candidate_sha256")
        if self.authoritative:
            raise TraceContractError(
                "terminal hit-slice replay is diagnostic and cannot be authoritative"
            )
        if tuple(sorted(set(self.reason_codes))) != self.reason_codes:
            raise TraceContractError("reason_codes must be sorted and unique")

    @property
    def formula_supported(self) -> bool:
        return not any(code.startswith("hit:") for code in self.reason_codes)

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_sha256": self.candidate_sha256,
            "hits": [hit.to_dict() for hit in self.hits],
            "actor_damage": [row.to_dict() for row in self.actor_damage],
            "team_uncapped_damage": self.team_uncapped_damage,
            "team_hp_damage_applied": self.team_hp_damage_applied,
            "team_reported_damage": self.team_reported_damage,
            "reason_codes": list(self.reason_codes),
            "authoritative": self.authoritative,
        }


def stat_dependency_key(actor_key: str, stat_key: str) -> str:
    """Return the canonical key used by topology guards for a snapshot stat."""

    _require_trimmed(actor_key, "actor_key")
    _require_trimmed(stat_key, "stat_key")
    return f"stat:{actor_key}:{stat_key}"


def replay_candidate_stat_deltas(
    document: TraceDocument,
    deltas: tuple[CandidateStatDelta, ...],
    *,
    candidate_sha256: str | None = None,
) -> CandidateReplayResult:
    """Replay one candidate's canonical snapshot-stat deltas.

    The result is authoritative only when ``result.exact`` is true.  A
    ``NEEDS_EXACT`` result intentionally retains any already-computed hit rows
    for diagnostics but exposes no team/actor total that a search could rank.
    """

    if not isinstance(document, TraceDocument):
        raise TraceContractError("document must be TraceDocument")
    if not isinstance(deltas, tuple):
        raise TraceContractError("deltas must be an immutable tuple")
    for delta in deltas:
        if not isinstance(delta, CandidateStatDelta):
            raise TraceContractError("every delta must be CandidateStatDelta")
    delta_keys = tuple((delta.actor_key, delta.stat_key) for delta in deltas)
    if delta_keys != tuple(sorted(delta_keys)) or len(delta_keys) != len(set(delta_keys)):
        raise TraceContractError("deltas must be sorted by unique actor_key/stat_key")

    if candidate_sha256 is None:
        candidate_sha256 = canonical_sha256(
            {
                "trace_receipt_sha256": document.receipt.receipt_sha256,
                "stat_deltas": [delta.to_dict() for delta in deltas],
            }
        )
    _require_sha256(candidate_sha256, "candidate_sha256")

    changed_by_actor = {
        actor_key: {
            delta.stat_key: delta.amount
            for delta in deltas
            if delta.actor_key == actor_key
        }
        for actor_key in {delta.actor_key for delta in deltas}
    }
    known_actors = set(document.request.character_keys)
    unknown_actors = set(changed_by_actor) - known_actors
    if unknown_actors:
        raise TraceContractError(f"unknown actor keys in deltas: {sorted(unknown_actors)!r}")

    if not document.topology.complete:
        return _needs_exact(
            document,
            candidate_sha256,
            reason_codes=("topology_incomplete",),
        )

    non_exact_hits = tuple(
        hit
        for hit in document.hits
        if hit.formula_replay_status is not ReplayStatus.EXACT_IN_CELL
    )
    if non_exact_hits:
        reasons = tuple(
            sorted(
                {
                    f"hit:{hit.event_id}:{hit.formula_replay_status.value.casefold()}"
                    for hit in non_exact_hits
                }
            )
        )
        return _needs_exact(document, candidate_sha256, reason_codes=reasons)

    actors_with_hits = {hit.actor_key for hit in document.hits}
    no_hit_actors = set(changed_by_actor) - actors_with_hits
    if no_hit_actors:
        return _needs_exact(
            document,
            candidate_sha256,
            reason_codes=tuple(
                f"actor_without_replayable_hit:{actor}" for actor in sorted(no_hit_actors)
            ),
        )

    missing_stats: set[str] = set()
    for actor_key, changes in changed_by_actor.items():
        observed = {
            stat.stat_key
            for hit in document.hits
            if hit.actor_key == actor_key
            for stat in hit.formula_inputs.snapshot_stats
        }
        missing_stats.update(
            f"{actor_key}:{stat_key}"
            for stat_key in changes
            if stat_key not in observed
        )
    if missing_stats:
        return _needs_exact(
            document,
            candidate_sha256,
            reason_codes=tuple(
                f"stat_missing_from_snapshot:{item}" for item in sorted(missing_stats)
            ),
        )

    triggered_guards: set[str] = set()
    guard_reasons: set[str] = set()
    delta_by_dependency = {
        stat_dependency_key(delta.actor_key, delta.stat_key): delta.amount
        for delta in deltas
    }
    for guard in document.topology.guards:
        affected = tuple(
            key for key in guard.dependency_keys if key in delta_by_dependency
        )
        if not affected:
            continue
        if len(affected) != 1 or isinstance(guard.baseline_value, (bool, str)):
            triggered_guards.add(guard.guard_id)
            guard_reasons.add(f"guard_not_replayable:{guard.guard_id}")
            continue
        candidate_value = float(guard.baseline_value) + delta_by_dependency[affected[0]]
        if not guard.predicate.holds(candidate_value):
            triggered_guards.add(guard.guard_id)
            guard_reasons.add(f"guard_crossed:{guard.guard_id}")
    if triggered_guards:
        return _needs_exact(
            document,
            candidate_sha256,
            reason_codes=tuple(sorted(guard_reasons)),
            triggered_guard_ids=tuple(sorted(triggered_guards)),
        )

    target_hp: dict[tuple[int, str], float] = {}
    baseline_target_hp: dict[tuple[int, str], float] = {}
    replayed_hits: list[ReplayHitDamage] = []

    for hit in document.hits:
        target_id = (hit.target_index, hit.target_key)
        if target_id in baseline_target_hp and not _close(
            baseline_target_hp[target_id], hit.target_hp_before
        ):
            return _needs_exact(
                document,
                candidate_sha256,
                reason_codes=(f"target_hp_external_mutation:{hit.event_id}",),
                replayed_hits=tuple(replayed_hits),
            )
        if target_id not in target_hp:
            target_hp[target_id] = hit.target_hp_before

        damage_or_reason = _replay_hit_uncapped(
            hit,
            changed_by_actor.get(hit.actor_key, {}),
        )
        if isinstance(damage_or_reason, str):
            return _needs_exact(
                document,
                candidate_sha256,
                reason_codes=(f"{damage_or_reason}:{hit.event_id}",),
                replayed_hits=tuple(replayed_hits),
            )
        uncapped_damage = damage_or_reason
        if uncapped_damage < 0.0:
            return _needs_exact(
                document,
                candidate_sha256,
                reason_codes=(f"negative_damage:{hit.event_id}",),
                replayed_hits=tuple(replayed_hits),
            )

        hp_before = target_hp[target_id]
        hp_damage_applied = min(uncapped_damage, hp_before)
        hp_after = max(0.0, hp_before - hp_damage_applied)
        killed = (
            _close(hp_after, 0.0)
            if hit.damage_mode is TraceDamageMode.DAMAGE
            else False
        )
        replayed = ReplayHitDamage(
            event_id=hit.event_id,
            frame=hit.frame,
            actor_key=hit.actor_key,
            target_key=hit.target_key,
            target_index=hit.target_index,
            uncapped_damage=uncapped_damage,
            hp_damage_applied=hp_damage_applied,
            reported_damage=(
                hp_damage_applied
                if hit.damage_mode is TraceDamageMode.DAMAGE and killed
                else uncapped_damage
            ),
            target_hp_before=hp_before,
            target_hp_after=hp_after,
            crit=hit.crit,
            killed=killed,
        )
        replayed_hits.append(replayed)
        target_hp[target_id] = hp_after
        baseline_target_hp[target_id] = hit.target_hp_after

        if hit.damage_mode is TraceDamageMode.DAMAGE and killed is not hit.target_killed:
            return _needs_exact(
                document,
                candidate_sha256,
                reason_codes=(f"death_topology_changed:{hit.event_id}",),
                replayed_hits=tuple(replayed_hits),
            )

    actor_uncapped: dict[str, float] = {}
    actor_hp_damage: dict[str, float] = {}
    actor_reported: dict[str, float] = {}
    for hit in replayed_hits:
        actor_uncapped[hit.actor_key] = (
            actor_uncapped.get(hit.actor_key, 0.0) + hit.uncapped_damage
        )
        actor_hp_damage[hit.actor_key] = (
            actor_hp_damage.get(hit.actor_key, 0.0) + hit.hp_damage_applied
        )
        actor_reported[hit.actor_key] = (
            actor_reported.get(hit.actor_key, 0.0) + hit.reported_damage
        )
    actor_damage = tuple(
        ReplayActorDamage(
            actor_key=actor_key,
            uncapped_damage=actor_uncapped[actor_key],
            hp_damage_applied=actor_hp_damage[actor_key],
            reported_damage=actor_reported[actor_key],
        )
        for actor_key in sorted(actor_reported)
    )
    team_uncapped = sum(hit.uncapped_damage for hit in replayed_hits)
    team_hp_damage = sum(hit.hp_damage_applied for hit in replayed_hits)
    team_reported = sum(hit.reported_damage for hit in replayed_hits)
    assessment = ReplayAssessment(
        trace_receipt_sha256=document.receipt.receipt_sha256,
        candidate_sha256=candidate_sha256,
        status=ReplayStatus.EXACT_IN_CELL,
        triggered_guard_ids=(),
        reason_codes=(),
        replayed_hit_count=len(replayed_hits),
    )
    return CandidateReplayResult(
        assessment=assessment,
        hits=tuple(replayed_hits),
        actor_damage=actor_damage,
        team_uncapped_damage=team_uncapped,
        team_hp_damage_applied=team_hp_damage,
        team_reported_damage=team_reported,
    )


def replay_terminal_hit_slice(
    document: TraceDocument,
    deltas: tuple[CandidateStatDelta, ...],
    *,
    candidate_sha256: str | None = None,
) -> TerminalHitSliceReplay:
    """Numerically replay supported terminal formulae without claiming safety.

    The raw engine v1 trace deliberately reports incomplete provider identity
    and topology.  This diagnostic therefore ignores those *global authority*
    gates, but it still refuses unknown formulae, reaction operators, crit-side
    changes, and malformed/missing snapshot inputs.  Successful totals prove
    arithmetic only; ``authoritative`` is permanently ``False``.
    """

    if not isinstance(document, TraceDocument):
        raise TraceContractError("document must be TraceDocument")
    changed_by_actor, candidate_sha256 = _normalize_candidate_inputs(
        document,
        deltas,
        candidate_sha256,
    )

    target_hp: dict[tuple[int, str], float] = {}
    replayed_hits: list[ReplayHitDamage] = []
    reasons: set[str] = {"diagnostic_only_not_authoritative"}
    if not document.topology.complete:
        reasons.add("topology_incomplete")
    if any(not hit.completeness.replay_complete for hit in document.hits):
        reasons.add("provider_or_formula_provenance_incomplete")

    for hit in document.hits:
        target_id = (hit.target_index, hit.target_key)
        if target_id not in target_hp:
            target_hp[target_id] = hit.target_hp_before
        if (
            hit.formula_replay_status is ReplayStatus.UNSUPPORTED
            or hit.formula_inputs.formula_sha256
            != document.request.formula_sha256
        ):
            reasons.add(f"hit:{hit.event_id}:unsupported_formula_identity")
            continue
        damage_or_reason = _replay_hit_uncapped(
            hit,
            changed_by_actor.get(hit.actor_key, {}),
            require_safe_provenance=False,
        )
        if isinstance(damage_or_reason, str):
            reasons.add(f"hit:{hit.event_id}:{damage_or_reason}")
            continue
        uncapped_damage = damage_or_reason
        hp_before = target_hp[target_id]
        hp_damage_applied = min(uncapped_damage, hp_before)
        hp_after = max(0.0, hp_before - hp_damage_applied)
        killed = (
            _close(hp_after, 0.0)
            if hit.damage_mode is TraceDamageMode.DAMAGE
            else False
        )
        replayed_hits.append(
            ReplayHitDamage(
                event_id=hit.event_id,
                frame=hit.frame,
                actor_key=hit.actor_key,
                target_key=hit.target_key,
                target_index=hit.target_index,
                uncapped_damage=uncapped_damage,
                hp_damage_applied=hp_damage_applied,
                reported_damage=(
                    hp_damage_applied
                    if hit.damage_mode is TraceDamageMode.DAMAGE and killed
                    else uncapped_damage
                ),
                target_hp_before=hp_before,
                target_hp_after=hp_after,
                crit=hit.crit,
                killed=killed,
            )
        )
        target_hp[target_id] = hp_after

    if len(replayed_hits) != len(document.hits):
        return TerminalHitSliceReplay(
            candidate_sha256=candidate_sha256,
            hits=tuple(replayed_hits),
            actor_damage=(),
            team_uncapped_damage=None,
            team_hp_damage_applied=None,
            team_reported_damage=None,
            reason_codes=tuple(sorted(reasons)),
        )

    actor_uncapped: dict[str, float] = {}
    actor_hp_damage: dict[str, float] = {}
    actor_reported: dict[str, float] = {}
    for hit in replayed_hits:
        actor_uncapped[hit.actor_key] = (
            actor_uncapped.get(hit.actor_key, 0.0) + hit.uncapped_damage
        )
        actor_hp_damage[hit.actor_key] = (
            actor_hp_damage.get(hit.actor_key, 0.0) + hit.hp_damage_applied
        )
        actor_reported[hit.actor_key] = (
            actor_reported.get(hit.actor_key, 0.0) + hit.reported_damage
        )
    actor_damage = tuple(
        ReplayActorDamage(
            actor_key=actor_key,
            uncapped_damage=actor_uncapped[actor_key],
            hp_damage_applied=actor_hp_damage[actor_key],
            reported_damage=actor_reported[actor_key],
        )
        for actor_key in sorted(actor_uncapped)
    )
    return TerminalHitSliceReplay(
        candidate_sha256=candidate_sha256,
        hits=tuple(replayed_hits),
        actor_damage=actor_damage,
        team_uncapped_damage=sum(hit.uncapped_damage for hit in replayed_hits),
        team_hp_damage_applied=sum(
            hit.hp_damage_applied for hit in replayed_hits
        ),
        team_reported_damage=sum(hit.reported_damage for hit in replayed_hits),
        reason_codes=tuple(sorted(reasons)),
    )


def _replay_hit_uncapped(
    hit: TraceHitEvent,
    changes: dict[str, float],
    *,
    require_safe_provenance: bool = True,
) -> float | str:
    inputs = hit.formula_inputs
    if inputs.known_formula_kind is not DamageFormulaKind.NORMAL:
        return "formula_not_replayable"
    if hit.lineage.known_reaction_operator is not ReactionOperator.NONE:
        return "reaction_operator_not_replayable_v1"
    if inputs.amplifying:
        return "amplifying_reaction_not_replayable_v1"
    if require_safe_provenance and any(
        row.read_mode is ValueReadMode.LIVE
        or row.provider_event_id is not None
        or row.modifier_channel is not None
        or row.source_kind
        in {
            ProvenanceSourceKind.REACTION,
            ProvenanceSourceKind.GADGET,
            ProvenanceSourceKind.OPAQUE_CUSTOM,
        }
        for row in hit.provenance
    ):
        return "dynamic_or_unresolved_provider_not_replayable_v1"

    stats = {row.stat_key: row.value for row in inputs.snapshot_stats}
    for stat_key, amount in changes.items():
        if stat_key not in stats:
            return f"stat_missing_from_hit:{stat_key}"
        stats[stat_key] += amount

    scaling_or_reason = _scaling_value(inputs.scaling_kind, stats)
    if isinstance(scaling_or_reason, str):
        return scaling_or_reason
    scaling_value = scaling_or_reason

    baseline_scaling_or_reason = _scaling_value(
        inputs.scaling_kind,
        {row.stat_key: row.value for row in inputs.snapshot_stats},
    )
    if isinstance(baseline_scaling_or_reason, str):
        return baseline_scaling_or_reason
    if not _close(baseline_scaling_or_reason, inputs.scaling_value.value):
        return "scaling_snapshot_mismatch"

    raw_crit_rate = _require_stat(stats, "cr")
    if isinstance(raw_crit_rate, str):
        return raw_crit_rate
    crit_rate = max(0.0, min(1.0, raw_crit_rate))
    crit_damage = _require_stat(stats, "cd")
    if isinstance(crit_damage, str):
        return crit_damage

    if inputs.hit_weak_point:
        candidate_crit = True
    else:
        if inputs.crit_roll is None:
            return "crit_roll_missing"
        candidate_crit = inputs.crit_roll.value <= crit_rate
    if candidate_crit is not hit.crit:
        return "crit_roll_side_changed"

    base_damage = (
        inputs.mult.value
        * scaling_value
        * (1.0 + inputs.base_dmg_bonus.value)
        + inputs.flat_dmg.value
    )
    damage = base_damage * (1.0 + inputs.dmg_bonus.value)
    damage *= inputs.defense_multiplier.value
    damage *= inputs.resistance_multiplier.value
    if candidate_crit:
        damage *= 1.0 + crit_damage
    if inputs.amplifying:
        em = _require_stat(stats, "em")
        if isinstance(em, str):
            return em
        if em <= -1400.0:
            return "em_formula_domain_crossed"
        em_bonus = (2.78 * em) / (1400.0 + em)
        damage *= inputs.amp_multiplier.value * (
            1.0 + em_bonus + inputs.reaction_bonus.value
        )
    damage *= inputs.group_multiplier.value
    damage *= inputs.elevation_multiplier.value
    if not math.isfinite(damage):
        return "nonfinite_replay_damage"
    if not changes and not _close(damage, hit.uncapped_rolled_damage):
        return "zero_delta_formula_parity_mismatch"
    return damage


def _normalize_candidate_inputs(
    document: TraceDocument,
    deltas: tuple[CandidateStatDelta, ...],
    candidate_sha256: str | None,
) -> tuple[dict[str, dict[str, float]], str]:
    if not isinstance(deltas, tuple):
        raise TraceContractError("deltas must be an immutable tuple")
    for delta in deltas:
        if not isinstance(delta, CandidateStatDelta):
            raise TraceContractError("every delta must be CandidateStatDelta")
    delta_keys = tuple((delta.actor_key, delta.stat_key) for delta in deltas)
    if delta_keys != tuple(sorted(delta_keys)) or len(delta_keys) != len(set(delta_keys)):
        raise TraceContractError("deltas must be sorted by unique actor_key/stat_key")
    changed_by_actor = {
        actor_key: {
            delta.stat_key: delta.amount
            for delta in deltas
            if delta.actor_key == actor_key
        }
        for actor_key in {delta.actor_key for delta in deltas}
    }
    unknown_actors = set(changed_by_actor) - set(document.request.character_keys)
    if unknown_actors:
        raise TraceContractError(f"unknown actor keys in deltas: {sorted(unknown_actors)!r}")
    if candidate_sha256 is None:
        candidate_sha256 = canonical_sha256(
            {
                "trace_receipt_sha256": document.receipt.receipt_sha256,
                "stat_deltas": [delta.to_dict() for delta in deltas],
            }
        )
    _require_sha256(candidate_sha256, "candidate_sha256")
    return changed_by_actor, candidate_sha256


def _scaling_value(
    scaling_kind: ScalingKind,
    stats: dict[str, float],
) -> float | str:
    if scaling_kind is ScalingKind.ELEMENTAL_MASTERY:
        return _require_stat(stats, "em")
    if scaling_kind is ScalingKind.ATTACK:
        prefix = "atk"
    elif scaling_kind is ScalingKind.HP:
        prefix = "hp"
    elif scaling_kind is ScalingKind.DEFENSE:
        prefix = "def"
    else:
        return "unknown_scaling_kind"
    base = _require_stat(stats, f"base_{prefix}")
    flat = _require_stat(stats, prefix)
    percent = _require_stat(stats, f"{prefix}%")
    if isinstance(base, str):
        return base
    if isinstance(flat, str):
        return flat
    if isinstance(percent, str):
        return percent
    return base * (1.0 + percent) + flat


def _require_stat(stats: dict[str, float], key: str) -> float | str:
    if key not in stats:
        return f"required_snapshot_stat_missing:{key}"
    value = stats[key]
    if not math.isfinite(value):
        return f"snapshot_stat_nonfinite:{key}"
    return value


def _needs_exact(
    document: TraceDocument,
    candidate_sha256: str,
    *,
    reason_codes: tuple[str, ...],
    triggered_guard_ids: tuple[str, ...] = (),
    replayed_hits: tuple[ReplayHitDamage, ...] = (),
) -> CandidateReplayResult:
    assessment = ReplayAssessment(
        trace_receipt_sha256=document.receipt.receipt_sha256,
        candidate_sha256=candidate_sha256,
        status=ReplayStatus.NEEDS_EXACT,
        triggered_guard_ids=tuple(sorted(set(triggered_guard_ids))),
        reason_codes=tuple(sorted(set(reason_codes))),
        replayed_hit_count=len(replayed_hits),
    )
    return CandidateReplayResult(
        assessment=assessment,
        hits=replayed_hits,
        actor_damage=(),
        team_uncapped_damage=None,
        team_hp_damage_applied=None,
        team_reported_damage=None,
    )


def _close(left: float, right: float) -> bool:
    return math.isclose(
        left,
        right,
        rel_tol=_REL_TOLERANCE,
        abs_tol=_ABS_TOLERANCE,
    )


def _require_trimmed(value: object, label: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TraceContractError(f"{label} must be a non-empty trimmed string")


def _require_finite(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TraceContractError(f"{label} must be a number")
    if not math.isfinite(float(value)):
        raise TraceContractError(f"{label} must be finite")


def _require_sha256(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or value.casefold() != value
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise TraceContractError(f"{label} must be a lowercase SHA-256 digest")


__all__ = [
    "CandidateReplayResult",
    "CandidateStatDelta",
    "ReplayActorDamage",
    "ReplayHitDamage",
    "SUPPORTED_SNAPSHOT_STAT_KEYS",
    "TerminalHitSliceReplay",
    "replay_candidate_stat_deltas",
    "replay_terminal_hit_slice",
    "stat_dependency_key",
]
