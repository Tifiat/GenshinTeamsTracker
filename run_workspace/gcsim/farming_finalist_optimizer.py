"""Bounded upstream substat-optimizer race for theoretical 4p finalists.

This is deliberately the *last* theoretical farming stage.  It accepts only a
small, already-ranked collection of :class:`FullTeamPhysicalState` values,
materializes their exact sets and main stats, runs upstream ``substatOptim``
sequentially, and ranks the successful optimized simulations.  It does not
turn the preceding heuristic search into a global optimum proof.

The boundary is intentionally strict: one static high-HP target, canonical
wearer order, catalog-backed 4p/off-piece choices, an explicit validation
iteration count, one CPU-worker budget, one wall-clock deadline, and complete
content hashes for every reproducible input and successful optimizer output.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import re
from threading import Event, Lock, Timer
from time import monotonic
from types import MappingProxyType
from typing import Protocol

from .artifact_runner import (
    GcsimResultParseError,
    GcsimResultSummary,
    parse_gcsim_result_payload,
)
from .farming_pipeline import (
    GcsimFarmingPipelineError,
    _normalize_layout_catalog,
    _require_trusted_engine_context,
    _validated_prepared_config,
    _validated_wearer_ids,
)
from .farming_profile_config import (
    DEFAULT_FIXED_SUBSTATS_COUNT,
    DEFAULT_INDIVIDUAL_LIQUID_CAP,
    DEFAULT_TOTAL_LIQUID_SUBSTATS,
    FOUR_STAR_LIQUID_ROLL_PENALTY,
    FOUR_STAR_RARITY_PENALTY,
    GCSIM_SUBSTAT_ROLL_VALUES,
    apply_gcsim_screening_runtime_options,
)
from .farming_team_search import FullTeamPhysicalState
from .optimizer_backend import (
    GcsimBoundOptimizerCandidate,
    GcsimBoundOptimizerError,
    prepare_bound_gcsim_four_piece_optimizer_candidate,
    resolve_gcsim_optimizer_worker_count,
)
from .optimizer_config import GcsimFiveStarMainStatLayout
from .optimizer_cache import build_gcsim_optimizer_cache_identity_from_sha256
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_runner import (
    DEFAULT_GCSIM_OPTIMIZED_CONFIG_FILENAME,
    DEFAULT_GCSIM_OPTIMIZER_INPUT_FILENAME,
    DEFAULT_GCSIM_OPTIMIZER_RESULT_FILENAME,
    GcsimOptimizerRunRequest,
    GcsimOptimizerRunResult,
    GcsimOptimizerRunStatus,
    GcsimOptimizerSession,
    GcsimOptimizerSessionStatus,
    GcsimOptimizerStageName,
    GcsimOptimizerStageStatus,
    freeze_gcsim_optimizer_environment,
    format_gcsim_optimizer_options,
    normalize_gcsim_optimizer_frozen_environment,
)


GCSIM_FINALIST_OPTIMIZER_PROVENANCE_SCHEMA = 1
GCSIM_FINALIST_OPTIMIZER_MODE = "theoretical_4p_finalist_optimizer"

_ADD_STATS_RE = re.compile(
    r"^\s*(?P<wearer>[a-z]+)\s+add\s+stats\b(?P<body>[^;]*);\s*$",
    re.IGNORECASE,
)
_MAIN_STATS_RE = re.compile(
    r"^\s*(?P<wearer>[a-z]+)\s+add\s+stats\s+hp=(?:4780|3571)\b[^;]*;\s*$",
    re.IGNORECASE,
)
_SUBSTAT_TERM_RE = re.compile(
    r"^(?P<key>hp%|atk%|def%|hp|atk|def|er|em|cr|cd)="
    r"(?P<value>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"(?:\*(?P<count>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?))?$"
)
_ANY_SET_RE = re.compile(
    r"^\s*(?P<wearer>[a-z]+)\s+add\s+set\b[^;]*;\s*$",
    re.IGNORECASE,
)
_EXACT_SET_RE = re.compile(
    r'^\s*(?P<wearer>[a-z]+)\s+add\s+set\s*=\s*"'
    r'(?P<set>[a-z0-9]+)"\s+count\s*=\s*4\s*;\s*$',
    re.IGNORECASE,
)


class GcsimFinalistOptimizerError(RuntimeError):
    """Raised when a finalist request or returned evidence is incoherent."""


class GcsimFinalistOptimizerStatus(str, Enum):
    BEST_FOUND = "best_found"
    CANCELLED = "cancelled"
    DEADLINE = "deadline"
    NO_SUCCESS = "no_success"


class GcsimFinalistAttemptStatus(str, Enum):
    PASSED = "passed"
    MATERIALIZATION_FAILED = "materialization_failed"
    SESSION_FACTORY_FAILED = "session_factory_failed"
    RUN_FAILED = "run_failed"
    RESULT_REJECTED = "result_rejected"


@dataclass(frozen=True, slots=True)
class GcsimFinalistOptimizerBudget:
    """Hard bounds for one sequential finalist race."""

    max_finalists: int
    top_n: int
    worker_count: int
    validation_iterations: int
    overall_deadline_seconds: float
    optimizer_timeout_seconds: float
    simulation_timeout_seconds: float

    def __post_init__(self) -> None:
        for field_name in (
            "max_finalists",
            "top_n",
            "worker_count",
            "validation_iterations",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise GcsimFinalistOptimizerError(
                    f"{field_name} must be a positive integer"
                )
        if self.top_n > self.max_finalists:
            raise GcsimFinalistOptimizerError(
                "top_n cannot exceed max_finalists"
            )
        try:
            resolved_workers = resolve_gcsim_optimizer_worker_count(self.worker_count)
        except GcsimBoundOptimizerError as exc:
            raise GcsimFinalistOptimizerError(str(exc)) from exc
        if resolved_workers != self.worker_count:
            raise GcsimFinalistOptimizerError(
                "worker_count did not resolve to the requested CPU budget"
            )
        for field_name in (
            "overall_deadline_seconds",
            "optimizer_timeout_seconds",
            "simulation_timeout_seconds",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise GcsimFinalistOptimizerError(
                    f"{field_name} must be finite and positive"
                )


@dataclass(frozen=True, slots=True)
class GcsimFinalistOptimizerRequest:
    """Deep-frozen inputs for a bounded race over upstream-search finalists."""

    engine_context: GcsimOptimizerEngineContext
    prepared_config_text: str
    wearer_ids: tuple[str, ...]
    layout_catalog: Mapping[
        str,
        Mapping[str, GcsimFiveStarMainStatLayout],
    ]
    finalists: tuple[FullTeamPhysicalState, ...]
    budget: GcsimFinalistOptimizerBudget
    optimizer_options: Mapping[str, int | float] = field(default_factory=dict)
    environment: Mapping[str, str] = field(default_factory=dict, repr=False)
    environment_is_frozen: bool = field(default=False, repr=False, compare=False)
    validation_config_text: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.budget, GcsimFinalistOptimizerBudget):
            raise GcsimFinalistOptimizerError(
                "budget must be a GcsimFinalistOptimizerBudget"
            )
        try:
            _require_trusted_engine_context(self.engine_context)
            wearer_ids = _validated_wearer_ids(self.wearer_ids)
            prepared_config = _validated_prepared_config(
                self.prepared_config_text,
                wearer_ids,
            )
            normalized_layouts = _normalize_layout_catalog(
                self.layout_catalog,
                wearer_ids,
            )
            validation_config = apply_gcsim_screening_runtime_options(
                prepared_config,
                iterations=self.budget.validation_iterations,
                workers=self.budget.worker_count,
            )
            _validated_prepared_config(validation_config, wearer_ids)
        except (GcsimFarmingPipelineError, ValueError) as exc:
            raise GcsimFinalistOptimizerError(str(exc)) from exc

        if isinstance(self.finalists, (str, bytes)):
            raise GcsimFinalistOptimizerError("finalists must be a sequence")
        try:
            finalists = tuple(self.finalists)
        except TypeError as exc:
            raise GcsimFinalistOptimizerError(
                "finalists must be an iterable of FullTeamPhysicalState values"
            ) from exc
        if not finalists:
            raise GcsimFinalistOptimizerError("finalists must not be empty")
        if len(finalists) > self.budget.max_finalists:
            raise GcsimFinalistOptimizerError(
                "finalist count exceeds the frozen max_finalists budget"
            )
        if any(not isinstance(state, FullTeamPhysicalState) for state in finalists):
            raise GcsimFinalistOptimizerError(
                "finalists must contain only FullTeamPhysicalState values"
            )
        if len({state.key for state in finalists}) != len(finalists):
            raise GcsimFinalistOptimizerError("finalists must be physically unique")

        for state in finalists:
            if tuple(choice.wearer_id for choice in state.choices) != wearer_ids:
                raise GcsimFinalistOptimizerError(
                    "every finalist must match wearer_ids in exact canonical order"
                )
            for choice in state.choices:
                wearer_layouts = normalized_layouts[choice.wearer_id]
                if choice.main_stat_layout_id not in wearer_layouts:
                    raise GcsimFinalistOptimizerError(
                        "finalist references an unknown wearer/layout pair: "
                        f"{(choice.wearer_id, choice.main_stat_layout_id)!r}"
                    )
                capability = self.engine_context.catalog.get(choice.set_key)
                if capability is None:
                    raise GcsimFinalistOptimizerError(
                        f"finalist references an unknown set: {choice.set_key!r}"
                    )
                if not capability.optimizer_four_piece_ready:
                    raise GcsimFinalistOptimizerError(
                        "finalist set is not optimizer-ready for a complete 4p race: "
                        f"{choice.set_key!r}"
                    )
                if capability.max_rarity == 4 and not choice.offpiece_slot:
                    raise GcsimFinalistOptimizerError(
                        "a four-star-only finalist set requires one explicit "
                        f"five-star off-piece slot: {choice.set_key!r}"
                    )
                if capability.max_rarity == 5 and choice.offpiece_slot:
                    raise GcsimFinalistOptimizerError(
                        "a five-star finalist set must not carry a rarity "
                        f"off-piece override: {choice.set_key!r}"
                    )
                if capability.max_rarity not in (4, 5):
                    raise GcsimFinalistOptimizerError(
                        "finalist set has an unsupported maximum rarity"
                    )

        if not isinstance(self.optimizer_options, Mapping):
            raise GcsimFinalistOptimizerError("optimizer_options must be a mapping")
        try:
            format_gcsim_optimizer_options(self.optimizer_options)
        except ValueError as exc:
            raise GcsimFinalistOptimizerError(str(exc)) from exc
        normalized_options = {
            str(key): value
            for key, value in sorted(
                self.optimizer_options.items(),
                key=lambda item: str(item[0]),
            )
        }
        if not isinstance(self.environment, Mapping):
            raise GcsimFinalistOptimizerError("environment must be a mapping")
        try:
            frozen_environment = (
                normalize_gcsim_optimizer_frozen_environment(self.environment)
                if self.environment_is_frozen
                else freeze_gcsim_optimizer_environment(self.environment)
            )
        except ValueError as exc:
            raise GcsimFinalistOptimizerError(str(exc)) from exc
        environment_by_folded_key = {
            key.casefold(): (key, value)
            for key, value in frozen_environment.items()
            if key.casefold() != "gomaxprocs"
        }
        environment_by_folded_key["gomaxprocs"] = (
            "GOMAXPROCS",
            str(self.budget.worker_count),
        )
        normalized_environment = dict(
            sorted(environment_by_folded_key.values(), key=lambda item: item[0])
        )

        object.__setattr__(self, "wearer_ids", wearer_ids)
        object.__setattr__(self, "prepared_config_text", prepared_config)
        object.__setattr__(self, "validation_config_text", validation_config)
        object.__setattr__(self, "finalists", finalists)
        object.__setattr__(
            self,
            "layout_catalog",
            MappingProxyType(
                {
                    wearer: MappingProxyType(dict(normalized_layouts[wearer]))
                    for wearer in wearer_ids
                }
            ),
        )
        object.__setattr__(
            self,
            "optimizer_options",
            MappingProxyType(normalized_options),
        )
        object.__setattr__(
            self,
            "environment",
            MappingProxyType(dict(sorted(normalized_environment.items()))),
        )
        object.__setattr__(self, "environment_is_frozen", True)
        _validate_request_substat_budget_feasibility(self)

    @property
    def source_config_sha256(self) -> str:
        return _text_sha256(self.prepared_config_text)

    @property
    def validation_config_sha256(self) -> str:
        return _text_sha256(self.validation_config_text)

    @property
    def layout_catalog_sha256(self) -> str:
        return _canonical_sha256(_layout_catalog_payload(self))

    @property
    def finalist_domain_sha256(self) -> str:
        return _canonical_sha256(_finalist_domain_payload(self.finalists))

    @property
    def budget_sha256(self) -> str:
        return _canonical_sha256(_budget_payload(self.budget))

    @property
    def request_sha256(self) -> str:
        return _canonical_sha256(_request_payload(self))


@dataclass(frozen=True, slots=True)
class GcsimOptimizedWearerAllocation:
    wearer_id: str
    set_key: str
    main_stat_layout_id: str
    offpiece_slot: str
    add_stats_lines: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "add_stats_lines", tuple(self.add_stats_lines))
        for field_name in ("wearer_id", "set_key", "main_stat_layout_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise GcsimFinalistOptimizerError(
                    f"allocation {field_name} must be a non-empty string"
                )
        if not self.add_stats_lines:
            raise GcsimFinalistOptimizerError(
                "optimized allocation must contain add-stats evidence"
            )
        for line in self.add_stats_lines:
            match = _ADD_STATS_RE.match(line)
            if match is None or match.group("wearer") != self.wearer_id:
                raise GcsimFinalistOptimizerError(
                    "allocation add-stats evidence does not match its wearer"
                )
            if not match.group("body").strip():
                raise GcsimFinalistOptimizerError(
                    "allocation add-stats evidence must contain stats"
                )


@dataclass(frozen=True, slots=True)
class GcsimFinalistOptimizerOutcome:
    ordinal: int
    state: FullTeamPhysicalState
    dps_mean: float
    dps_se: float | None
    iterations: int
    optimizer_input_config_text: str = field(repr=False)
    optimizer_input_sha256: str
    optimized_config_text: str = field(repr=False)
    optimized_config_sha256: str
    result_json_bytes: bytes = field(repr=False)
    result_json_sha256: str
    allocation_sha256: str
    allocations: tuple[GcsimOptimizedWearerAllocation, ...]
    cache_identity_sha256: str
    runner_result: GcsimOptimizerRunResult = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "allocations", tuple(self.allocations))
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int) or self.ordinal < 0:
            raise GcsimFinalistOptimizerError(
                "outcome ordinal must be a non-negative integer"
            )
        if not isinstance(self.state, FullTeamPhysicalState):
            raise GcsimFinalistOptimizerError(
                "outcome state must be a FullTeamPhysicalState"
            )
        if (
            isinstance(self.dps_mean, bool)
            or not isinstance(self.dps_mean, (int, float))
            or not math.isfinite(self.dps_mean)
            or self.dps_mean < 0
        ):
            raise GcsimFinalistOptimizerError(
                "outcome DPS must be finite and non-negative"
            )
        if self.dps_se is not None and (
            isinstance(self.dps_se, bool)
            or not isinstance(self.dps_se, (int, float))
            or not math.isfinite(self.dps_se)
            or self.dps_se < 0
        ):
            raise GcsimFinalistOptimizerError(
                "outcome DPS SE must be finite and non-negative or None"
            )
        if (
            isinstance(self.iterations, bool)
            or not isinstance(self.iterations, int)
            or self.iterations <= 0
        ):
            raise GcsimFinalistOptimizerError(
                "outcome iterations must be a positive integer"
            )
        for field_name in (
            "optimizer_input_sha256",
            "optimized_config_sha256",
            "result_json_sha256",
            "allocation_sha256",
            "cache_identity_sha256",
        ):
            if not _is_sha256(getattr(self, field_name)):
                raise GcsimFinalistOptimizerError(
                    f"outcome {field_name} must be a lowercase SHA-256 digest"
                )
        if self.optimizer_input_sha256 != _text_sha256(
            self.optimizer_input_config_text
        ):
            raise GcsimFinalistOptimizerError(
                "outcome optimizer input hash does not match its text"
            )
        if self.optimized_config_sha256 != _text_sha256(self.optimized_config_text):
            raise GcsimFinalistOptimizerError(
                "outcome optimized config hash does not match its text"
            )
        if (
            not isinstance(self.result_json_bytes, bytes)
            or not self.result_json_bytes
            or self.result_json_sha256
            != hashlib.sha256(self.result_json_bytes).hexdigest()
        ):
            raise GcsimFinalistOptimizerError(
                "outcome result JSON hash does not match its byte snapshot"
            )
        wearer_ids = tuple(choice.wearer_id for choice in self.state.choices)
        try:
            _validated_prepared_config(
                self.optimizer_input_config_text,
                wearer_ids,
            )
            _validated_prepared_config(self.optimized_config_text, wearer_ids)
        except GcsimFarmingPipelineError as exc:
            raise GcsimFinalistOptimizerError(
                f"outcome config violates the static-target contract: {exc}"
            ) from exc
        _validate_optimizer_owned_config_diff(
            self.optimizer_input_config_text,
            self.optimized_config_text,
            self.state,
        )
        _validate_exact_set_evidence(self.optimizer_input_config_text, self.state)
        _validate_exact_set_evidence(self.optimized_config_text, self.state)
        if self.allocations != _extract_allocations(
            self.optimized_config_text,
            self.state,
        ):
            raise GcsimFinalistOptimizerError(
                "outcome allocations do not match its optimized config"
            )
        if self.allocation_sha256 != _canonical_sha256(
            _allocation_payload(self.allocations)
        ):
            raise GcsimFinalistOptimizerError(
                "outcome allocation hash does not match its evidence"
            )
        if not isinstance(self.runner_result, GcsimOptimizerRunResult):
            raise GcsimFinalistOptimizerError(
                "outcome runner_result must be typed"
            )
        try:
            snapshot_summary = parse_gcsim_result_payload(
                json.loads(self.result_json_bytes.decode("utf-8"))
            )
            runner_input_text = self.runner_result.input_config_bytes.decode("utf-8")
            runner_optimized_text = self.runner_result.optimized_config_bytes.decode(
                "utf-8"
            )
        except (UnicodeDecodeError, json.JSONDecodeError, GcsimResultParseError) as exc:
            raise GcsimFinalistOptimizerError(
                f"outcome result JSON snapshot is invalid: {exc}"
            ) from exc
        if (
            self.runner_result.status is not GcsimOptimizerRunStatus.PASSED
            or not self.runner_result.success
            or self.runner_result.session_status
            is not GcsimOptimizerSessionStatus.PASSED
            or self.runner_result.summary.dps_mean != self.dps_mean
            or self.runner_result.summary.dps_se != self.dps_se
            or self.runner_result.summary.iterations != self.iterations
            or snapshot_summary != self.runner_result.summary
            or runner_input_text != self.optimizer_input_config_text
            or runner_optimized_text != self.optimized_config_text
            or self.runner_result.result_json_bytes != self.result_json_bytes
            or self.runner_result.input_config_sha256
            != self.optimizer_input_sha256
            or self.runner_result.optimized_config_sha256
            != self.optimized_config_sha256
            or self.runner_result.result_json_sha256 != self.result_json_sha256
        ):
            raise GcsimFinalistOptimizerError(
                "outcome metrics do not match its passed runner evidence"
            )


@dataclass(frozen=True, slots=True)
class GcsimFinalistOptimizerAttempt:
    ordinal: int
    state: FullTeamPhysicalState
    status: GcsimFinalistAttemptStatus
    runner_status: str = ""
    optimizer_input_sha256: str = ""
    cache_identity_sha256: str = ""
    runner_result: GcsimOptimizerRunResult | None = field(default=None, repr=False)
    outcome: GcsimFinalistOptimizerOutcome | None = None
    error: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int) or self.ordinal < 0:
            raise GcsimFinalistOptimizerError(
                "attempt ordinal must be a non-negative integer"
            )
        if not isinstance(self.state, FullTeamPhysicalState):
            raise GcsimFinalistOptimizerError(
                "attempt state must be a FullTeamPhysicalState"
            )
        if not isinstance(self.status, GcsimFinalistAttemptStatus):
            raise GcsimFinalistOptimizerError("attempt status must be typed")
        for field_name in ("optimizer_input_sha256", "cache_identity_sha256"):
            value = getattr(self, field_name)
            if value and not _is_sha256(value):
                raise GcsimFinalistOptimizerError(
                    f"attempt {field_name} must be empty or a SHA-256 digest"
                )
        if self.runner_result is not None and not isinstance(
            self.runner_result,
            GcsimOptimizerRunResult,
        ):
            raise GcsimFinalistOptimizerError(
                "attempt runner_result must be typed or None"
            )
        if self.runner_result is None and self.runner_status:
            raise GcsimFinalistOptimizerError(
                "attempt runner_status requires typed runner evidence"
            )
        if self.runner_result is not None and (
            self.runner_status != self.runner_result.status.value
        ):
            raise GcsimFinalistOptimizerError(
                "attempt runner_status differs from its runner evidence"
            )
        if self.status is GcsimFinalistAttemptStatus.PASSED:
            if (
                self.runner_status != GcsimOptimizerRunStatus.PASSED.value
                or not self.optimizer_input_sha256
                or not self.cache_identity_sha256
                or self.runner_result is None
                or self.outcome is None
                or self.error
                or self.outcome.ordinal != self.ordinal
                or self.outcome.state != self.state
                or self.outcome.runner_result != self.runner_result
                or self.outcome.optimizer_input_sha256
                != self.optimizer_input_sha256
                or self.outcome.cache_identity_sha256
                != self.cache_identity_sha256
            ):
                raise GcsimFinalistOptimizerError(
                    "passed attempt lacks coherent optimizer evidence"
                )
        else:
            if self.outcome is not None or not self.error:
                raise GcsimFinalistOptimizerError(
                    "non-passed attempt must carry an error and no outcome"
                )
            if self.status is GcsimFinalistAttemptStatus.MATERIALIZATION_FAILED:
                if (
                    self.optimizer_input_sha256
                    or self.cache_identity_sha256
                    or self.runner_result is not None
                ):
                    raise GcsimFinalistOptimizerError(
                        "materialization failure must not claim execution evidence"
                    )
            elif not self.optimizer_input_sha256 or not self.cache_identity_sha256:
                raise GcsimFinalistOptimizerError(
                    "post-materialization attempt requires input and cache hashes"
                )
            if (
                self.status is GcsimFinalistAttemptStatus.SESSION_FACTORY_FAILED
                and self.runner_result is not None
            ):
                raise GcsimFinalistOptimizerError(
                    "session-factory failure must not carry runner evidence"
                )
            if (
                self.status is GcsimFinalistAttemptStatus.RUN_FAILED
                and self.runner_result is not None
                and self.runner_result.status is GcsimOptimizerRunStatus.PASSED
            ):
                raise GcsimFinalistOptimizerError(
                    "run-failed attempt must not carry a passed runner result"
                )
            if (
                self.status is GcsimFinalistAttemptStatus.RESULT_REJECTED
                and self.runner_result is not None
                and self.runner_result.status is not GcsimOptimizerRunStatus.PASSED
            ):
                raise GcsimFinalistOptimizerError(
                    "result-rejected attempt may carry only passed runner evidence"
                )


@dataclass(frozen=True, slots=True)
class GcsimFinalistOptimizerResult:
    status: GcsimFinalistOptimizerStatus
    stop_reason: str
    provenance_schema_version: int
    request_snapshot: GcsimFinalistOptimizerRequest = field(repr=False)
    request_sha256: str
    source_config_sha256: str
    validation_config_sha256: str
    layout_catalog_sha256: str
    finalist_domain_sha256: str
    budget_sha256: str
    engine_binding_sha256: str
    elapsed_seconds: float
    attempted_count: int
    successful_count: int
    attempts: tuple[GcsimFinalistOptimizerAttempt, ...]
    outcomes: tuple[GcsimFinalistOptimizerOutcome, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "attempts", tuple(self.attempts))
        object.__setattr__(self, "outcomes", tuple(self.outcomes))
        if not isinstance(self.status, GcsimFinalistOptimizerStatus):
            raise GcsimFinalistOptimizerError("result status must be typed")
        expected_reason = {
            GcsimFinalistOptimizerStatus.BEST_FOUND: "finalist_race_completed",
            GcsimFinalistOptimizerStatus.CANCELLED: "cancelled",
            GcsimFinalistOptimizerStatus.DEADLINE: "deadline_reached",
            GcsimFinalistOptimizerStatus.NO_SUCCESS: "no_success",
        }[self.status]
        if self.stop_reason != expected_reason:
            raise GcsimFinalistOptimizerError(
                "result stop_reason does not match its typed status"
            )
        if self.provenance_schema_version != GCSIM_FINALIST_OPTIMIZER_PROVENANCE_SCHEMA:
            raise GcsimFinalistOptimizerError(
                "result provenance schema is unsupported"
            )
        if not isinstance(self.request_snapshot, GcsimFinalistOptimizerRequest):
            raise GcsimFinalistOptimizerError(
                "result request_snapshot must be a finalist optimizer request"
            )
        expected_hashes = {
            "request_sha256": self.request_snapshot.request_sha256,
            "source_config_sha256": self.request_snapshot.source_config_sha256,
            "validation_config_sha256": (
                self.request_snapshot.validation_config_sha256
            ),
            "layout_catalog_sha256": self.request_snapshot.layout_catalog_sha256,
            "finalist_domain_sha256": self.request_snapshot.finalist_domain_sha256,
            "budget_sha256": self.request_snapshot.budget_sha256,
            "engine_binding_sha256": (
                self.request_snapshot.engine_context.binding_sha256
            ),
        }
        for field_name, expected in expected_hashes.items():
            if getattr(self, field_name) != expected or not _is_sha256(expected):
                raise GcsimFinalistOptimizerError(
                    f"result {field_name} does not match its request snapshot"
                )
        if (
            isinstance(self.elapsed_seconds, bool)
            or not isinstance(self.elapsed_seconds, (int, float))
            or not math.isfinite(self.elapsed_seconds)
            or self.elapsed_seconds < 0
        ):
            raise GcsimFinalistOptimizerError(
                "result elapsed_seconds must be finite and non-negative"
            )
        for field_name in ("attempted_count", "successful_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise GcsimFinalistOptimizerError(
                    f"result {field_name} must be a non-negative integer"
                )
        if self.attempted_count != len(self.attempts):
            raise GcsimFinalistOptimizerError(
                "result attempted_count differs from its audit trace"
            )
        if self.attempted_count > len(self.request_snapshot.finalists):
            raise GcsimFinalistOptimizerError(
                "result attempted_count exceeds its finalist domain"
            )
        if tuple(attempt.ordinal for attempt in self.attempts) != tuple(
            range(len(self.attempts))
        ):
            raise GcsimFinalistOptimizerError(
                "result attempt ordinals must form a contiguous prefix"
            )
        if tuple(attempt.state for attempt in self.attempts) != (
            self.request_snapshot.finalists[: len(self.attempts)]
        ):
            raise GcsimFinalistOptimizerError(
                "result attempts are not the canonical finalist prefix"
            )
        for attempt in self.attempts:
            if not attempt.optimizer_input_sha256:
                continue
            try:
                expected_input, expected_cache_sha = (
                    _expected_finalist_materialization(
                        self.request_snapshot,
                        attempt.state,
                    )
                )
            except Exception as exc:
                raise GcsimFinalistOptimizerError(
                    "could not rematerialize finalist evidence from the frozen "
                    f"request: {_safe_error(exc)}"
                ) from exc
            expected_input_sha = _text_sha256(expected_input)
            if attempt.optimizer_input_sha256 != expected_input_sha:
                raise GcsimFinalistOptimizerError(
                    "attempt optimizer input does not match the deterministic "
                    "request/state materialization"
                )
            if attempt.cache_identity_sha256 != expected_cache_sha:
                raise GcsimFinalistOptimizerError(
                    "attempt cache identity does not match the deterministic "
                    "request/state materialization"
                )
            if attempt.outcome is not None:
                if attempt.outcome.optimizer_input_config_text != expected_input:
                    raise GcsimFinalistOptimizerError(
                        "outcome optimizer input text does not match the "
                        "deterministic request/state materialization"
                    )
                _validate_optimizer_substat_budget(
                    attempt.outcome.optimized_config_text,
                    attempt.state,
                    self.request_snapshot,
                )
        successful = tuple(
            attempt.outcome
            for attempt in self.attempts
            if attempt.status is GcsimFinalistAttemptStatus.PASSED
            and attempt.outcome is not None
        )
        if self.successful_count != len(successful):
            raise GcsimFinalistOptimizerError(
                "result successful_count differs from its audit trace"
            )
        expected_outcomes = tuple(
            sorted(successful, key=_outcome_rank_key)[
                : self.request_snapshot.budget.top_n
            ]
        )
        if self.outcomes != expected_outcomes:
            raise GcsimFinalistOptimizerError(
                "result outcomes are not the canonical top-N successful attempts"
            )
        for outcome in successful:
            if outcome.iterations != self.request_snapshot.budget.validation_iterations:
                raise GcsimFinalistOptimizerError(
                    "result outcome did not use the frozen validation iteration count"
                )
            if (
                outcome.runner_result.artifact_sha256
                != self.request_snapshot.engine_context.artifact_sha256
                or outcome.runner_result.engine_binding_sha256
                != self.request_snapshot.engine_context.binding_sha256
            ):
                raise GcsimFinalistOptimizerError(
                    "result outcome belongs to another engine identity"
                )
            if tuple(item.wearer_id for item in outcome.allocations) != (
                self.request_snapshot.wearer_ids
            ):
                raise GcsimFinalistOptimizerError(
                    "result allocation evidence uses another wearer order"
                )
            if tuple(
                (
                    item.wearer_id,
                    item.set_key,
                    item.main_stat_layout_id,
                    item.offpiece_slot,
                )
                for item in outcome.allocations
            ) != tuple(
                (
                    choice.wearer_id,
                    choice.set_key,
                    choice.main_stat_layout_id,
                    choice.offpiece_slot,
                )
                for choice in outcome.state.choices
            ):
                raise GcsimFinalistOptimizerError(
                    "result allocations differ from their finalist state"
                )
        if self.status in {
            GcsimFinalistOptimizerStatus.BEST_FOUND,
            GcsimFinalistOptimizerStatus.NO_SUCCESS,
        } and self.attempted_count != len(self.request_snapshot.finalists):
            raise GcsimFinalistOptimizerError(
                "completed finalist status requires the full bounded domain"
            )
        if self.status is GcsimFinalistOptimizerStatus.BEST_FOUND and not successful:
            raise GcsimFinalistOptimizerError(
                "best_found result requires a successful optimized finalist"
            )
        if self.status is GcsimFinalistOptimizerStatus.NO_SUCCESS and successful:
            raise GcsimFinalistOptimizerError(
                "no_success result must not carry successful outcomes"
            )

    @property
    def best_found(self) -> GcsimFinalistOptimizerOutcome | None:
        return self.outcomes[0] if self.outcomes else None


class OptimizerSessionLike(Protocol):
    def cancel(self) -> None: ...

    def run(self) -> GcsimOptimizerRunResult: ...


OptimizerSessionFactory = Callable[[GcsimOptimizerRunRequest], OptimizerSessionLike]


class GcsimFinalistOptimizerSession:
    """One-shot, externally cancellable sequential finalist optimizer."""

    def __init__(
        self,
        request: GcsimFinalistOptimizerRequest,
        *,
        session_factory: OptimizerSessionFactory | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not isinstance(request, GcsimFinalistOptimizerRequest):
            raise GcsimFinalistOptimizerError(
                "request must be a GcsimFinalistOptimizerRequest"
            )
        if not callable(clock):
            raise GcsimFinalistOptimizerError("clock must be callable")
        self.request = request
        self._session_factory = session_factory or GcsimOptimizerSession
        self._clock = clock
        self._cancel_event = Event()
        self._lock = Lock()
        self._active: OptimizerSessionLike | None = None
        self._started = False

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            active = self._active
        if active is not None:
            try:
                active.cancel()
            except Exception:
                # The run thread will still observe the outer cancellation flag.
                pass

    def run(self) -> GcsimFinalistOptimizerResult:
        with self._lock:
            if self._started:
                raise RuntimeError(
                    "GcsimFinalistOptimizerSession instances are one-shot"
                )
            self._started = True
        started = self._clock()
        deadline = started + self.request.budget.overall_deadline_seconds
        attempts: list[GcsimFinalistOptimizerAttempt] = []

        for ordinal, state in enumerate(self.request.finalists):
            terminal = self._terminal_status(deadline)
            if terminal is not None:
                return self._result(started, terminal, attempts)

            try:
                execution = self._materialize_execution(state, deadline)
            except Exception as exc:
                attempts.append(
                    GcsimFinalistOptimizerAttempt(
                        ordinal=ordinal,
                        state=state,
                        status=GcsimFinalistAttemptStatus.MATERIALIZATION_FAILED,
                        error=_safe_error(exc),
                    )
                )
                terminal = self._terminal_status(deadline)
                if terminal is not None:
                    return self._result(started, terminal, attempts)
                continue

            run_request = execution.request
            input_sha = _text_sha256(str(run_request.config_text))
            cache_sha = execution.cache_identity.cache_key
            terminal = self._terminal_status(deadline)
            if terminal is not None:
                attempts.append(
                    GcsimFinalistOptimizerAttempt(
                        ordinal=ordinal,
                        state=state,
                        status=GcsimFinalistAttemptStatus.RUN_FAILED,
                        optimizer_input_sha256=input_sha,
                        cache_identity_sha256=cache_sha,
                        error=(
                            "cancelled_before_session_factory"
                            if terminal is GcsimFinalistOptimizerStatus.CANCELLED
                            else "deadline_before_session_factory"
                        ),
                    )
                )
                return self._result(started, terminal, attempts)

            try:
                session = self._session_factory(run_request)
            except Exception as exc:
                attempts.append(
                    GcsimFinalistOptimizerAttempt(
                        ordinal=ordinal,
                        state=state,
                        status=GcsimFinalistAttemptStatus.SESSION_FACTORY_FAILED,
                        optimizer_input_sha256=input_sha,
                        cache_identity_sha256=cache_sha,
                        error=_safe_error(exc),
                    )
                )
                terminal = self._terminal_status(deadline)
                if terminal is not None:
                    return self._result(started, terminal, attempts)
                continue

            if not callable(getattr(session, "run", None)) or not callable(
                getattr(session, "cancel", None)
            ):
                attempts.append(
                    GcsimFinalistOptimizerAttempt(
                        ordinal=ordinal,
                        state=state,
                        status=GcsimFinalistAttemptStatus.RESULT_REJECTED,
                        optimizer_input_sha256=input_sha,
                        cache_identity_sha256=cache_sha,
                        error="session_factory_returned_an_invalid_session",
                    )
                )
                terminal = self._terminal_status(deadline)
                if terminal is not None:
                    return self._result(started, terminal, attempts)
                continue

            terminal = self._terminal_status(deadline)
            if terminal is not None:
                try:
                    session.cancel()
                except Exception:
                    pass
                attempts.append(
                    GcsimFinalistOptimizerAttempt(
                        ordinal=ordinal,
                        state=state,
                        status=GcsimFinalistAttemptStatus.RUN_FAILED,
                        optimizer_input_sha256=input_sha,
                        cache_identity_sha256=cache_sha,
                        error=(
                            "cancelled_before_session_run"
                            if terminal is GcsimFinalistOptimizerStatus.CANCELLED
                            else "deadline_before_session_run"
                        ),
                    )
                )
                return self._result(started, terminal, attempts)

            self._set_active(session)
            remaining_for_run = max(deadline - self._clock(), 0.0)
            deadline_expired = Event()
            deadline_timer = Timer(
                remaining_for_run,
                _expire_optimizer_session_safely,
                args=(deadline_expired, session),
            )
            deadline_timer.daemon = True
            try:
                if self._cancel_event.is_set():
                    session.cancel()
                deadline_timer.start()
                try:
                    raw_result = session.run()
                except Exception as exc:
                    raw_result = exc
            finally:
                deadline_timer.cancel()
                self._clear_active(session)

            terminal = self._terminal_status(deadline)
            if terminal is None and deadline_expired.is_set():
                terminal = GcsimFinalistOptimizerStatus.DEADLINE
            if isinstance(raw_result, Exception):
                attempts.append(
                    GcsimFinalistOptimizerAttempt(
                        ordinal=ordinal,
                        state=state,
                        status=GcsimFinalistAttemptStatus.RUN_FAILED,
                        optimizer_input_sha256=input_sha,
                        cache_identity_sha256=cache_sha,
                        error=_safe_error(raw_result),
                    )
                )
            elif not isinstance(raw_result, GcsimOptimizerRunResult):
                attempts.append(
                    GcsimFinalistOptimizerAttempt(
                        ordinal=ordinal,
                        state=state,
                        status=GcsimFinalistAttemptStatus.RESULT_REJECTED,
                        optimizer_input_sha256=input_sha,
                        cache_identity_sha256=cache_sha,
                        error="optimizer_session_returned_a_non_typed_result",
                    )
                )
            elif raw_result.status is not GcsimOptimizerRunStatus.PASSED:
                attempts.append(
                    GcsimFinalistOptimizerAttempt(
                        ordinal=ordinal,
                        state=state,
                        status=GcsimFinalistAttemptStatus.RUN_FAILED,
                        runner_status=raw_result.status.value,
                        optimizer_input_sha256=input_sha,
                        cache_identity_sha256=cache_sha,
                        runner_result=raw_result,
                        error=raw_result.error or "optimizer_session_did_not_pass",
                    )
                )
            else:
                try:
                    outcome = _accepted_outcome(
                        ordinal=ordinal,
                        state=state,
                        request=self.request,
                        run_request=run_request,
                        cache_identity_sha256=cache_sha,
                        result=raw_result,
                    )
                except Exception as exc:
                    attempts.append(
                        GcsimFinalistOptimizerAttempt(
                            ordinal=ordinal,
                            state=state,
                            status=GcsimFinalistAttemptStatus.RESULT_REJECTED,
                            runner_status=raw_result.status.value,
                            optimizer_input_sha256=input_sha,
                            cache_identity_sha256=cache_sha,
                            runner_result=raw_result,
                            error=_safe_error(exc),
                        )
                    )
                else:
                    attempts.append(
                        GcsimFinalistOptimizerAttempt(
                            ordinal=ordinal,
                            state=state,
                            status=GcsimFinalistAttemptStatus.PASSED,
                            runner_status=raw_result.status.value,
                            optimizer_input_sha256=input_sha,
                            cache_identity_sha256=cache_sha,
                            runner_result=raw_result,
                            outcome=outcome,
                        )
                    )

            terminal = self._terminal_status(deadline)
            if terminal is None and deadline_expired.is_set():
                terminal = GcsimFinalistOptimizerStatus.DEADLINE
            if terminal is not None:
                return self._result(started, terminal, attempts)

        status = (
            GcsimFinalistOptimizerStatus.BEST_FOUND
            if any(
                attempt.status is GcsimFinalistAttemptStatus.PASSED
                for attempt in attempts
            )
            else GcsimFinalistOptimizerStatus.NO_SUCCESS
        )
        return self._result(started, status, attempts)

    def _materialize_execution(self, state, deadline):
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise GcsimFinalistOptimizerError(
                "deadline reached before finalist materialization"
            )
        bound = _prepare_bound_finalist_candidate(self.request, state)
        remaining = deadline - self._clock()
        if remaining <= 0:
            raise GcsimFinalistOptimizerError(
                "deadline reached during finalist materialization"
            )
        return bound.build_execution(
            worker_count=self.request.budget.worker_count,
            optimizer_timeout_seconds=min(
                self.request.budget.optimizer_timeout_seconds,
                remaining,
            ),
            simulation_timeout_seconds=min(
                self.request.budget.simulation_timeout_seconds,
                remaining,
            ),
            overall_timeout_seconds=remaining,
            optimizer_options=self.request.optimizer_options,
            environment=self.request.environment,
            environment_is_frozen=True,
            mode=GCSIM_FINALIST_OPTIMIZER_MODE,
        )

    def _terminal_status(
        self,
        deadline: float,
    ) -> GcsimFinalistOptimizerStatus | None:
        if self._cancel_event.is_set():
            return GcsimFinalistOptimizerStatus.CANCELLED
        if self._clock() >= deadline:
            return GcsimFinalistOptimizerStatus.DEADLINE
        return None

    def _set_active(self, session: OptimizerSessionLike) -> None:
        with self._lock:
            if self._active is not None:
                raise GcsimFinalistOptimizerError(
                    "another finalist optimizer session is active"
                )
            self._active = session

    def _clear_active(self, session: OptimizerSessionLike) -> None:
        with self._lock:
            if self._active is session:
                self._active = None

    def _result(
        self,
        started: float,
        status: GcsimFinalistOptimizerStatus,
        attempts: Sequence[GcsimFinalistOptimizerAttempt],
    ) -> GcsimFinalistOptimizerResult:
        attempt_tuple = tuple(attempts)
        successful = tuple(
            attempt.outcome
            for attempt in attempt_tuple
            if attempt.status is GcsimFinalistAttemptStatus.PASSED
            and attempt.outcome is not None
        )
        outcomes = tuple(
            sorted(successful, key=_outcome_rank_key)[: self.request.budget.top_n]
        )
        stop_reason = {
            GcsimFinalistOptimizerStatus.BEST_FOUND: "finalist_race_completed",
            GcsimFinalistOptimizerStatus.CANCELLED: "cancelled",
            GcsimFinalistOptimizerStatus.DEADLINE: "deadline_reached",
            GcsimFinalistOptimizerStatus.NO_SUCCESS: "no_success",
        }[status]
        return GcsimFinalistOptimizerResult(
            status=status,
            stop_reason=stop_reason,
            provenance_schema_version=GCSIM_FINALIST_OPTIMIZER_PROVENANCE_SCHEMA,
            request_snapshot=self.request,
            request_sha256=self.request.request_sha256,
            source_config_sha256=self.request.source_config_sha256,
            validation_config_sha256=self.request.validation_config_sha256,
            layout_catalog_sha256=self.request.layout_catalog_sha256,
            finalist_domain_sha256=self.request.finalist_domain_sha256,
            budget_sha256=self.request.budget_sha256,
            engine_binding_sha256=self.request.engine_context.binding_sha256,
            elapsed_seconds=max(self._clock() - started, 0.0),
            attempted_count=len(attempt_tuple),
            successful_count=len(successful),
            attempts=attempt_tuple,
            outcomes=outcomes,
        )


def run_gcsim_finalist_optimizer(
    request: GcsimFinalistOptimizerRequest,
    **session_options,
) -> GcsimFinalistOptimizerResult:
    return GcsimFinalistOptimizerSession(request, **session_options).run()


def _expire_optimizer_session_safely(
    deadline_expired: Event,
    session: OptimizerSessionLike,
) -> None:
    deadline_expired.set()
    try:
        session.cancel()
    except Exception:
        pass


def _prepare_bound_finalist_candidate(
    request: GcsimFinalistOptimizerRequest,
    state: FullTeamPhysicalState,
) -> GcsimBoundOptimizerCandidate:
    set_assignments = {
        choice.wearer_id: choice.set_key for choice in state.choices
    }
    main_stat_layouts = {
        choice.wearer_id: request.layout_catalog[choice.wearer_id][
            choice.main_stat_layout_id
        ]
        for choice in state.choices
    }
    offpieces = {
        choice.wearer_id: choice.offpiece_slot
        for choice in state.choices
        if choice.offpiece_slot
    }
    bound = prepare_bound_gcsim_four_piece_optimizer_candidate(
        request.validation_config_text,
        engine_context=request.engine_context,
        set_assignments=set_assignments,
        main_stat_layouts=main_stat_layouts,
        four_star_offpiece_slots=offpieces,
        require_full_team=True,
    )
    if not bound.ready:
        issue_text = "; ".join(
            issue.message or issue.status for issue in bound.candidate.issues
        )
        raise GcsimFinalistOptimizerError(
            "finalist optimizer candidate is not ready: "
            + (issue_text or bound.candidate.status)
        )
    return bound


def _expected_finalist_materialization(
    request: GcsimFinalistOptimizerRequest,
    state: FullTeamPhysicalState,
) -> tuple[str, str]:
    """Rebuild the exact optimizer input/cache identity from frozen inputs."""

    bound = _prepare_bound_finalist_candidate(request, state)
    config_text = bound.prepared_config(
        worker_count=request.budget.worker_count,
    )
    context = request.engine_context
    identity = build_gcsim_optimizer_cache_identity_from_sha256(
        engine_sha256=context.artifact_sha256,
        engine_version=context.engine_version,
        source_config_text=config_text,
        mode=GCSIM_FINALIST_OPTIMIZER_MODE,
        optimizer_options=request.optimizer_options,
        catalog_fingerprint=context.catalog.source_fingerprint,
        candidate_key=_text_sha256(config_text),
    )
    return config_text, identity.cache_key


def _accepted_outcome(
    *,
    ordinal: int,
    state: FullTeamPhysicalState,
    request: GcsimFinalistOptimizerRequest,
    run_request: GcsimOptimizerRunRequest,
    cache_identity_sha256: str,
    result: GcsimOptimizerRunResult,
) -> GcsimFinalistOptimizerOutcome:
    if result.status is not GcsimOptimizerRunStatus.PASSED:
        raise GcsimFinalistOptimizerError("optimizer result did not pass")
    if (
        not result.success
        or result.session_status is not GcsimOptimizerSessionStatus.PASSED
        or result.optimize is None
        or result.optimize.name is not GcsimOptimizerStageName.OPTIMIZE
        or result.optimize.status is not GcsimOptimizerStageStatus.PASSED
        or result.simulate is None
        or result.simulate.name is not GcsimOptimizerStageName.SIMULATE
        or result.simulate.status is not GcsimOptimizerStageStatus.PASSED
    ):
        raise GcsimFinalistOptimizerError(
            "passed optimizer result has inconsistent stage evidence"
        )
    context = request.engine_context
    if (
        result.artifact_sha256 != context.artifact_sha256
        or result.engine_binding_sha256 != context.binding_sha256
        or Path(result.artifact_path).expanduser().resolve()
        != Path(context.artifact_path).expanduser().resolve()
        or result.artifact_source != "explicit"
    ):
        raise GcsimFinalistOptimizerError(
            "optimizer result does not belong to the bound engine context"
        )
    if run_request.config_text is None or run_request.config_path is not None:
        raise GcsimFinalistOptimizerError(
            "finalist execution did not use its exact in-memory optimizer input"
        )
    if (
        run_request.expected_artifact_sha256 != context.artifact_sha256
        or run_request.engine_binding_sha256 != context.binding_sha256
        or run_request.environment.get("GOMAXPROCS")
        != str(request.budget.worker_count)
    ):
        raise GcsimFinalistOptimizerError(
            "finalist run request lost its engine or CPU-worker binding"
        )

    run_dir = _required_directory(result.run_dir, "run_dir")
    input_path = _required_child_file(
        run_dir,
        result.input_config_path,
        DEFAULT_GCSIM_OPTIMIZER_INPUT_FILENAME,
        "optimizer input",
    )
    optimized_path = _required_child_file(
        run_dir,
        result.optimized_config_path,
        DEFAULT_GCSIM_OPTIMIZED_CONFIG_FILENAME,
        "optimized config",
    )
    result_path = _required_child_file(
        run_dir,
        result.result_path,
        DEFAULT_GCSIM_OPTIMIZER_RESULT_FILENAME,
        "simulation result",
    )
    try:
        current_input_bytes = input_path.read_bytes()
        current_optimized_bytes = optimized_path.read_bytes()
        current_result_bytes = result_path.read_bytes()
    except OSError as exc:
        raise GcsimFinalistOptimizerError(
            f"could not read optimizer evidence: {exc}"
        ) from exc
    if (
        current_input_bytes != result.input_config_bytes
        or current_optimized_bytes != result.optimized_config_bytes
        or current_result_bytes != result.result_json_bytes
    ):
        raise GcsimFinalistOptimizerError(
            "optimizer evidence files changed after the runner byte snapshot"
        )
    try:
        input_text = result.input_config_bytes.decode("utf-8")
        optimized_text = result.optimized_config_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GcsimFinalistOptimizerError(
            f"optimizer config byte snapshot is not UTF-8: {exc}"
        ) from exc
    result_bytes = result.result_json_bytes
    if input_text != run_request.config_text:
        raise GcsimFinalistOptimizerError(
            "optimizer input artifact differs from the exact run request"
        )
    if not optimized_text.strip() or "\x00" in optimized_text:
        raise GcsimFinalistOptimizerError(
            "optimized config is empty or contains NUL"
        )
    try:
        _validated_prepared_config(optimized_text, request.wearer_ids)
    except GcsimFarmingPipelineError as exc:
        raise GcsimFinalistOptimizerError(
            f"optimized config violates the static-target contract: {exc}"
        ) from exc
    _validate_optimizer_owned_config_diff(input_text, optimized_text, state)
    _validate_optimizer_substat_budget(optimized_text, state, request)
    _validate_exact_set_evidence(optimized_text, state)
    allocations = _extract_allocations(optimized_text, state)
    try:
        result_payload = json.loads(result_bytes.decode("utf-8"))
        parsed_summary = parse_gcsim_result_payload(result_payload)
    except (UnicodeDecodeError, json.JSONDecodeError, GcsimResultParseError) as exc:
        raise GcsimFinalistOptimizerError(
            f"could not re-parse optimizer result evidence: {exc}"
        ) from exc
    if parsed_summary != result.summary:
        raise GcsimFinalistOptimizerError(
            "optimizer summary differs from the persisted result JSON"
        )
    summary: GcsimResultSummary = result.summary
    if summary.iterations != request.budget.validation_iterations:
        raise GcsimFinalistOptimizerError(
            "optimizer result iteration count differs from validation_iterations"
        )
    if (
        summary.dps_mean is None
        or not math.isfinite(summary.dps_mean)
        or summary.dps_mean < 0
        or summary.dps_se is not None
        and (not math.isfinite(summary.dps_se) or summary.dps_se < 0)
        or summary.incomplete_characters
    ):
        raise GcsimFinalistOptimizerError(
            "optimizer result lacks valid complete-team DPS evidence"
        )
    return GcsimFinalistOptimizerOutcome(
        ordinal=ordinal,
        state=state,
        dps_mean=summary.dps_mean,
        dps_se=summary.dps_se,
        iterations=summary.iterations,
        optimizer_input_config_text=input_text,
        optimizer_input_sha256=_text_sha256(input_text),
        optimized_config_text=optimized_text,
        optimized_config_sha256=_text_sha256(optimized_text),
        result_json_bytes=result_bytes,
        result_json_sha256=hashlib.sha256(result_bytes).hexdigest(),
        allocation_sha256=_canonical_sha256(_allocation_payload(allocations)),
        allocations=allocations,
        cache_identity_sha256=cache_identity_sha256,
        runner_result=result,
    )


def _extract_allocations(
    optimized_text: str,
    state: FullTeamPhysicalState,
) -> tuple[GcsimOptimizedWearerAllocation, ...]:
    lines_by_wearer: dict[str, list[str]] = {
        choice.wearer_id: [] for choice in state.choices
    }
    for raw_line in optimized_text.splitlines():
        match = _ADD_STATS_RE.match(raw_line)
        if match is None:
            continue
        wearer = match.group("wearer")
        if wearer not in lines_by_wearer:
            raise GcsimFinalistOptimizerError(
                "optimized config carries add-stats evidence for an unknown wearer"
            )
        line = raw_line.strip()
        if not match.group("body").strip():
            raise GcsimFinalistOptimizerError(
                "optimized config contains an empty add-stats row"
            )
        lines_by_wearer[wearer].append(line)
    allocations = tuple(
        GcsimOptimizedWearerAllocation(
            wearer_id=choice.wearer_id,
            set_key=choice.set_key,
            main_stat_layout_id=choice.main_stat_layout_id,
            offpiece_slot=choice.offpiece_slot,
            add_stats_lines=tuple(lines_by_wearer[choice.wearer_id]),
        )
        for choice in state.choices
    )
    return allocations


def _validate_optimizer_owned_config_diff(
    input_text: str,
    optimized_text: str,
    state: FullTeamPhysicalState,
) -> None:
    """Allow only upstream's deterministic main-row + one-substat-row rewrite."""

    if optimized_text.strip() == input_text.strip():
        raise GcsimFinalistOptimizerError(
            "optimized config must differ from its optimizer input"
        )
    wearer_ids = tuple(choice.wearer_id for choice in state.choices)
    input_contract = _partition_optimizer_config(
        input_text,
        wearer_ids,
        label="optimizer input",
    )
    output_contract = _partition_optimizer_config(
        optimized_text,
        wearer_ids,
        label="optimized config",
    )
    input_main_rows, output_main_rows = input_contract[1], output_contract[1]
    output_substat_rows = output_contract[2]
    output_positions = output_contract[3]
    for wearer in wearer_ids:
        if len(input_main_rows[wearer]) != 1:
            raise GcsimFinalistOptimizerError(
                f"optimizer input must contain exactly one main-stat row for {wearer}"
            )
        if len(output_main_rows[wearer]) != 1:
            raise GcsimFinalistOptimizerError(
                "optimized config must contain exactly one main-stat row "
                f"for {wearer}"
            )
        if output_main_rows[wearer] != input_main_rows[wearer]:
            raise GcsimFinalistOptimizerError(
                f"optimized config changed the exact main-stat row for {wearer}"
            )
        if len(output_substat_rows[wearer]) != 1:
            raise GcsimFinalistOptimizerError(
                "optimized config must contain exactly one optimizer substat row "
                f"for {wearer}"
            )
    if input_contract[0] != output_contract[0]:
        raise GcsimFinalistOptimizerError(
            "optimized config changed the non-stat config shell"
        )
    for wearer in wearer_ids:
        main_index, substat_index = output_positions[wearer]
        if substat_index != main_index + 1:
            raise GcsimFinalistOptimizerError(
                "optimizer substat row must immediately follow its main-stat row "
                f"for {wearer}"
            )
        _validate_optimizer_substat_row(
            output_substat_rows[wearer][0],
            wearer,
        )


