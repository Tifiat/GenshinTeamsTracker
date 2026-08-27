"""Frozen selected-to-all fallback orchestration.

The all-database search is a strict superset operation, so it must never start
without first obtaining one exact, confirmed selected-pool account proposal.
This module preserves that two-phase invariant and keeps cancellation attached
to the active fallback session.  It is retained for diagnostics while the
artifact-first shared kernel is built; it is not the release architecture.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
from threading import Event, Lock

from .optimizer_all_set_service import (
    GcsimOptimizerAllSetPlan,
    GcsimOptimizerAllSetResult,
    GcsimOptimizerAllSetSession,
)
from .optimizer_anytime_selected_service import (
    AnytimeSelectedProgressCallback,
    GcsimOptimizerAnytimeSelectedPlan,
    GcsimOptimizerAnytimeSelectedResult,
    GcsimOptimizerAnytimeSelectedSession,
)
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_joint_proposals import GcsimOptimizerJointProposal
from .optimizer_product_contracts import (
    GcsimOptimizerAccountScope,
    GcsimOptimizerOperation,
    GcsimOptimizerTerminalResult,
    GcsimOptimizerTerminalStatus,
)
from .optimizer_run_input import GcsimOptimizerRunInput
from .optimizer_stat_response import GcsimStatResponseTarget


GCSIM_OPTIMIZER_ACCOUNT_SUPERSET_SCHEMA_VERSION = 1


class GcsimOptimizerAccountSupersetError(ValueError):
    """Fail-closed validation or orchestration error."""


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAccountSupersetResult:
    """Typed workflow result, including pre-all cancellation/deadline."""

    selected_result: GcsimOptimizerAnytimeSelectedResult
    all_set_result: GcsimOptimizerAllSetResult
    schema_version: int = GCSIM_OPTIMIZER_ACCOUNT_SUPERSET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_ACCOUNT_SUPERSET_SCHEMA_VERSION:
            raise GcsimOptimizerAccountSupersetError(
                "unsupported account-superset result schema"
            )
        if not isinstance(
            self.selected_result,
            GcsimOptimizerAnytimeSelectedResult,
        ):
            raise GcsimOptimizerAccountSupersetError(
                "selected_result must be a typed anytime selected result"
            )
        if not isinstance(self.all_set_result, GcsimOptimizerAllSetResult):
            raise GcsimOptimizerAccountSupersetError(
                "all_set_result must be a typed all-set result"
            )
        if (
            self.all_set_result.account_result is None
            and self.all_set_result.terminal.status
            in {
                GcsimOptimizerTerminalStatus.CANCELLED,
                GcsimOptimizerTerminalStatus.DEADLINE,
            }
        ):
            if _injected_anchor_count(self.all_set_result) != 0:
                raise GcsimOptimizerAccountSupersetError(
                    "short-circuited all-set result cannot claim an anchor"
                )
        else:
            _require_one_injected_anchor(self.all_set_result)

    @property
    def terminal(self):
        return self.all_set_result.terminal

    @property
    def best_found(self):
        return self.all_set_result.best_found

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "selected_result": self.selected_result.to_dict(),
            "all_set_result": self.all_set_result.to_dict(),
        }


SelectedSessionFactory = Callable[..., object]
AllSetSessionFactory = Callable[..., object]


class GcsimOptimizerAccountSupersetSession:
    """One-shot, cancellable selected-pool then all-database workflow."""

    def __init__(
        self,
        selected_run_input: GcsimOptimizerRunInput,
        all_run_input: GcsimOptimizerRunInput,
        *,
        engine_context: GcsimOptimizerEngineContext,
        prepared_config_text: str,
        selected_plan: GcsimOptimizerAnytimeSelectedPlan | None = None,
        all_set_plan: GcsimOptimizerAllSetPlan | None = None,
        progress_callback: AnytimeSelectedProgressCallback | None = None,
        stat_response_target: GcsimStatResponseTarget | None = None,
        response_master_seed: int | None = None,
        selected_session_factory: SelectedSessionFactory | None = None,
        all_set_session_factory: AllSetSessionFactory | None = None,
    ) -> None:
        self.selected_run_input = selected_run_input
        self.all_run_input = all_run_input
        self.engine_context = engine_context
        self.prepared_config_text = prepared_config_text
        self.selected_plan = selected_plan or GcsimOptimizerAnytimeSelectedPlan()
        self.all_set_plan = all_set_plan or GcsimOptimizerAllSetPlan(
            account_plan=self.selected_plan
        )
        self.progress_callback = progress_callback
        self.stat_response_target = stat_response_target
        self.response_master_seed = response_master_seed
        self.selected_session_factory = (
            selected_session_factory or GcsimOptimizerAnytimeSelectedSession
        )
        self.all_set_session_factory = (
            all_set_session_factory or GcsimOptimizerAllSetSession
        )
        _validate_inputs(
            selected_run_input,
            all_run_input,
            engine_context=engine_context,
            prepared_config_text=prepared_config_text,
        )
        if not isinstance(
            self.selected_plan,
            GcsimOptimizerAnytimeSelectedPlan,
        ):
            raise GcsimOptimizerAccountSupersetError(
                "selected_plan must be a typed anytime selected plan"
            )
        if not isinstance(self.all_set_plan, GcsimOptimizerAllSetPlan):
            raise GcsimOptimizerAccountSupersetError(
                "all_set_plan must be a typed all-set plan"
            )
        if progress_callback is not None and not callable(progress_callback):
            raise GcsimOptimizerAccountSupersetError(
                "progress_callback must be callable"
            )
        if stat_response_target is not None and not isinstance(
            stat_response_target,
            GcsimStatResponseTarget,
        ):
            raise GcsimOptimizerAccountSupersetError(
                "stat_response_target must be typed"
            )
        if (
            stat_response_target is not None
            and stat_response_target.target_sha256
            != selected_run_input.request.source_simulation.target_sha256
        ):
            raise GcsimOptimizerAccountSupersetError(
                "stat_response_target differs from the frozen source target"
            )
        if not callable(self.selected_session_factory):
            raise GcsimOptimizerAccountSupersetError(
                "selected_session_factory must be callable"
            )
        if not callable(self.all_set_session_factory):
            raise GcsimOptimizerAccountSupersetError(
                "all_set_session_factory must be callable"
            )
        self._cancel_event = Event()
        self._lock = Lock()
        self._active: object | None = None
        self._started = False

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            active = self._active
        if active is not None:
            cancel = getattr(active, "cancel", None)
            if not callable(cancel):
                raise GcsimOptimizerAccountSupersetError(
                    "active optimizer phase is not cancellable"
                )
            cancel()

    def run(self) -> GcsimOptimizerAccountSupersetResult:
        with self._lock:
            if self._started:
                raise GcsimOptimizerAccountSupersetError(
                    "account-superset optimizer sessions are one-shot"
                )
            self._started = True

        selected_session = self.selected_session_factory(
            self.selected_run_input,
            engine_context=self.engine_context,
            prepared_config_text=self.prepared_config_text,
            plan=self.selected_plan,
            progress_callback=self.progress_callback,
            stat_response_target=self.stat_response_target,
            response_master_seed=self.response_master_seed,
        )
        selected_result = self._run_phase(selected_session)
        if not isinstance(
            selected_result,
            GcsimOptimizerAnytimeSelectedResult,
        ):
            raise GcsimOptimizerAccountSupersetError(
                "selected phase returned an untyped result"
            )
        if selected_result.run_input_sha256 != (
            self.selected_run_input.run_input_sha256
        ):
            raise GcsimOptimizerAccountSupersetError(
                "selected result belongs to another frozen run input"
            )
        proposal = _selected_terminal_anchor_proposal(selected_result)
        if proposal is None:
            if selected_result.terminal.status in {
                GcsimOptimizerTerminalStatus.CANCELLED,
                GcsimOptimizerTerminalStatus.DEADLINE,
            }:
                return GcsimOptimizerAccountSupersetResult(
                    selected_result=selected_result,
                    all_set_result=self._short_circuit_all_set_result(
                        status=selected_result.terminal.status,
                        stop_reason=(
                            "account_superset_selected_"
                            + selected_result.terminal.status.value
                        ),
                    ),
                )
            raise GcsimOptimizerAccountSupersetError(
                "selected phase produced no confirmed account winner"
            )
        if self._cancel_event.is_set():
            return GcsimOptimizerAccountSupersetResult(
                selected_result=selected_result,
                all_set_result=self._short_circuit_all_set_result(
                    status=GcsimOptimizerTerminalStatus.CANCELLED,
                    stop_reason=(
                        "account_superset_cancelled_before_all_set"
                    ),
                ),
            )

        all_set_session = self.all_set_session_factory(
            self.all_run_input,
            engine_context=self.engine_context,
            prepared_config_text=self.prepared_config_text,
            plan=self.all_set_plan,
            progress_callback=self.progress_callback,
            stat_response_target=self.stat_response_target,
            response_master_seed=self.response_master_seed,
            required_account_anchors=(proposal,),
        )
        all_set_result = self._run_phase(all_set_session)
        if not isinstance(all_set_result, GcsimOptimizerAllSetResult):
            raise GcsimOptimizerAccountSupersetError(
                "all-set phase returned an untyped result"
            )
        if all_set_result.run_input_sha256 != self.all_run_input.run_input_sha256:
            raise GcsimOptimizerAccountSupersetError(
                "all-set result belongs to another frozen run input"
            )
        _require_one_injected_anchor(all_set_result)
        return GcsimOptimizerAccountSupersetResult(
            selected_result=selected_result,
            all_set_result=all_set_result,
        )

    def _run_phase(self, session: object):
        run = getattr(session, "run", None)
        cancel = getattr(session, "cancel", None)
        if not callable(run) or not callable(cancel):
            raise GcsimOptimizerAccountSupersetError(
                "optimizer phase must expose callable run() and cancel()"
            )
        with self._lock:
            self._active = session
            cancelled = self._cancel_event.is_set()
        if cancelled:
            cancel()
        try:
            return run()
        finally:
            with self._lock:
                if self._active is session:
                    self._active = None

    def _short_circuit_all_set_result(
        self,
        *,
        status: GcsimOptimizerTerminalStatus,
        stop_reason: str,
    ) -> GcsimOptimizerAllSetResult:
        terminal = GcsimOptimizerTerminalResult(
            request=self.all_run_input.request,
            status=status,
            stop_reason=stop_reason,
            elapsed_seconds=0.0,
        )
        return GcsimOptimizerAllSetResult(
            terminal=terminal,
            run_input_sha256=self.all_run_input.run_input_sha256,
            plan=self.all_set_plan,
            derived_set_refs=(),
            package_bounds=(),
            package_decisions=(),
            account_result=None,
        )


def run_gcsim_optimizer_account_superset(
    selected_run_input: GcsimOptimizerRunInput,
    all_run_input: GcsimOptimizerRunInput,
    **kwargs,
) -> GcsimOptimizerAccountSupersetResult:
    return GcsimOptimizerAccountSupersetSession(
        selected_run_input,
        all_run_input,
        **kwargs,
    ).run()


def _validate_inputs(
    selected_run_input: GcsimOptimizerRunInput,
    all_run_input: GcsimOptimizerRunInput,
    *,
    engine_context: GcsimOptimizerEngineContext,
    prepared_config_text: str,
) -> None:
    if not isinstance(selected_run_input, GcsimOptimizerRunInput):
        raise GcsimOptimizerAccountSupersetError(
            "selected_run_input must be typed"
        )
    if not isinstance(all_run_input, GcsimOptimizerRunInput):
        raise GcsimOptimizerAccountSupersetError("all_run_input must be typed")
    if not isinstance(engine_context, GcsimOptimizerEngineContext):
        raise GcsimOptimizerAccountSupersetError("engine_context must be typed")
    if not isinstance(prepared_config_text, str) or not prepared_config_text.strip():
        raise GcsimOptimizerAccountSupersetError(
            "prepared_config_text must be non-empty"
        )

    selected_request = selected_run_input.request
    all_request = all_run_input.request
    if (
        selected_request.operation
        is not GcsimOptimizerOperation.ACCOUNT_ARTIFACTS
        or selected_request.account_scope
        is not GcsimOptimizerAccountScope.SELECTED_SET_POOLS
    ):
        raise GcsimOptimizerAccountSupersetError(
            "selected run input must use selected-set account scope"
        )
    if (
        all_request.operation is not GcsimOptimizerOperation.ACCOUNT_ARTIFACTS
        or all_request.account_scope
        is not GcsimOptimizerAccountScope.ALL_DATABASE_SETS
    ):
        raise GcsimOptimizerAccountSupersetError(
            "all run input must use all-database account scope"
        )
    if (
        selected_request.source_simulation.identity_sha256
        != all_request.source_simulation.identity_sha256
    ):
        raise GcsimOptimizerAccountSupersetError(
            "account scopes belong to different source simulations"
        )
    if selected_request.include_2p2p != all_request.include_2p2p:
        raise GcsimOptimizerAccountSupersetError(
            "account scopes use different include_2p2p policies"
        )
    if (
        selected_request.minimum_stat_constraints
        != all_request.minimum_stat_constraints
    ):
        raise GcsimOptimizerAccountSupersetError(
            "account scopes use different minimum-stat constraints"
        )
    if selected_request.four_star_overrides != all_request.four_star_overrides:
        raise GcsimOptimizerAccountSupersetError(
            "account scopes use different four-star overrides"
        )
    if (
        selected_run_input.artifact_database.artifact_database_input_sha256
        != all_run_input.artifact_database.artifact_database_input_sha256
        or selected_run_input.optimizer_artifact_input_sha256
        != all_run_input.optimizer_artifact_input_sha256
    ):
        raise GcsimOptimizerAccountSupersetError(
            "account scopes use different frozen artifact databases"
        )
    if (
        selected_run_input.config_shell.shell_sha256
        != all_run_input.config_shell.shell_sha256
    ):
        raise GcsimOptimizerAccountSupersetError(
            "account scopes use different frozen config shells"
        )
    if (
        selected_run_input.engine_binding_sha256
        != all_run_input.engine_binding_sha256
        or selected_run_input.catalog_fingerprint
        != all_run_input.catalog_fingerprint
        or selected_run_input.engine_binding_sha256
        != engine_context.binding_sha256
        or selected_run_input.catalog_fingerprint
        != engine_context.catalog.source_fingerprint
    ):
        raise GcsimOptimizerAccountSupersetError(
            "account scopes do not share the supplied frozen engine"
        )
    prepared_sha256 = hashlib.sha256(
        prepared_config_text.encode("utf-8")
    ).hexdigest()
    if prepared_sha256 != (
        selected_request.source_simulation.prepared_config_sha256
    ):
        raise GcsimOptimizerAccountSupersetError(
            "prepared config differs from the frozen source simulation"
        )


def _require_one_injected_anchor(result: GcsimOptimizerAllSetResult) -> None:
    count = _injected_anchor_count(result)
    if count != 1:
        raise GcsimOptimizerAccountSupersetError(
            "all-set phase did not retain exactly one injected account anchor"
        )


def _selected_terminal_anchor_proposal(
    result: GcsimOptimizerAnytimeSelectedResult,
) -> GcsimOptimizerJointProposal | None:
    """Resolve the exact proposal backing the selected terminal winner.

    The selected terminal top-N combines confirmed rows from preliminary and
    final races.  Consequently, ``race_result.best_confirmed`` is not
    necessarily the winner exposed to the product.  Match both the typed
    candidate identity and its exact race-evidence identity so the all-set
    phase receives the same physical proposal that selected mode reported.
    """

    winner = result.best_found
    if winner is None:
        return None
    race_evidence_sha256 = winner.evidence_sha256.get("race_evaluation")
    if race_evidence_sha256 is None:
        raise GcsimOptimizerAccountSupersetError(
            "selected terminal winner lacks exact race evidence"
        )

    phases = (
        *result.preliminary_race_results,
        *((result.race_result,) if result.race_result is not None else ()),
    )
    matches: list[GcsimOptimizerJointProposal] = []
    for phase in phases:
        for evaluation in phase.confirmed_evaluations:
            proposal = evaluation.proposal
            if not isinstance(proposal, GcsimOptimizerJointProposal):
                raise GcsimOptimizerAccountSupersetError(
                    "selected confirmed proposal is not typed"
                )
            compiled = proposal.compiled_candidate
            if (
                compiled.candidate_identity_sha256
                != winner.candidate_identity_sha256
                or evaluation.evidence_sha256 != race_evidence_sha256
            ):
                continue
            if (
                compiled.assignment_witness != winner.account_assignment
                or tuple(compiled.targets) != tuple(winner.target_packages)
            ):
                raise GcsimOptimizerAccountSupersetError(
                    "selected terminal winner differs from its typed proposal"
                )
            matches.append(proposal)

    if not matches:
        raise GcsimOptimizerAccountSupersetError(
            "selected terminal winner has no matching confirmed proposal"
        )
    proposal_ids = {proposal.proposal_sha256 for proposal in matches}
    if len(proposal_ids) != 1:
        raise GcsimOptimizerAccountSupersetError(
            "selected terminal winner matches multiple proposal identities"
        )
    return matches[0]


def _injected_anchor_count(result: GcsimOptimizerAllSetResult) -> int:
    return result.terminal.coverage.counters.get(
        "all_set_injected_account_anchor_count",
        0,
    )


__all__ = [
    "GCSIM_OPTIMIZER_ACCOUNT_SUPERSET_SCHEMA_VERSION",
    "GcsimOptimizerAccountSupersetError",
    "GcsimOptimizerAccountSupersetResult",
    "GcsimOptimizerAccountSupersetSession",
    "run_gcsim_optimizer_account_superset",
]
