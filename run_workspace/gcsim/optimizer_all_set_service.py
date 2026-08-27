"""Frozen bounded all-database fallback on the package-first anytime kernel.

The old all-set path expanded a broad per-layout response graph and delegated
to the retired selected-pool service.  This boundary now derives every trusted
five-star set from the frozen database, then gives those targets to the same
bounded candidate/no-reuse/race kernel used by selected-set account search.
It remains a best-found diagnostic mode, not an exhaustive set-coverage claim
or the target release architecture.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
import hashlib
import json
from threading import Event, Lock
from time import monotonic

from .artifact_set_catalog import GcsimArtifactSetCapability
from .optimizer_artifact_materializer import (
    compile_gcsim_optimizer_team_candidate,
    materialize_gcsim_optimizer_wearer_build,
)
from .optimizer_anytime_selected_service import (
    AnytimeSelectedProgressCallback,
    GcsimOptimizerAnytimeSelectedPlan,
    GcsimOptimizerAnytimeSelectedResult,
    GcsimOptimizerAnytimeSelectedSession,
)
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_joint_proposals import GcsimOptimizerJointProposal
from .optimizer_lazy_candidates import GcsimOptimizerLazyWearerCandidate
from .optimizer_product_contracts import (
    GcsimOptimizerAccountAssignmentWitness,
    GcsimFourPieceTargetPackage,
    GcsimOptimizerAccountScope,
    GcsimOptimizerCacheCounters,
    GcsimOptimizerCoverageCounters,
    GcsimOptimizerOperation,
    GcsimOptimizerSetReference,
    GcsimOptimizerTerminalResult,
    GcsimOptimizerTerminalStatus,
    GcsimOptimizerTimingCounters,
    GcsimOptimizerWearerSetPool,
    GcsimOptimizerWearerArtifactAssignment,
    GcsimOptimizerWearerTarget,
    GcsimTwoPlusTwoTargetPackage,
)
from .optimizer_run_input import GcsimOptimizerRunInput
from .optimizer_package_feasibility import (
    gcsim_optimizer_account_target_is_physically_feasible,
    gcsim_optimizer_eligible_slots_by_set,
)
from .optimizer_set_impact import (
    GcsimOptimizerSetImpactClassification,
    GcsimOptimizerSetImpactPlan,
    GcsimOptimizerSetImpactResult,
)
from .optimizer_stat_response import GcsimStatResponseTarget


GCSIM_OPTIMIZER_ALL_SET_SCHEMA_VERSION = 6
GCSIM_OPTIMIZER_ALL_SET_PLAN_ID = "all_database_sets_anytime_approx_v3"
GCSIM_OPTIMIZER_ALL_SET_PLAN_VERSION = 10


class GcsimOptimizerAllSetError(ValueError):
    """Fail-closed all-database derivation/orchestration error."""


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAllSetPlan:
    account_plan: GcsimOptimizerAnytimeSelectedPlan = field(
        default_factory=GcsimOptimizerAnytimeSelectedPlan
    )
    set_impact: GcsimOptimizerSetImpactPlan = field(
        default_factory=GcsimOptimizerSetImpactPlan
    )
    response_minimum_iterations: int = 32
    local_refinement_signature_limit: int = 8
    local_refinement_proposals_per_signature: int = 12
    schema_version: int = GCSIM_OPTIMIZER_ALL_SET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if not isinstance(
            self.account_plan,
            GcsimOptimizerAnytimeSelectedPlan,
        ):
            raise GcsimOptimizerAllSetError(
                "account_plan must be an anytime selected plan"
            )
        if not isinstance(self.set_impact, GcsimOptimizerSetImpactPlan):
            raise GcsimOptimizerAllSetError(
                "set_impact must be a typed paired set-impact plan"
            )
        for field_name in (
            "response_minimum_iterations",
            "local_refinement_signature_limit",
            "local_refinement_proposals_per_signature",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise GcsimOptimizerAllSetError(
                    f"{field_name} must be a positive integer"
                )
        if self.response_minimum_iterations > 1024:
            raise GcsimOptimizerAllSetError(
                "response_minimum_iterations must not exceed 1024"
            )
        if self.local_refinement_signature_limit < self.account_plan.top_n:
            raise GcsimOptimizerAllSetError(
                "local refinement must cover every displayable package "
                "signature"
            )

    @property
    def identity_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": GCSIM_OPTIMIZER_ALL_SET_PLAN_ID,
            "plan_version": GCSIM_OPTIMIZER_ALL_SET_PLAN_VERSION,
            "claim": "best_found_under_frozen_budget",
            "account_plan": self.account_plan.to_dict(),
            "set_impact": self.set_impact.to_dict(),
            "response_minimum_iterations": self.response_minimum_iterations,
            "neutral_main_response_policy": "soft_ranking_only",
            "local_refinement_signature_limit": (
                self.local_refinement_signature_limit
            ),
            "local_refinement_proposals_per_signature": (
                self.local_refinement_proposals_per_signature
            ),
            "local_refinement_policy": (
                "confirmed_signatures_structural_main_coordinate_v4"
            ),
            "source_package_anchor_policy": "required_when_resolvable",
            "injected_account_anchor_policy": (
                "exact_rebind_required_through_every_race_tier"
            ),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAllSetPackageBound:
    """Compatibility-shaped evidence row; v3 does not claim numeric bounds."""

    target: GcsimOptimizerWearerTarget
    attainable_score: str | None
    candidate_sha256: str
    response_model_sha256: str
    evidence_sha256: str
    reason: str
    schema_version: int = GCSIM_OPTIMIZER_ALL_SET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if self.attainable_score is not None:
            raise GcsimOptimizerAllSetError(
                "v3 all-set search does not publish numeric package bounds"
            )
        if self.candidate_sha256 or self.response_model_sha256:
            raise GcsimOptimizerAllSetError(
                "unbounded package evidence cannot claim candidate hashes"
            )
        _require_sha256(self.evidence_sha256, "evidence_sha256")
        if not self.reason or self.reason != self.reason.strip():
            raise GcsimOptimizerAllSetError("bound reason must be trimmed")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "target": self.target.to_dict(),
            "attainable_score": None,
            "candidate_sha256": "",
            "response_model_sha256": "",
            "evidence_sha256": self.evidence_sha256,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAllSetPackageDecision:
    target: GcsimOptimizerWearerTarget
    status: str
    reason: str
    evidence_sha256: str
    schema_version: int = GCSIM_OPTIMIZER_ALL_SET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        if self.status not in {
            "inventory_infeasible",
            "probe_negligible",
            "probe_uncertain_retained",
            "probe_positive_retained",
            "candidate_retained",
            "exact_screened",
            "refined",
            "validated",
            "not_completed",
        }:
            raise GcsimOptimizerAllSetError(
                "v3 package decision has unsupported status"
            )
        if not self.reason or self.reason != self.reason.strip():
            raise GcsimOptimizerAllSetError(
                "package decision reason must be trimmed"
            )
        _require_sha256(self.evidence_sha256, "evidence_sha256")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "target": self.target.to_dict(),
            "status": self.status,
            "reason": self.reason,
            "evidence_sha256": self.evidence_sha256,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAllSetResult:
    terminal: GcsimOptimizerTerminalResult
    run_input_sha256: str
    plan: GcsimOptimizerAllSetPlan
    derived_set_refs: tuple[GcsimOptimizerSetReference, ...]
    package_bounds: tuple[GcsimOptimizerAllSetPackageBound, ...]
    package_decisions: tuple[GcsimOptimizerAllSetPackageDecision, ...]
    account_result: GcsimOptimizerAnytimeSelectedResult | None
    schema_version: int = GCSIM_OPTIMIZER_ALL_SET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version)
        _require_sha256(self.run_input_sha256, "run_input_sha256")
        if not isinstance(self.plan, GcsimOptimizerAllSetPlan):
            raise GcsimOptimizerAllSetError("plan must be typed")
        if self.account_result is not None and (
            self.account_result.run_input_sha256 != self.run_input_sha256
            or self.account_result.terminal != self.terminal
        ):
            raise GcsimOptimizerAllSetError(
                "account result differs from all-set terminal"
            )

    @property
    def best_found(self):
        return self.terminal.best_found

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "terminal": self.terminal.to_dict(),
            "run_input_sha256": self.run_input_sha256,
            "plan_sha256": self.plan.identity_sha256,
            "derived_set_refs": [
                item.to_dict() for item in self.derived_set_refs
            ],
            "package_bounds": [
                item.to_dict() for item in self.package_bounds
            ],
            "package_decisions": [
                item.to_dict() for item in self.package_decisions
            ],
            "has_account_result": self.account_result is not None,
        }


class GcsimOptimizerAllSetSession:
    """One-shot owner of bounded all-database account search."""

    def __init__(
        self,
        run_input: GcsimOptimizerRunInput,
        *,
        engine_context: GcsimOptimizerEngineContext,
        prepared_config_text: str,
        plan: GcsimOptimizerAllSetPlan | None = None,
        progress_callback: AnytimeSelectedProgressCallback | None = None,
        cache_store=None,
        enable_cache: bool = True,
        session_factory: Callable[[object], object] | None = None,
        response_discovery: Callable[..., object] | None = None,
        response_master_seed: int | None = None,
        set_impact_discovery: Callable[..., object] | None = None,
        stat_response_target: GcsimStatResponseTarget | None = None,
        environment: Mapping[str, str] | None = None,
        clock: Callable[[], float] = monotonic,
        required_account_anchors: Sequence[
            GcsimOptimizerJointProposal
        ] = (),
    ) -> None:
        if not isinstance(run_input, GcsimOptimizerRunInput):
            raise GcsimOptimizerAllSetError("run_input must be typed")
        if not isinstance(engine_context, GcsimOptimizerEngineContext):
            raise GcsimOptimizerAllSetError("engine_context must be typed")
        self.run_input = run_input
        self.engine_context = engine_context
        self.prepared_config_text = prepared_config_text
        self.plan = plan or GcsimOptimizerAllSetPlan()
        self.progress_callback = progress_callback
        self.cache_store = cache_store
        self.enable_cache = bool(enable_cache)
        self.session_factory = session_factory
        self.response_discovery = response_discovery
        self.response_master_seed = response_master_seed
        self.set_impact_discovery = set_impact_discovery
        self.stat_response_target = stat_response_target
        self.environment = dict(environment or {})
        self.clock = clock
        self.required_account_anchors = tuple(required_account_anchors)
        if any(
            not isinstance(item, GcsimOptimizerJointProposal)
            for item in self.required_account_anchors
        ):
            raise GcsimOptimizerAllSetError(
                "required account anchors must be typed joint proposals"
            )
        if len(
            {item.proposal_sha256 for item in self.required_account_anchors}
        ) != len(self.required_account_anchors):
            raise GcsimOptimizerAllSetError(
                "required account anchor identities must be unique"
            )
        self._cancel_event = Event()
        self._lock = Lock()
        self._active: GcsimOptimizerAnytimeSelectedSession | None = None
        self._started = False

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            active = self._active
        if active is not None:
            active.cancel()

    def run(self) -> GcsimOptimizerAllSetResult:
        with self._lock:
            if self._started:
                raise GcsimOptimizerAllSetError(
                    "all-set optimizer sessions are one-shot"
                )
            self._started = True
        request = self.run_input.request
        if (
            request.operation is not GcsimOptimizerOperation.ACCOUNT_ARTIFACTS
            or request.account_scope
            is not GcsimOptimizerAccountScope.ALL_DATABASE_SETS
        ):
            return self._not_ready("all_set_scope_required")
        set_refs = derive_gcsim_optimizer_all_database_set_refs(self.run_input)
        if not set_refs:
            return self._not_ready("all_set_no_modeled_five_star_package")
        pools = tuple(
            GcsimOptimizerWearerSetPool(wearer, set_refs)
            for wearer in request.source_simulation.wearers
        )
        source_anchor_targets = derive_gcsim_optimizer_source_package_anchor(
            self.run_input,
            set_refs=set_refs,
        )
        rebound_account_anchors = tuple(
            rebind_gcsim_optimizer_account_anchor(
                self.run_input,
                source_proposal=proposal,
            )
            for proposal in self.required_account_anchors
        )
        response_iterations = max(
            self.plan.account_plan.response.iterations,
            self.plan.response_minimum_iterations,
        )
        effective_account_plan = replace(
            self.plan.account_plan,
            response=replace(
                self.plan.account_plan.response,
                iterations=response_iterations,
                worker_count=min(
                    self.plan.account_plan.response.total_cpu_budget,
                    response_iterations,
                ),
            ),
        )
        account_session = GcsimOptimizerAnytimeSelectedSession(
            self.run_input,
            engine_context=self.engine_context,
            prepared_config_text=self.prepared_config_text,
            plan=effective_account_plan,
            progress_callback=self.progress_callback,
            cache_store=self.cache_store,
            enable_cache=self.enable_cache,
            session_factory=self.session_factory,
            response_discovery=self.response_discovery,
            response_master_seed=self.response_master_seed,
            stat_response_target=self.stat_response_target,
            environment=self.environment,
            clock=self.clock,
            target_pools=pools,
            allow_all_database_scope=True,
            boundary_plan_id=GCSIM_OPTIMIZER_ALL_SET_PLAN_ID,
            boundary_plan_version=GCSIM_OPTIMIZER_ALL_SET_PLAN_VERSION,
            boundary_plan_parameters=self.plan.to_dict(),
            neutral_package_response=True,
            enable_set_impact_screening=True,
            set_impact_plan=self.plan.set_impact,
            set_impact_discovery=self.set_impact_discovery,
            soft_main_pruning=True,
            local_refinement_signature_limit=(
                self.plan.local_refinement_signature_limit
            ),
            local_refinement_proposals_per_signature=(
                self.plan.local_refinement_proposals_per_signature
            ),
            required_anchor_targets=source_anchor_targets,
            required_joint_proposals=rebound_account_anchors,
        )
        with self._lock:
            self._active = account_session
        if self._cancel_event.is_set():
            account_session.cancel()
        try:
            account_result = account_session.run()
        finally:
            with self._lock:
                self._active = None
        decisions = _package_decisions(
            pools,
            account_result,
            set_impact_result=account_session.set_impact_result,
            include_2p2p=request.include_2p2p,
        )
        coverage = dict(account_result.terminal.coverage.counters)
        coverage.update(
            {
                "derived_concrete_set_count": len(set_refs),
                "all_set_package_probe_retained_count": sum(
                    item.retained
                    for item in (
                        ()
                        if account_session.set_impact_result is None
                        else account_session.set_impact_result.rows
                    )
                ),
                "all_set_package_candidate_retained_count": sum(
                    item.status
                    in {
                        "candidate_retained",
                        "exact_screened",
                        "refined",
                        "validated",
                    }
                    for item in decisions
                ),
                "all_set_package_exact_screened_count": sum(
                    item.status
                    in {"exact_screened", "refined", "validated"}
                    for item in decisions
                ),
                "all_set_package_refined_count": sum(
                    item.status in {"refined", "validated"}
                    for item in decisions
                ),
                "all_set_package_validated_count": sum(
                    item.status == "validated" for item in decisions
                ),
                "all_set_package_inventory_infeasible_count": sum(
                    item.status == "inventory_infeasible"
                    for item in decisions
                ),
                "all_set_package_probe_negligible_count": sum(
                    item.status == "probe_negligible"
                    for item in decisions
                ),
                "all_set_source_package_anchor_count": (
                    1 if source_anchor_targets else 0
                ),
                "all_set_injected_account_anchor_count": len(
                    rebound_account_anchors
                ),
                "all_set_local_refinement_signature_count": (
                    account_session.local_refinement_signature_count
                ),
                "all_set_local_refinement_candidate_count": (
                    account_session.local_refinement_candidate_count
                ),
                "all_set_local_refinement_proposal_count": (
                    account_session.local_refinement_proposal_count
                ),
            }
        )
        terminal = replace(
            account_result.terminal,
            evidence_sha256={
                **account_result.terminal.evidence_sha256,
                "all_set_plan": self.plan.identity_sha256,
            },
            coverage=GcsimOptimizerCoverageCounters(coverage),
        )
        account_result = replace(account_result, terminal=terminal)
        return GcsimOptimizerAllSetResult(
            terminal=terminal,
            run_input_sha256=self.run_input.run_input_sha256,
            plan=self.plan,
            derived_set_refs=set_refs,
            package_bounds=(),
            package_decisions=decisions,
            account_result=account_result,
        )

    def _not_ready(self, reason: str) -> GcsimOptimizerAllSetResult:
        terminal = GcsimOptimizerTerminalResult(
            request=self.run_input.request,
            status=GcsimOptimizerTerminalStatus.NOT_READY,
            stop_reason=reason,
            elapsed_seconds=0.0,
            evidence_sha256={
                "run_input": self.run_input.run_input_sha256,
                "service_plan": self.plan.identity_sha256,
            },
            cache=GcsimOptimizerCacheCounters(),
            timing=GcsimOptimizerTimingCounters(),
        )
        return GcsimOptimizerAllSetResult(
            terminal=terminal,
            run_input_sha256=self.run_input.run_input_sha256,
            plan=self.plan,
            derived_set_refs=(),
            package_bounds=(),
            package_decisions=(),
            account_result=None,
        )


def run_gcsim_optimizer_all_database_sets(
    run_input: GcsimOptimizerRunInput,
    **kwargs,
) -> GcsimOptimizerAllSetResult:
    return GcsimOptimizerAllSetSession(run_input, **kwargs).run()


def rebind_gcsim_optimizer_account_anchor(
    run_input: GcsimOptimizerRunInput,
    *,
    source_proposal: GcsimOptimizerJointProposal,
) -> GcsimOptimizerJointProposal:
    """Recompile one exact account winner against an all-set request.

    Request hashes legitimately differ between selected-set and all-set runs.
    Reusing the old compiled object would therefore weaken provenance checks;
    regenerating the assignment witness, four materialized builds, and config
    proves that the same twenty physical artifact IDs are attainable in the
    broader frozen space.
    """

    if not isinstance(run_input, GcsimOptimizerRunInput):
        raise GcsimOptimizerAllSetError("run_input must be typed")
    if not isinstance(source_proposal, GcsimOptimizerJointProposal):
        raise GcsimOptimizerAllSetError(
            "source account anchor must be a typed joint proposal"
        )
    if (
        run_input.request.operation
        is not GcsimOptimizerOperation.ACCOUNT_ARTIFACTS
        or run_input.request.account_scope
        is not GcsimOptimizerAccountScope.ALL_DATABASE_SETS
    ):
        raise GcsimOptimizerAllSetError(
            "account anchors can only be rebound to all-set account runs"
        )
    source_rows = tuple(source_proposal.wearer_candidates)
    if tuple(
        row.target.wearer.team_slot for row in source_rows
    ) != (1, 2, 3, 4):
        raise GcsimOptimizerAllSetError(
            "source account anchor must cover canonical slots 1..4"
        )

    response_model_sha256 = _canonical_sha256(
        {
            "policy": "exact_injected_account_anchor_v1",
            "run_input_sha256": run_input.run_input_sha256,
            "source_proposal_sha256": source_proposal.proposal_sha256,
        }
    )
    wearer_candidates = []
    for source_row, wearer in zip(
        source_rows,
        run_input.request.source_simulation.wearers,
        strict=True,
    ):
        if (
            source_row.target.wearer.team_slot != wearer.team_slot
            or source_row.target.wearer.gcsim_character_key
            != wearer.gcsim_character_key
        ):
            raise GcsimOptimizerAllSetError(
                "source account anchor belongs to another frozen team"
            )
        target = GcsimOptimizerWearerTarget(
            wearer=wearer,
            package=source_row.target.package,
        )
        assignment = GcsimOptimizerWearerArtifactAssignment(
            wearer=wearer,
            artifact_ids_by_slot=(
                source_row.assignment.artifact_ids_by_slot
            ),
        )
        materialized = materialize_gcsim_optimizer_wearer_build(
            run_input,
            assignment=assignment,
            target=target,
        )
        if not materialized.ready or materialized.build is None:
            reason = ", ".join(
                item.code for item in materialized.diagnostics
            ) or "unknown_materialization_failure"
            raise GcsimOptimizerAllSetError(
                "injected account anchor is not attainable in all-set "
                f"scope: {reason}"
            )
        build = materialized.build
        if isinstance(target.package, GcsimFourPieceTargetPackage):
            target_uid = target.package.set_ref.set_uid
            offpieces = tuple(
                slot
                for slot, artifact in build.artifacts_by_slot
                if artifact.set_uid != target_uid
            )
            offpiece_shape = "5p" if not offpieces else offpieces[0]
        else:
            offpiece_shape = "2p2p"
        candidate_payload = {
            "policy": "exact_injected_account_anchor_v1",
            "run_input_sha256": run_input.run_input_sha256,
            "source_candidate_sha256": source_row.candidate_sha256,
            "target": target.to_dict(),
            "assignment": assignment.to_dict(),
            "wearer_build_identity_sha256": (
                build.wearer_build_identity_sha256
            ),
        }
        wearer_candidates.append(
            GcsimOptimizerLazyWearerCandidate(
                target=target,
                response_model_sha256=response_model_sha256,
                assignment=assignment,
                materialized_build=build,
                proposal_score=source_row.proposal_score,
                crit_value=source_row.crit_value,
                offpiece_shape=offpiece_shape,
                feature_labels=tuple(
                    sorted(
                        {
                            *source_row.feature_labels,
                            "required_external_anchor",
                            "source_selected_winner",
                        }
                    )
                ),
                content_fingerprint=build.compiled_block_sha256,
                candidate_sha256=_canonical_sha256(candidate_payload),
            )
        )

    witness = GcsimOptimizerAccountAssignmentWitness(
        request_sha256=run_input.request.request_sha256,
        artifact_database_input_sha256=(
            run_input.artifact_database.artifact_database_input_sha256
        ),
        wearer_assignments=tuple(
            item.assignment for item in wearer_candidates
        ),
    )
    execution_identity_sha256 = _canonical_sha256(
        {
            "policy": "exact_injected_account_anchor_v1",
            "run_input_sha256": run_input.run_input_sha256,
            "source_proposal_sha256": source_proposal.proposal_sha256,
        }
    )
    compiled = compile_gcsim_optimizer_team_candidate(
        run_input,
        assignment_witness=witness,
        targets=tuple(item.target for item in wearer_candidates),
        execution_identity_sha256=execution_identity_sha256,
    )
    if not compiled.ready or compiled.candidate is None:
        reason = ", ".join(
            item.code for item in compiled.diagnostics
        ) or "unknown_compilation_failure"
        raise GcsimOptimizerAllSetError(
            f"could not compile injected account anchor: {reason}"
        )
    proposal_payload = {
        "policy": "exact_injected_account_anchor_v1",
        "run_input_sha256": run_input.run_input_sha256,
        "source_proposal_sha256": source_proposal.proposal_sha256,
        "candidate_identity_sha256": (
            compiled.candidate.candidate_identity_sha256
        ),
        "wearer_candidate_sha256s": [
            item.candidate_sha256 for item in wearer_candidates
        ],
    }
    return GcsimOptimizerJointProposal(
        wearer_candidates=tuple(wearer_candidates),
        compiled_candidate=compiled.candidate,
        surrogate_score=source_proposal.surrogate_score,
        changed_wearer_count=source_proposal.changed_wearer_count,
        diversity_labels=tuple(
            sorted(
                {
                    *source_proposal.diversity_labels,
                    "required_external_anchor",
                    "source_selected_winner",
                }
            )
        ),
        proposal_sha256=_canonical_sha256(proposal_payload),
    )


def derive_gcsim_optimizer_all_database_set_refs(
    run_input: GcsimOptimizerRunInput,
) -> tuple[GcsimOptimizerSetReference, ...]:
    """Derive mapped, modeled five-star sets from frozen database rows."""

    if not isinstance(run_input, GcsimOptimizerRunInput):
        raise GcsimOptimizerAllSetError("run_input must be typed")
    mapped: dict[str, str] = {}
    slots_by_set = gcsim_optimizer_eligible_slots_by_set(run_input)
    for artifact in run_input.artifact_database.artifacts:
        if not artifact.default_eligible or artifact.set_mapping_status != "ready":
            continue
        capability = run_input.set_capability(artifact.gcsim_set_key)
        if not _five_star_search_ready(
            capability,
            include_2p2p=run_input.request.include_2p2p,
        ):
            continue
        slot_count = len(slots_by_set.get(artifact.set_uid, ()))
        if not (
            (
                capability is not None
                and capability.optimizer_four_piece_ready
                and slot_count >= 4
            )
            or (
                run_input.request.include_2p2p
                and capability is not None
                and capability.two_piece_modeled
                and slot_count >= 2
            )
        ):
            continue
        previous = mapped.setdefault(artifact.set_uid, artifact.gcsim_set_key)
        if previous != artifact.gcsim_set_key:
            raise GcsimOptimizerAllSetError(
                "one concrete set_uid maps to multiple GCSIM keys"
            )
    return tuple(
        GcsimOptimizerSetReference(
            set_uid=set_uid,
            gcsim_set_key=mapped[set_uid],
            engine_binding_sha256=run_input.engine_binding_sha256,
            catalog_fingerprint=run_input.catalog_fingerprint,
            set_parameters={},
        )
        for set_uid in sorted(mapped)
    )


def derive_gcsim_optimizer_source_package_anchor(
    run_input: GcsimOptimizerRunInput,
    *,
    set_refs: Sequence[GcsimOptimizerSetReference] | None = None,
) -> tuple[GcsimOptimizerWearerTarget, ...]:
    """Resolve the source config's package combination, never its equipment.

    This is a quality-control package signature only.  Physical artifact
    assignments are rebuilt from the complete frozen database by the same
    local refinement kernel as every other shortlisted signature.
    """

    if not isinstance(run_input, GcsimOptimizerRunInput):
        raise GcsimOptimizerAllSetError("run_input must be typed")
    refs = tuple(
        derive_gcsim_optimizer_all_database_set_refs(run_input)
        if set_refs is None
        else set_refs
    )
    by_key: dict[str, list[GcsimOptimizerSetReference]] = {}
    for set_ref in refs:
        by_key.setdefault(set_ref.gcsim_set_key.casefold(), []).append(set_ref)
    suggestions_by_slot = {
        slot: tuple(
            item
            for item in run_input.config_shell.source_set_suggestions
            if item.wearer.team_slot == slot and item.mapping_status == "ready"
        )
        for slot in (1, 2, 3, 4)
    }
    targets: list[GcsimOptimizerWearerTarget] = []
    for wearer in run_input.request.source_simulation.wearers:
        suggestions = suggestions_by_slot[wearer.team_slot]
        package_candidates = []
        for suggestion in suggestions:
            if suggestion.source_count < 4:
                continue
            for set_ref in by_key.get(
                suggestion.gcsim_set_key.casefold(),
                (),
            ):
                package_candidates.append(
                    GcsimFourPieceTargetPackage(set_ref)
                )
        if run_input.request.include_2p2p:
            two_piece_refs = tuple(
                set_ref
                for suggestion in suggestions
                if suggestion.source_count >= 2
                for set_ref in by_key.get(
                    suggestion.gcsim_set_key.casefold(),
                    (),
                )
            )
            package_candidates.extend(
                GcsimTwoPlusTwoTargetPackage(left, right)
                for left_index, left in enumerate(two_piece_refs)
                for right in two_piece_refs[left_index + 1 :]
                if left.gcsim_set_key.casefold()
                != right.gcsim_set_key.casefold()
            )
        target = next(
            (
                GcsimOptimizerWearerTarget(wearer, package)
                for package in package_candidates
                if gcsim_optimizer_account_target_is_physically_feasible(
                    run_input,
                    GcsimOptimizerWearerTarget(wearer, package),
                )
            ),
            None,
        )
        if target is None:
            return ()
        targets.append(target)
    return tuple(targets)


def _five_star_search_ready(
    capability: GcsimArtifactSetCapability | None,
    *,
    include_2p2p: bool,
) -> bool:
    return bool(
        capability is not None
        and capability.registered
        and capability.max_rarity == 5
        and (
            capability.optimizer_four_piece_ready
            or (include_2p2p and capability.two_piece_modeled)
        )
    )


def _package_decisions(
    pools: Sequence[GcsimOptimizerWearerSetPool],
    result: GcsimOptimizerAnytimeSelectedResult,
    *,
    set_impact_result: GcsimOptimizerSetImpactResult | None,
    include_2p2p: bool,
) -> tuple[GcsimOptimizerAllSetPackageDecision, ...]:
    race_phases = (
        *result.preliminary_race_results,
        *((result.race_result,) if result.race_result is not None else ()),
    )
    retained = {
        _target_key(candidate.target)
        for pool in result.wearer_pools
        for candidate in pool.candidates
    }
    impact_by_key = (
        {}
        if set_impact_result is None
        else {
            _target_key(item.target): item
            for item in set_impact_result.rows
        }
    )
    exact_screened = {
        key
        for phase in race_phases
        for evaluation in phase.trace_evaluations
        if evaluation.tier_id == "screen_8"
        for key in _proposal_coverage_keys(evaluation.proposal)
    }
    refined = {
        key
        for phase in race_phases
        for evaluation in phase.trace_evaluations
        if evaluation.tier_id == "refine_32"
        for key in _proposal_coverage_keys(evaluation.proposal)
    }
    validated = {
        key
        for phase in race_phases
        for evaluation in phase.confirmed_evaluations
        for key in _proposal_coverage_keys(evaluation.proposal)
    }
    marginal_uncovered = set(
        ()
        if result.joint_coverage is None
        else result.joint_coverage.marginal_uncovered_targets
    )
    interrupted = result.terminal.status in {
        GcsimOptimizerTerminalStatus.CANCELLED,
        GcsimOptimizerTerminalStatus.DEADLINE,
        GcsimOptimizerTerminalStatus.FAILED,
    }
    decisions = []
    for pool in pools:
        packages = [
            GcsimFourPieceTargetPackage(set_ref)
            for set_ref in pool.allowed_sets
        ]
        if include_2p2p:
            packages.extend(
                GcsimTwoPlusTwoTargetPackage(left, right)
                for left_index, left in enumerate(pool.allowed_sets)
                for right in pool.allowed_sets[left_index + 1 :]
                if left.gcsim_set_key.casefold()
                != right.gcsim_set_key.casefold()
            )
        for package in packages:
            target = GcsimOptimizerWearerTarget(pool.wearer, package)
            key = _target_key(target)
            is_retained = key in retained
            impact = impact_by_key.get(key)
            if key in validated:
                status = "validated"
                reason = "package_reached_confirmed_race_fidelity"
            elif key in refined:
                status = "refined"
                reason = "package_reached_32_iteration_refinement"
            elif key in exact_screened:
                status = "exact_screened"
                reason = "strongest_physical_package_build_reached_exact_screen"
            elif key in marginal_uncovered:
                status = (
                    "not_completed" if interrupted else "inventory_infeasible"
                )
                reason = (
                    result.terminal.stop_reason
                    if interrupted
                    else "retained_package_has_no_disjoint_exact_team"
                )
            elif impact is not None and impact.retained and not is_retained:
                status = (
                    "not_completed" if interrupted else "inventory_infeasible"
                )
                reason = (
                    result.terminal.stop_reason
                    if interrupted
                    else "retained_package_has_no_exact_physical_build"
                )
            elif is_retained:
                status = "candidate_retained"
                reason = "strongest_physical_package_candidate_retained"
            elif impact is None:
                status = (
                    "not_completed" if interrupted else "inventory_infeasible"
                )
                reason = (
                    result.terminal.stop_reason
                    if interrupted
                    else "package_cannot_fill_required_distinct_slots"
                )
            elif not impact.retained:
                status = "probe_negligible"
                reason = "paired_set_impact_proved_no_material_gain"
            elif (
                impact.classification
                is GcsimOptimizerSetImpactClassification.UNCERTAIN_RETAINED
            ):
                status = "probe_uncertain_retained"
                reason = "paired_set_impact_uncertain_and_conservatively_retained"
            else:
                status = "probe_positive_retained"
                reason = "paired_set_impact_measured_personal_or_team_gain"
            decisions.append(
                GcsimOptimizerAllSetPackageDecision(
                    target=target,
                    status=status,
                    reason=reason,
                    evidence_sha256=_canonical_sha256(
                        {
                            "target": target.to_dict(),
                            "status": status,
                            "reason": reason,
                        }
                    ),
                )
            )
    return tuple(decisions)


def _target_key(target: GcsimOptimizerWearerTarget) -> tuple[int, str]:
    return target.wearer.team_slot, target.package.identity_sha256


def _marginal_coverage_keys(proposal) -> tuple[tuple[int, str], ...]:
    prefix = "marginal_package_coverage:"
    rows = []
    for label in proposal.diversity_labels:
        if not label.startswith(prefix):
            continue
        payload = label.removeprefix(prefix)
        slot_text, separator, package_sha256 = payload.partition(":")
        if (
            separator != ":"
            or slot_text not in {"1", "2", "3", "4"}
        ):
            raise GcsimOptimizerAllSetError(
                "malformed marginal package coverage label"
            )
        _require_sha256(
            package_sha256,
            "marginal_package_coverage.package_sha256",
        )
        rows.append((int(slot_text), package_sha256))
    if len(set(rows)) != len(rows):
        raise GcsimOptimizerAllSetError(
            "duplicate marginal package coverage label"
        )
    return tuple(sorted(rows))


def _proposal_coverage_keys(proposal) -> tuple[tuple[int, str], ...]:
    """Return both exact worn packages and explicit marginal witnesses."""

    exact = {
        _target_key(build.target)
        for build in proposal.compiled_candidate.builds
    }
    return tuple(sorted(exact | set(_marginal_coverage_keys(proposal))))


def _canonical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _require_sha256(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise GcsimOptimizerAllSetError(
            f"{field_name} must be lowercase SHA-256"
        )


def _require_schema(value: int) -> None:
    if value != GCSIM_OPTIMIZER_ALL_SET_SCHEMA_VERSION:
        raise GcsimOptimizerAllSetError(
            "unsupported all-set optimizer schema"
        )


__all__ = [
    "GCSIM_OPTIMIZER_ALL_SET_PLAN_ID",
    "GCSIM_OPTIMIZER_ALL_SET_PLAN_VERSION",
    "GCSIM_OPTIMIZER_ALL_SET_SCHEMA_VERSION",
    "GcsimOptimizerAllSetError",
    "GcsimOptimizerAllSetPackageBound",
    "GcsimOptimizerAllSetPackageDecision",
    "GcsimOptimizerAllSetPlan",
    "GcsimOptimizerAllSetResult",
    "GcsimOptimizerAllSetSession",
    "derive_gcsim_optimizer_all_database_set_refs",
    "derive_gcsim_optimizer_source_package_anchor",
    "rebind_gcsim_optimizer_account_anchor",
    "run_gcsim_optimizer_all_database_sets",
]