def _partition_optimizer_config(
    config_text: str,
    wearer_ids: tuple[str, ...],
    *,
    label: str,
) -> tuple[
    tuple[str, ...],
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
    dict[str, tuple[int, int]],
]:
    expected = set(wearer_ids)
    shell: list[str] = []
    main_rows: dict[str, list[str]] = {wearer: [] for wearer in wearer_ids}
    substat_rows: dict[str, list[str]] = {wearer: [] for wearer in wearer_ids}
    main_positions: dict[str, list[int]] = {wearer: [] for wearer in wearer_ids}
    substat_positions: dict[str, list[int]] = {wearer: [] for wearer in wearer_ids}
    lines = config_text.splitlines()
    for index, raw_line in enumerate(lines):
        match = _ADD_STATS_RE.match(raw_line)
        if match is None:
            shell.append(raw_line)
            continue
        wearer = match.group("wearer")
        if wearer not in expected:
            raise GcsimFinalistOptimizerError(
                f"{label} contains add-stats evidence for an unknown wearer"
            )
        normalized = raw_line.strip()
        if _MAIN_STATS_RE.match(raw_line) is not None:
            main_rows[wearer].append(normalized)
            main_positions[wearer].append(index)
            shell.append(f"<gtt-main-stats:{wearer}:{normalized}>")
        else:
            substat_rows[wearer].append(normalized)
            substat_positions[wearer].append(index)

    while shell and not shell[0].strip():
        shell.pop(0)
    while shell and not shell[-1].strip():
        shell.pop()
    positions: dict[str, tuple[int, int]] = {}
    for wearer in wearer_ids:
        if len(main_positions[wearer]) == 1 and len(substat_positions[wearer]) == 1:
            positions[wearer] = (
                main_positions[wearer][0],
                substat_positions[wearer][0],
            )
        else:
            positions[wearer] = (-1, -1)
    return (
        tuple(shell),
        {wearer: tuple(main_rows[wearer]) for wearer in wearer_ids},
        {wearer: tuple(substat_rows[wearer]) for wearer in wearer_ids},
        positions,
    )


def _validate_optimizer_substat_row(
    row: str,
    wearer: str,
) -> tuple[tuple[str, float, float | None], ...]:
    match = _ADD_STATS_RE.match(row)
    if match is None or match.group("wearer") != wearer:
        raise GcsimFinalistOptimizerError(
            "optimizer substat row does not match its wearer"
        )
    tokens = match.group("body").strip().split()
    if not tokens:
        raise GcsimFinalistOptimizerError("optimizer substat row is empty")
    observed_keys: set[str] = set()
    parsed: list[tuple[str, float, float | None]] = []
    for token in tokens:
        term = _SUBSTAT_TERM_RE.match(token)
        if term is None:
            raise GcsimFinalistOptimizerError(
                f"optimizer substat row contains a non-canonical term: {token!r}"
            )
        key = term.group("key")
        if key in observed_keys:
            raise GcsimFinalistOptimizerError(
                f"optimizer substat row repeats stat key: {key!r}"
            )
        observed_keys.add(key)
        value = float(term.group("value"))
        raw_count = term.group("count")
        count = None if raw_count is None else float(raw_count)
        if value < 0 or count is not None and count < 0:
            raise GcsimFinalistOptimizerError(
                "optimizer substat values and scalars must be non-negative"
            )
        parsed.append((key, value, count))
    return tuple(parsed)


def _validate_request_substat_budget_feasibility(
    request: GcsimFinalistOptimizerRequest,
) -> None:
    """Reject option/layout combinations the pinned optimizer cannot allocate."""

    for state in request.finalists:
        for choice in state.choices:
            expected_liquid, _fixed, _rarity, capacities = (
                _substat_budget_contract(request, choice)
            )
            negative = tuple(
                key for key, capacity in capacities.items() if capacity < 0
            )
            if negative:
                raise GcsimFinalistOptimizerError(
                    "optimizer substat budget gives a negative liquid cap for "
                    f"{choice.wearer_id}: {', '.join(negative)}"
                )
            if expected_liquid > sum(capacities.values()):
                raise GcsimFinalistOptimizerError(
                    "optimizer total liquid substat budget exceeds the available "
                    f"per-stat capacity for {choice.wearer_id}"
                )


def _validate_optimizer_substat_budget(
    optimized_text: str,
    state: FullTeamPhysicalState,
    request: GcsimFinalistOptimizerRequest,
) -> None:
    """Verify upstream output represents one feasible integer-roll allocation."""

    wearer_ids = tuple(choice.wearer_id for choice in state.choices)
    partition = _partition_optimizer_config(
        optimized_text,
        wearer_ids,
        label="optimized config",
    )
    rows_by_wearer = partition[2]
    show_scalars = _optimizer_option_int(
        request,
        "show_substat_scalars",
        1,
    ) > 0
    expected_keys = set(GCSIM_SUBSTAT_ROLL_VALUES)

    for choice in state.choices:
        rows = rows_by_wearer[choice.wearer_id]
        if len(rows) != 1:
            raise GcsimFinalistOptimizerError(
                "optimized config must contain exactly one optimizer substat row "
                f"for {choice.wearer_id}"
            )
        terms = _validate_optimizer_substat_row(rows[0], choice.wearer_id)
        if {key for key, _value, _count in terms} != expected_keys:
            raise GcsimFinalistOptimizerError(
                "optimizer substat row must contain every pinned optimizer stat "
                f"exactly once for {choice.wearer_id}"
            )

        expected_liquid, fixed, rarity_modifier, capacities = (
            _substat_budget_contract(request, choice)
        )
        observed_liquid = 0
        for key, value, scalar in terms:
            roll_unit = GCSIM_SUBSTAT_ROLL_VALUES[key] * rarity_modifier
            if show_scalars:
                if scalar is None:
                    raise GcsimFinalistOptimizerError(
                        "optimizer substat row omitted required roll scalars for "
                        f"{choice.wearer_id}"
                    )
                if not _matches_gcsim_six_digit_float(value, roll_unit):
                    raise GcsimFinalistOptimizerError(
                        "optimizer substat roll unit does not match the pinned "
                        f"engine contract for {choice.wearer_id}/{key}"
                    )
                total_count = _required_integer_roll_count(
                    scalar,
                    wearer=choice.wearer_id,
                    stat_key=key,
                )
            else:
                if scalar is not None:
                    raise GcsimFinalistOptimizerError(
                        "optimizer substat row unexpectedly contains roll scalars "
                        f"for {choice.wearer_id}"
                    )
                nearest = int(round(value / roll_unit))
                expected_value = roll_unit * nearest
                if nearest < 0 or not _matches_gcsim_six_digit_float(
                    value,
                    expected_value,
                ):
                    raise GcsimFinalistOptimizerError(
                        "optimizer substat value is not an integral pinned roll "
                        f"allocation for {choice.wearer_id}/{key}"
                    )
                total_count = nearest

            liquid_count = total_count - fixed
            if liquid_count < 0:
                raise GcsimFinalistOptimizerError(
                    "optimizer substat allocation is below the fixed-roll floor "
                    f"for {choice.wearer_id}/{key}"
                )
            if liquid_count > capacities[key]:
                raise GcsimFinalistOptimizerError(
                    "optimizer substat allocation exceeds the main-stat-aware "
                    f"liquid cap for {choice.wearer_id}/{key}"
                )
            observed_liquid += liquid_count

        if observed_liquid != expected_liquid:
            raise GcsimFinalistOptimizerError(
                "optimizer substat allocation uses an unexpected total liquid "
                f"roll budget for {choice.wearer_id}: observed "
                f"{observed_liquid}, expected {expected_liquid}"
            )


def _substat_budget_contract(
    request: GcsimFinalistOptimizerRequest,
    choice,
) -> tuple[int, int, float, dict[str, int]]:
    total_liquid = _optimizer_option_int(
        request,
        "total_liquid_substats",
        DEFAULT_TOTAL_LIQUID_SUBSTATS,
    )
    individual_cap = _optimizer_option_int(
        request,
        "indiv_liquid_cap",
        DEFAULT_INDIVIDUAL_LIQUID_CAP,
    )
    fixed = _optimizer_option_int(
        request,
        "fixed_substats_count",
        DEFAULT_FIXED_SUBSTATS_COUNT,
    )
    capability = request.engine_context.catalog.get(choice.set_key)
    if capability is None or capability.max_rarity not in (4, 5):
        raise GcsimFinalistOptimizerError(
            f"cannot derive substat rarity for set {choice.set_key!r}"
        )
    four_star_count = 4 if capability.max_rarity == 4 else 0
    expected_liquid = max(
        total_liquid - FOUR_STAR_LIQUID_ROLL_PENALTY * four_star_count,
        0,
    )
    rarity_modifier = 1.0 - FOUR_STAR_RARITY_PENALTY * four_star_count
    layout = request.layout_catalog[choice.wearer_id][
        choice.main_stat_layout_id
    ]
    main_counts = {key: 0 for key in GCSIM_SUBSTAT_ROLL_VALUES}
    for key in ("hp", "atk", layout.sands, layout.goblet, layout.circlet):
        if key in main_counts:
            main_counts[key] += 1
    capacities = {
        key: individual_cap - fixed * main_counts[key]
        for key in GCSIM_SUBSTAT_ROLL_VALUES
    }
    return expected_liquid, fixed, rarity_modifier, capacities


def _optimizer_option_int(
    request: GcsimFinalistOptimizerRequest,
    key: str,
    default: int,
) -> int:
    return int(float(request.optimizer_options.get(key, default)))


def _required_integer_roll_count(
    value: float,
    *,
    wearer: str,
    stat_key: str,
) -> int:
    if not value.is_integer():
        raise GcsimFinalistOptimizerError(
            "optimizer substat scalar is not an integer roll count for "
            f"{wearer}/{stat_key}"
        )
    return int(value)


def _matches_gcsim_six_digit_float(observed: float, expected: float) -> bool:
    if expected == 0:
        return observed == 0
    return math.isclose(observed, expected, rel_tol=5e-6, abs_tol=1e-9)


def _validate_exact_set_evidence(
    optimized_text: str,
    state: FullTeamPhysicalState,
) -> None:
    observed: list[tuple[str, str]] = []
    for raw_line in optimized_text.splitlines():
        if _ANY_SET_RE.match(raw_line) is None:
            continue
        exact = _EXACT_SET_RE.match(raw_line)
        if exact is None:
            raise GcsimFinalistOptimizerError(
                "optimized config contains a non-canonical artifact-set row"
            )
        observed.append((exact.group("wearer"), exact.group("set")))
    expected = tuple((choice.wearer_id, choice.set_key) for choice in state.choices)
    if tuple(observed) != expected:
        raise GcsimFinalistOptimizerError(
            "optimized config does not preserve the exact finalist set assignments"
        )


def _required_directory(raw_path: str, field_name: str) -> Path:
    if not raw_path:
        raise GcsimFinalistOptimizerError(f"optimizer {field_name} is missing")
    path = Path(raw_path).expanduser().resolve()
    if not path.is_dir():
        raise GcsimFinalistOptimizerError(
            f"optimizer {field_name} is not an existing directory"
        )
    return path


def _required_child_file(
    run_dir: Path,
    raw_path: str,
    expected_name: str,
    label: str,
) -> Path:
    if not raw_path:
        raise GcsimFinalistOptimizerError(f"{label} path is missing")
    path = Path(raw_path).expanduser().resolve()
    if path != (run_dir / expected_name).resolve() or not path.is_file():
        raise GcsimFinalistOptimizerError(
            f"{label} is not the expected session-owned file"
        )
    return path


def _outcome_rank_key(outcome: GcsimFinalistOptimizerOutcome):
    return (
        -outcome.dps_mean,
        math.inf if outcome.dps_se is None else outcome.dps_se,
        outcome.state.key,
        outcome.ordinal,
    )


def _allocation_payload(
    allocations: Sequence[GcsimOptimizedWearerAllocation],
) -> list[dict[str, object]]:
    return [
        {
            "wearer_id": item.wearer_id,
            "set_key": item.set_key,
            "main_stat_layout_id": item.main_stat_layout_id,
            "offpiece_slot": item.offpiece_slot,
            "add_stats_lines": list(item.add_stats_lines),
        }
        for item in allocations
    ]


def _layout_catalog_payload(
    request: GcsimFinalistOptimizerRequest,
) -> list[dict[str, object]]:
    return [
        {
            "wearer_id": wearer,
            "layouts": [
                {
                    "layout_id": layout_id,
                    "sands": layout.sands,
                    "goblet": layout.goblet,
                    "circlet": layout.circlet,
                }
                for layout_id, layout in sorted(
                    request.layout_catalog[wearer].items()
                )
            ],
        }
        for wearer in request.wearer_ids
    ]


def _finalist_domain_payload(
    finalists: Sequence[FullTeamPhysicalState],
) -> list[list[list[str]]]:
    return [
        [list(choice.key) for choice in state.choices]
        for state in finalists
    ]


def _budget_payload(budget: GcsimFinalistOptimizerBudget) -> dict[str, object]:
    return {
        "max_finalists": budget.max_finalists,
        "top_n": budget.top_n,
        "worker_count": budget.worker_count,
        "validation_iterations": budget.validation_iterations,
        "overall_deadline_seconds": float(budget.overall_deadline_seconds),
        "optimizer_timeout_seconds": float(budget.optimizer_timeout_seconds),
        "simulation_timeout_seconds": float(budget.simulation_timeout_seconds),
    }


def _request_payload(request: GcsimFinalistOptimizerRequest) -> dict[str, object]:
    context = request.engine_context
    return {
        "provenance_schema_version": GCSIM_FINALIST_OPTIMIZER_PROVENANCE_SCHEMA,
        "engine": {
            "engine_id": context.engine_id,
            "engine_version": context.engine_version,
            "optimizer_contract_version": context.optimizer_contract_version,
            "artifact_sha256": context.artifact_sha256,
            "engine_tree_sha256": context.engine_tree_sha256,
            "catalog_fingerprint": context.catalog.source_fingerprint,
            "binding_sha256": context.binding_sha256,
        },
        "source_config_sha256": request.source_config_sha256,
        "validation_config_sha256": request.validation_config_sha256,
        "wearer_ids": list(request.wearer_ids),
        "layout_catalog_sha256": request.layout_catalog_sha256,
        "finalist_domain_sha256": request.finalist_domain_sha256,
        "budget_sha256": request.budget_sha256,
        "optimizer_options": [
            [str(key), str(value)]
            for key, value in sorted(request.optimizer_options.items())
        ],
        "environment": [
            [key, value] for key, value in sorted(request.environment.items())
        ],
    }


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _safe_error(exc: BaseException) -> str:
    text = str(exc).strip().replace("\x00", "")
    return text[:2000] or type(exc).__name__


__all__ = [
    "GCSIM_FINALIST_OPTIMIZER_PROVENANCE_SCHEMA",
    "GcsimFinalistAttemptStatus",
    "GcsimFinalistOptimizerAttempt",
    "GcsimFinalistOptimizerBudget",
    "GcsimFinalistOptimizerError",
    "GcsimFinalistOptimizerOutcome",
    "GcsimFinalistOptimizerRequest",
    "GcsimFinalistOptimizerResult",
    "GcsimFinalistOptimizerSession",
    "GcsimFinalistOptimizerStatus",
    "GcsimOptimizedWearerAllocation",
    "OptimizerSessionFactory",
    "run_gcsim_finalist_optimizer",
]
