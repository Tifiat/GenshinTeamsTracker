"""Bound ordinary-GCSIM evaluator and bounded farming-screen scheduler.

This module executes already-rendered *whole-team* configs for
``farming_search.SetProfileCandidate`` rows.  It intentionally does not render
stat probes, compose four-character beams, or run the expensive substat
optimizer.  Its boundary is the cheaper, ordinary ``gcsim -c ... -out ...``
screen used by those later search layers.

Every request freezes its config/environment and binds the candidate to one
resealed engine context.  The scheduler caps both process count and the sum of
GCSIM workers, persists only successful semantic results, and returns typed
best-so-far output when cancelled or when its overall deadline is reached.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
from queue import Empty, Queue
import re
import subprocess
from threading import Event, Lock, Thread
from tempfile import TemporaryDirectory
from time import monotonic, perf_counter
from types import MappingProxyType
from typing import Protocol
from uuid import uuid4

from .artifact_runner import (
    GcsimResultParseError,
    GcsimResultSummary,
    parse_gcsim_result_file,
)
from .config_structure import (
    build_gcsim_comment_free_view,
    validate_gcsim_farming_static_config,
)
from .engine_store import PROJECT_ROOT
from .farming_search import CandidateEvaluation, SetProfileCandidate
from .optimizer_backend import (
    GcsimBoundOptimizerError,
    resolve_gcsim_optimizer_worker_count,
)
from .optimizer_cache import (
    GcsimOptimizerCacheError,
    GcsimOptimizerCacheIdentity,
    GcsimOptimizerCacheStore,
)
from .optimizer_config import (
    ARTIFACT_MAIN_STAT_SLOTS,
    apply_gcsim_optimizer_worker_budget,
)
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .runtime_probe import _trim_probe_text


GCSIM_FARMING_EVALUATION_CONTRACT = "ordinary-screen-v2"
GCSIM_FARMING_EVALUATION_IDENTITY_SCHEMA = 2
GCSIM_FARMING_EVALUATION_CACHE_SCHEMA = 2
GCSIM_FARMING_EVALUATION_CACHE_MODE = "farming_ordinary_screen_v2"
DEFAULT_GCSIM_FARMING_RUNS_DIR = PROJECT_ROOT / "data" / "gcsim" / "farming-runs"
DEFAULT_GCSIM_FARMING_CANDIDATE_TIMEOUT_SECONDS = 30.0
PROCESS_POLL_INTERVAL_SECONDS = 0.05
PROCESS_TERMINATE_GRACE_SECONDS = 0.5
_GCSIM_FARMING_AMBIENT_ENV_ALLOWLIST = frozenset(
    key.casefold()
    for key in (
        "APPDATA",
        "COMSPEC",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USERPROFILE",
        "WINDIR",
    )
)

_CONFIG_OPTIONS_LINE_RE = re.compile(
    r"(?m)^(?P<prefix>[ \t]*options\b)(?P<body>[^;\r\n]*);"
    r"[ \t]*(?P<ending>\r?)$"
)
_CONFIG_WORKERS_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])workers\s*=\s*[^\s;]+"
)
_CONFIG_ITERATION_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])iteration\s*=\s*[^\s;]+"
)
_COMPARISON_VARIABLE_ROW_RE = re.compile(
    r"^\s*[A-Za-z0-9_]+\s+add\s+(?:set|stats)\b[^;]*;\s*$",
    re.IGNORECASE,
)

_PROCESS_TERMINAL_COMPLETED = "completed"
_PROCESS_TERMINAL_CANCELLED = "cancelled"
_PROCESS_TERMINAL_TIMEOUT = "timeout"

CandidateKey = tuple[str, str, str, str, str]
EvaluationCandidateKeys = tuple[CandidateKey, ...]


class GcsimFarmingEvaluationError(RuntimeError):
    """Raised when a farming evaluation cannot be bound safely."""


class GcsimFarmingEvaluationStatus(str, Enum):
    PASSED = "passed"
    CACHED = "cached"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    RUN_DIR_EXISTS = "run_dir_exists"
    RUN_DIR_FAILED = "run_dir_failed"
    ARTIFACT_MISSING = "artifact_missing"
    ARTIFACT_IDENTITY_MISMATCH = "artifact_identity_mismatch"
    START_FAILED = "start_failed"
    PROCESS_FAILED = "process_failed"
    RESULT_MISSING = "result_missing"
    RESULT_INVALID = "result_invalid"
    INTERNAL_ERROR = "internal_error"
    SKIPPED_DEADLINE = "skipped_deadline"
    SKIPPED_CANCELLED = "skipped_cancelled"


class GcsimFarmingBatchStatus(str, Enum):
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    DEADLINE_REACHED = "deadline_reached"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class GcsimFarmingEvaluationIdentity:
    """Content identity for one ordinary simulation candidate.

    Run-directory and wall-clock limits are deliberately absent: they do not
    change the simulation answer.  Worker count and the caller environment are
    included because they are part of the exact execution provenance and may
    affect a future engine's seed/parallel behavior.
    """

    candidate_keys: EvaluationCandidateKeys
    comparison_context_sha256: str
    investment_signature: str
    source_config_sha256: str
    engine_id: str
    engine_version: str
    artifact_sha256: str
    engine_binding_sha256: str
    catalog_fingerprint: str
    worker_count: int
    expected_iterations: int
    environment_sha256: str
    contract: str = GCSIM_FARMING_EVALUATION_CONTRACT
    schema_version: int = GCSIM_FARMING_EVALUATION_IDENTITY_SCHEMA

    def __post_init__(self) -> None:
        _validate_candidate_keys(self.candidate_keys)
        for field_name in (
            "investment_signature",
            "engine_id",
            "engine_version",
            "contract",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise ValueError(f"{field_name} must be a non-empty trimmed string")
        for field_name in (
            "comparison_context_sha256",
            "source_config_sha256",
            "artifact_sha256",
            "engine_binding_sha256",
            "catalog_fingerprint",
            "environment_sha256",
        ):
            if not _is_sha256(getattr(self, field_name)):
                raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
        if isinstance(self.worker_count, bool) or not isinstance(self.worker_count, int):
            raise ValueError("worker_count must be an integer")
        if self.worker_count <= 0:
            raise ValueError("worker_count must be positive")
        if (
            isinstance(self.expected_iterations, bool)
            or not isinstance(self.expected_iterations, int)
            or self.expected_iterations <= 0
        ):
            raise ValueError("expected_iterations must be a positive integer")
        if self.schema_version != GCSIM_FARMING_EVALUATION_IDENTITY_SCHEMA:
            raise ValueError("unsupported farming evaluation identity schema")

    @property
    def identity_sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.to_dict()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "contract": self.contract,
            "candidate_keys": [list(key) for key in self.candidate_keys],
            "comparison_context_sha256": self.comparison_context_sha256,
            "investment_signature": self.investment_signature,
            "source_config_sha256": self.source_config_sha256,
            "engine_id": self.engine_id,
            "engine_version": self.engine_version,
            "artifact_sha256": self.artifact_sha256,
            "engine_binding_sha256": self.engine_binding_sha256,
            "catalog_fingerprint": self.catalog_fingerprint,
            "worker_count": self.worker_count,
            "expected_iterations": self.expected_iterations,
            "environment_sha256": self.environment_sha256,
        }


@dataclass(frozen=True, slots=True)
class GcsimFarmingEvaluationRequest:
    candidate: SetProfileCandidate | None
    config_text: str
    comparison_context_sha256: str
    investment_signature: str
    engine_id: str
    engine_version: str
    artifact_path: str
    artifact_sha256: str
    engine_binding_sha256: str
    catalog_fingerprint: str
    worker_count: int
    expected_iterations: int
    timeout_seconds: float = DEFAULT_GCSIM_FARMING_CANDIDATE_TIMEOUT_SECONDS
    environment: Mapping[str, str] = field(default_factory=dict, repr=False)
    run_dir: str | None = None
    novelty_score: float = 0.0
    novelty_tags: tuple[str, ...] = ()
    joint_candidate_keys: EvaluationCandidateKeys = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "config_text", str(self.config_text))
        object.__setattr__(
            self,
            "environment",
            MappingProxyType(
                {
                    str(key): str(value)
                    for key, value in self.environment.items()
                }
            ),
        )
        object.__setattr__(self, "novelty_tags", tuple(self.novelty_tags))
        if self.candidate is not None:
            if self.joint_candidate_keys and self.joint_candidate_keys != (
                self.candidate.key,
            ):
                raise ValueError(
                    "single candidate conflicts with joint_candidate_keys"
                )
            object.__setattr__(
                self,
                "joint_candidate_keys",
                (self.candidate.key,),
            )
        else:
            object.__setattr__(
                self,
                "joint_candidate_keys",
                tuple(tuple(key) for key in self.joint_candidate_keys),
            )
        _validate_candidate_keys(self.joint_candidate_keys)
        if not self.config_text.strip() or "\x00" in self.config_text:
            raise ValueError("config_text must be non-empty and contain no NUL")
        validate_gcsim_farming_static_config(self.config_text)
        if not isinstance(self.artifact_path, str) or not self.artifact_path.strip():
            raise ValueError("artifact_path must be a non-empty string")
        if isinstance(self.worker_count, bool) or not isinstance(self.worker_count, int):
            raise ValueError("worker_count must be an integer")
        if self.worker_count <= 0:
            raise ValueError("worker_count must be positive")
        _validate_request_worker_binding(
            self.config_text,
            self.environment,
            self.worker_count,
            self.expected_iterations,
        )
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        if not math.isfinite(self.novelty_score):
            raise ValueError("novelty_score must be finite")
        if len(set(self.novelty_tags)) != len(self.novelty_tags):
            raise ValueError("novelty_tags must be unique")
        for tag in self.novelty_tags:
            if not isinstance(tag, str) or not tag or tag != tag.strip():
                raise ValueError("novelty tags must be non-empty trimmed strings")
        # Constructing the identity here makes direct/test construction fail
        # closed just like the bound builder.
        _ = self.identity

    @property
    def identity(self) -> GcsimFarmingEvaluationIdentity:
        return GcsimFarmingEvaluationIdentity(
            candidate_keys=self.joint_candidate_keys,
            comparison_context_sha256=self.comparison_context_sha256,
            investment_signature=self.investment_signature,
            source_config_sha256=_sha256_text(self.config_text),
            engine_id=self.engine_id,
            engine_version=self.engine_version,
            artifact_sha256=self.artifact_sha256,
            engine_binding_sha256=self.engine_binding_sha256,
            catalog_fingerprint=self.catalog_fingerprint,
            worker_count=self.worker_count,
            expected_iterations=self.expected_iterations,
            environment_sha256=_sha256_environment(self.environment),
        )

    @property
    def candidate_keys(self) -> EvaluationCandidateKeys:
        return self.joint_candidate_keys

    @property
    def comparison_shell_sha256(self) -> str:
        return _comparison_shell_sha256(self.config_text)

    @property
    def cache_identity(self) -> GcsimOptimizerCacheIdentity:
        identity = self.identity
        return GcsimOptimizerCacheIdentity(
            engine_sha256=identity.artifact_sha256,
            engine_version=identity.engine_version,
            source_config_sha256=identity.source_config_sha256,
            mode=GCSIM_FARMING_EVALUATION_CACHE_MODE,
            optimizer_options=(
                ("contract", identity.contract),
                ("environment_sha256", identity.environment_sha256),
                ("worker_count", str(identity.worker_count)),
                ("expected_iterations", str(identity.expected_iterations)),
            ),
            catalog_fingerprint=identity.catalog_fingerprint,
            candidate_key=identity.identity_sha256,
        )


def prepare_bound_gcsim_farming_evaluation(
    *,
    engine_context: GcsimOptimizerEngineContext,
    candidate: SetProfileCandidate,
    config_text: str,
    comparison_context_sha256: str,
    investment_signature: str,
    worker_count: int | None = None,
    timeout_seconds: float = DEFAULT_GCSIM_FARMING_CANDIDATE_TIMEOUT_SECONDS,
    environment: Mapping[str, str] | None = None,
    environment_is_frozen: bool = False,
    run_dir: str | Path | None = None,
    novelty_score: float = 0.0,
    novelty_tags: Sequence[str] = (),
) -> GcsimFarmingEvaluationRequest:
    """Bind a rendered ordinary-sim config to its exact engine/candidate."""

    return _prepare_bound_gcsim_farming_evaluation(
        engine_context=engine_context,
        candidate=candidate,
        candidate_keys=(candidate.key,),
        config_text=config_text,
        comparison_context_sha256=comparison_context_sha256,
        investment_signature=investment_signature,
        worker_count=worker_count,
        timeout_seconds=timeout_seconds,
        environment=environment,
        environment_is_frozen=environment_is_frozen,
        run_dir=run_dir,
        novelty_score=novelty_score,
        novelty_tags=novelty_tags,
    )


def prepare_bound_gcsim_farming_joint_evaluation(
    *,
    engine_context: GcsimOptimizerEngineContext,
    candidate_keys: Sequence[CandidateKey],
    config_text: str,
    comparison_context_sha256: str,
    investment_signature: str,
    worker_count: int | None = None,
    timeout_seconds: float = DEFAULT_GCSIM_FARMING_CANDIDATE_TIMEOUT_SECONDS,
    environment: Mapping[str, str] | None = None,
    environment_is_frozen: bool = False,
    run_dir: str | Path | None = None,
    novelty_score: float = 0.0,
    novelty_tags: Sequence[str] = (),
) -> GcsimFarmingEvaluationRequest:
    """Bind a fully rendered joint team state without inventing one wearer."""

    normalized_keys = tuple(tuple(key) for key in candidate_keys)
    return _prepare_bound_gcsim_farming_evaluation(
        engine_context=engine_context,
        candidate=None,
        candidate_keys=normalized_keys,
        config_text=config_text,
        comparison_context_sha256=comparison_context_sha256,
        investment_signature=investment_signature,
        worker_count=worker_count,
        timeout_seconds=timeout_seconds,
        environment=environment,
        environment_is_frozen=environment_is_frozen,
        run_dir=run_dir,
        novelty_score=novelty_score,
        novelty_tags=novelty_tags,
    )


def _prepare_bound_gcsim_farming_evaluation(
    *,
    engine_context: GcsimOptimizerEngineContext,
    candidate: SetProfileCandidate | None,
    candidate_keys: EvaluationCandidateKeys,
    config_text: str,
    comparison_context_sha256: str,
    investment_signature: str,
    worker_count: int | None,
    timeout_seconds: float,
    environment: Mapping[str, str] | None,
    environment_is_frozen: bool,
    run_dir: str | Path | None,
    novelty_score: float,
    novelty_tags: Sequence[str],
) -> GcsimFarmingEvaluationRequest:
    if not engine_context.trusted:
        raise GcsimFarmingEvaluationError(
            "Farming evaluator requires a resealed trusted engine context."
        )
    _validate_bound_candidate_keys(engine_context, candidate_keys)

    try:
        resolved_workers = resolve_gcsim_optimizer_worker_count(worker_count)
        prepared_config = apply_gcsim_optimizer_worker_budget(
            config_text,
            resolved_workers,
        )
        expected_iterations = _canonical_config_iterations(prepared_config)
    except (GcsimBoundOptimizerError, ValueError) as exc:
        raise GcsimFarmingEvaluationError(str(exc)) from exc
    resolved_environment = (
        normalize_gcsim_farming_frozen_environment(
            environment,
            worker_count=resolved_workers,
        )
        if environment_is_frozen
        else freeze_gcsim_farming_environment(
            environment,
            worker_count=resolved_workers,
        )
    )
    return GcsimFarmingEvaluationRequest(
        candidate=candidate,
        config_text=prepared_config,
        comparison_context_sha256=comparison_context_sha256,
        investment_signature=investment_signature,
        engine_id=engine_context.engine_id,
        engine_version=engine_context.engine_version,
        artifact_path=str(Path(engine_context.artifact_path).resolve()),
        artifact_sha256=engine_context.artifact_sha256,
        engine_binding_sha256=engine_context.binding_sha256,
        catalog_fingerprint=engine_context.catalog.source_fingerprint,
        worker_count=resolved_workers,
        expected_iterations=expected_iterations,
        timeout_seconds=timeout_seconds,
        environment=resolved_environment,
        run_dir=None if run_dir is None else str(Path(run_dir).resolve()),
        novelty_score=novelty_score,
        novelty_tags=tuple(novelty_tags),
        joint_candidate_keys=candidate_keys,
    )


@dataclass(frozen=True, slots=True)
class GcsimFarmingEvaluationResult:
    status: GcsimFarmingEvaluationStatus
    success: bool
    request_identity_sha256: str
    cache_key: str
    candidate_keys: EvaluationCandidateKeys
    comparison_context_sha256: str
    expected_iterations: int
    evaluation: CandidateEvaluation | None = None
    summary: GcsimResultSummary = field(default_factory=GcsimResultSummary)
    cache_hit: bool = False
    engine_binding_sha256: str = ""
    artifact_sha256: str = ""
    source_config_sha256: str = ""
    run_dir: str = ""
    config_path: str = ""
    result_path: str = ""
    command: tuple[str, ...] = ()
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    elapsed_seconds: float = 0.0
    error: str = ""

    def __post_init__(self) -> None:
        if self.success != (self.status in {
            GcsimFarmingEvaluationStatus.PASSED,
            GcsimFarmingEvaluationStatus.CACHED,
        }):
            raise ValueError("success does not match farming evaluation status")
        _validate_candidate_keys(self.candidate_keys)
        if self.success and _summary_error(self.summary):
            raise ValueError("successful farming result requires a valid DPS summary")
        if (
            isinstance(self.expected_iterations, bool)
            or not isinstance(self.expected_iterations, int)
            or self.expected_iterations <= 0
        ):
            raise ValueError("expected_iterations must be a positive integer")
        if self.success and self.summary.iterations != self.expected_iterations:
            raise ValueError(
                "successful result iterations do not match the frozen request"
            )
        if self.evaluation is not None and (
            self.candidate_keys != (self.evaluation.candidate.key,)
        ):
            raise ValueError("evaluation candidate does not match result candidate_keys")
        if self.evaluation is not None and not self.success:
            raise ValueError("failed farming result cannot carry an evaluation")
        if self.evaluation is not None and (
            self.evaluation.expected_dps != self.summary.dps_mean
            or self.evaluation.standard_error != self.summary.dps_se
        ):
            raise ValueError(
                "evaluation DPS/uncertainty must exactly match the result summary"
            )
        if self.cache_hit != (self.status is GcsimFarmingEvaluationStatus.CACHED):
            raise ValueError("cache_hit does not match farming evaluation status")
        for field_name in (
            "request_identity_sha256",
            "cache_key",
            "comparison_context_sha256",
            "engine_binding_sha256",
            "artifact_sha256",
            "source_config_sha256",
        ):
            if not _is_sha256(getattr(self, field_name)):
                raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")

    @property
    def candidate_key(self) -> CandidateKey:
        if len(self.candidate_keys) != 1:
            raise AttributeError("joint farming result has no single candidate_key")
        return self.candidate_keys[0]

    @property
    def expected_dps(self) -> float | None:
        return self.summary.dps_mean

    def to_cache_payload(self) -> dict[str, object]:
        if not self.success:
            raise ValueError("only successful farming evaluations may be cached")
        return {
            "schema_version": GCSIM_FARMING_EVALUATION_CACHE_SCHEMA,
            "request_identity_sha256": self.request_identity_sha256,
            "candidate_keys": [list(key) for key in self.candidate_keys],
            "comparison_context_sha256": self.comparison_context_sha256,
            "expected_iterations": self.expected_iterations,
            "engine_binding_sha256": self.engine_binding_sha256,
            "artifact_sha256": self.artifact_sha256,
            "source_config_sha256": self.source_config_sha256,
            "summary": self.summary.to_dict(),
        }


class FarmingProcess(Protocol):
    returncode: int | None

    def communicate(self, timeout: float | None = None) -> tuple[str, str]: ...

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


FarmingProcessFactory = Callable[[Sequence[str], Path, Mapping[str, str]], FarmingProcess]


@dataclass(frozen=True, slots=True)
class _VerifiedArtifactIdentity:
    path: str
    execution_path: str
    sha256: str
    size: int
    mtime_ns: int


class GcsimFarmingEvaluationSession:
    """One-shot ordinary GCSIM process with thread-safe direct cancellation."""

    def __init__(
        self,
        request: GcsimFarmingEvaluationRequest,
        *,
        process_factory: FarmingProcessFactory | None = None,
        _verified_artifact: _VerifiedArtifactIdentity | None = None,
    ) -> None:
        self.request = request
        self._process_factory = process_factory or _popen_process
        self._cancel_event = Event()
        self._lock = Lock()
        self._process: FarmingProcess | None = None
        self._process_terminal_owner: str | None = None
        self._started = False
        self._verified_artifact = _verified_artifact

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self) -> None:
        self._cancel_event.set()
        should_terminate = False
        with self._lock:
            process = self._process
            if process is not None and self._process_terminal_owner is None:
                if process.poll() is None:
                    self._process_terminal_owner = _PROCESS_TERMINAL_CANCELLED
                    should_terminate = True
                else:
                    self._process_terminal_owner = _PROCESS_TERMINAL_COMPLETED
        if process is not None and should_terminate:
            try:
                process.terminate()
            except OSError:
                pass

    def run(self) -> GcsimFarmingEvaluationResult:
        with self._lock:
            if self._started:
                raise RuntimeError("GcsimFarmingEvaluationSession instances are one-shot")
            self._started = True
        started = perf_counter()
        if self.cancel_requested:
            return _result_for_request(
                self.request,
                GcsimFarmingEvaluationStatus.CANCELLED,
                started=started,
                error="Farming evaluation was cancelled before preparation.",
            )

        artifact = Path(self.request.artifact_path)
        if not artifact.is_file():
            return _result_for_request(
                self.request,
                GcsimFarmingEvaluationStatus.ARTIFACT_MISSING,
                started=started,
                error=f"Bound GCSIM artifact is missing: {artifact}",
            )
        direct_snapshot_bytes: bytes | None = None
        direct_snapshot_mode = 0
        execution_artifact = artifact
        try:
            if self._verified_artifact is not None:
                execution_artifact = Path(self._verified_artifact.execution_path)
                actual_artifact_sha = _artifact_sha_for_session(
                    artifact,
                    expected_sha256=self.request.artifact_sha256,
                    verified=self._verified_artifact,
                )
            else:
                direct_snapshot_bytes = artifact.read_bytes()
                direct_snapshot_mode = artifact.stat().st_mode
                actual_artifact_sha = hashlib.sha256(
                    direct_snapshot_bytes
                ).hexdigest()
        except OSError as exc:
            return _result_for_request(
                self.request,
                GcsimFarmingEvaluationStatus.ARTIFACT_MISSING,
                started=started,
                error=f"Could not hash bound GCSIM artifact: {exc}",
            )
        if actual_artifact_sha != self.request.artifact_sha256:
            return _result_for_request(
                self.request,
                GcsimFarmingEvaluationStatus.ARTIFACT_IDENTITY_MISMATCH,
                started=started,
                artifact_sha256=actual_artifact_sha,
                error=(
                    "GCSIM artifact SHA-256 changed after the farming request "
                    f"was bound (expected {self.request.artifact_sha256}, "
                    f"observed {actual_artifact_sha})."
                ),
            )

        run_dir_result = _create_run_dir(self.request)
        if isinstance(run_dir_result, tuple):
            status, error = run_dir_result
            return _result_for_request(
                self.request,
                status,
                started=started,
                artifact_sha256=actual_artifact_sha,
                error=error,
            )
        run_dir = run_dir_result
        config_path = run_dir / "config.txt"
        result_path = run_dir / "result.json"
        try:
            config_path.write_text(self.request.config_text, encoding="utf-8")
            if direct_snapshot_bytes is not None:
                suffix = artifact.suffix if artifact.suffix else ""
                execution_artifact = run_dir / f"gcsim-farming-engine{suffix}"
                execution_artifact.write_bytes(direct_snapshot_bytes)
                os.chmod(execution_artifact, direct_snapshot_mode | 0o100)
        except OSError as exc:
            return _result_for_request(
                self.request,
                GcsimFarmingEvaluationStatus.RUN_DIR_FAILED,
                started=started,
                artifact_sha256=actual_artifact_sha,
                run_dir=run_dir,
                config_path=config_path,
                result_path=result_path,
                error=f"Could not write isolated farming config: {exc}",
            )

        command = (
            str(execution_artifact),
            "-c",
            config_path.name,
            "-out",
            result_path.name,
        )
        env = dict(self.request.environment)
        if self.cancel_requested:
            return _result_for_request(
                self.request,
                GcsimFarmingEvaluationStatus.CANCELLED,
                started=started,
                artifact_sha256=actual_artifact_sha,
                run_dir=run_dir,
                config_path=config_path,
                result_path=result_path,
                command=command,
                error="Farming evaluation was cancelled before process start.",
            )
        try:
            process = self._process_factory(command, run_dir, env)
        except OSError as exc:
            return _result_for_request(
                self.request,
                GcsimFarmingEvaluationStatus.START_FAILED,
                started=started,
                artifact_sha256=actual_artifact_sha,
                run_dir=run_dir,
                config_path=config_path,
                result_path=result_path,
                command=command,
                error=f"Could not start ordinary GCSIM evaluation: {exc}",
            )
        should_terminate = False
        with self._lock:
            self._process = process
            if self.cancel_requested and self._process_terminal_owner is None:
                if process.poll() is None:
                    self._process_terminal_owner = _PROCESS_TERMINAL_CANCELLED
                    should_terminate = True
                else:
                    self._process_terminal_owner = _PROCESS_TERMINAL_COMPLETED
        if should_terminate:
            try:
                process.terminate()
            except OSError:
                pass

        deadline = monotonic() + self.request.timeout_seconds
        stdout = ""
        stderr = ""
        try:
            while True:
                with self._lock:
                    terminal_owner = self._process_terminal_owner
                if terminal_owner is _PROCESS_TERMINAL_CANCELLED:
                    stdout, stderr = _stop_and_collect(process)
                    break
                if terminal_owner is _PROCESS_TERMINAL_COMPLETED:
                    stdout, stderr = process.communicate(timeout=0)
                    break
                remaining = deadline - monotonic()
                if remaining <= 0:
                    should_stop = False
                    with self._lock:
                        if self._process_terminal_owner is None:
                            if process.poll() is None:
                                self._process_terminal_owner = (
                                    _PROCESS_TERMINAL_TIMEOUT
                                )
                                should_stop = True
                            else:
                                self._process_terminal_owner = (
                                    _PROCESS_TERMINAL_COMPLETED
                                )
                        terminal_owner = self._process_terminal_owner
                    if should_stop:
                        stdout, stderr = _stop_and_collect(process)
                    else:
                        stdout, stderr = process.communicate(timeout=0)
                    break
                try:
                    stdout, stderr = process.communicate(
                        timeout=min(PROCESS_POLL_INTERVAL_SECONDS, remaining)
                    )
                    with self._lock:
                        if self._process_terminal_owner is None:
                            self._process_terminal_owner = (
                                _PROCESS_TERMINAL_COMPLETED
                            )
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            with self._lock:
                if self._process is process:
                    self._process = None
                terminal_owner = self._process_terminal_owner

        if terminal_owner is _PROCESS_TERMINAL_CANCELLED:
            return _result_for_request(
                self.request,
                GcsimFarmingEvaluationStatus.CANCELLED,
                started=started,
                artifact_sha256=actual_artifact_sha,
                run_dir=run_dir,
                config_path=config_path,
                result_path=result_path,
                command=command,
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
                error="Ordinary GCSIM evaluation was cancelled while running.",
            )
        if terminal_owner is _PROCESS_TERMINAL_TIMEOUT:
            return _result_for_request(
                self.request,
                GcsimFarmingEvaluationStatus.TIMEOUT,
                started=started,
                artifact_sha256=actual_artifact_sha,
                run_dir=run_dir,
                config_path=config_path,
                result_path=result_path,
                command=command,
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
                error=(
                    "Ordinary GCSIM evaluation timed out after "
                    f"{self.request.timeout_seconds:g} seconds."
                ),
            )
        if terminal_owner is not _PROCESS_TERMINAL_COMPLETED:
            return _result_for_request(
                self.request,
                GcsimFarmingEvaluationStatus.INTERNAL_ERROR,
                started=started,
                artifact_sha256=actual_artifact_sha,
                run_dir=run_dir,
                config_path=config_path,
                result_path=result_path,
                command=command,
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
                error="Ordinary GCSIM process ended without a terminal owner.",
            )
        if process.returncode != 0:
            return _result_for_request(
                self.request,
                GcsimFarmingEvaluationStatus.PROCESS_FAILED,
                started=started,
                artifact_sha256=actual_artifact_sha,
                run_dir=run_dir,
                config_path=config_path,
                result_path=result_path,
                command=command,
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
                error=f"Ordinary GCSIM evaluation exited with {process.returncode}.",
            )
        if not result_path.is_file():
            return _result_for_request(
                self.request,
                GcsimFarmingEvaluationStatus.RESULT_MISSING,
                started=started,
                artifact_sha256=actual_artifact_sha,
                run_dir=run_dir,
                config_path=config_path,
                result_path=result_path,
                command=command,
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
                error="Ordinary GCSIM evaluation did not create result.json.",
            )
        try:
            summary = parse_gcsim_result_file(result_path)
        except GcsimResultParseError as exc:
            return _result_for_request(
                self.request,
                GcsimFarmingEvaluationStatus.RESULT_INVALID,
                started=started,
                artifact_sha256=actual_artifact_sha,
                run_dir=run_dir,
                config_path=config_path,
                result_path=result_path,
                command=command,
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
                error=str(exc),
            )
        summary_error = _summary_error(
            summary,
            expected_iterations=self.request.expected_iterations,
        )
        if summary_error:
            return _result_for_request(
                self.request,
                GcsimFarmingEvaluationStatus.RESULT_INVALID,
                started=started,
                artifact_sha256=actual_artifact_sha,
                run_dir=run_dir,
                config_path=config_path,
                result_path=result_path,
                command=command,
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
                summary=summary,
                error=summary_error,
            )
        assert summary.dps_mean is not None
        evaluation = (
            None
            if self.request.candidate is None
            else CandidateEvaluation(
                candidate=self.request.candidate,
                expected_dps=summary.dps_mean,
                investment_signature=self.request.investment_signature,
                standard_error=summary.dps_se,
                novelty_score=self.request.novelty_score,
                novelty_tags=self.request.novelty_tags,
            )
        )
        return _result_for_request(
            self.request,
            GcsimFarmingEvaluationStatus.PASSED,
            started=started,
            artifact_sha256=actual_artifact_sha,
            run_dir=run_dir,
            config_path=config_path,
            result_path=result_path,
            command=command,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
            summary=summary,
            evaluation=evaluation,
        )


class FarmingEvaluationSession(Protocol):
    def run(self) -> GcsimFarmingEvaluationResult: ...

    def cancel(self) -> None: ...


FarmingSessionFactory = Callable[[GcsimFarmingEvaluationRequest], FarmingEvaluationSession]


@dataclass(frozen=True, slots=True)
class GcsimFarmingSchedulerBudget:
    max_parallel_candidates: int
    total_cpu_budget: int
    overall_deadline_seconds: float

    def __post_init__(self) -> None:
        for field_name in ("max_parallel_candidates", "total_cpu_budget"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if (
            not math.isfinite(self.overall_deadline_seconds)
            or self.overall_deadline_seconds <= 0
        ):
            raise ValueError("overall_deadline_seconds must be finite and positive")
        logical_cpus = os.cpu_count() or 1
        if self.total_cpu_budget > logical_cpus:
            raise ValueError(
                "total_cpu_budget cannot exceed detected logical CPUs "
                f"({logical_cpus})"
            )


@dataclass(frozen=True, slots=True)
class GcsimFarmingBatchResult:
    status: GcsimFarmingBatchStatus
    comparison_context_sha256: str
    results: tuple[GcsimFarmingEvaluationResult, ...]
    best_result: GcsimFarmingEvaluationResult | None
    best_evaluation: CandidateEvaluation | None
    requested_count: int
    successful_count: int
    cache_hit_count: int
    failed_count: int
    skipped_count: int
    max_parallel_candidates: int
    total_cpu_budget: int
    deadline_seconds: float
    elapsed_seconds: float
    cache_errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "results", tuple(self.results))
        object.__setattr__(self, "cache_errors", tuple(self.cache_errors))
        if not isinstance(self.status, GcsimFarmingBatchStatus):
            raise ValueError("status must be a GcsimFarmingBatchStatus")
        if any(
            not isinstance(result, GcsimFarmingEvaluationResult)
            for result in self.results
        ):
            raise ValueError("results must contain GcsimFarmingEvaluationResult values")
        if self.results:
            if not _is_sha256(self.comparison_context_sha256):
                raise ValueError(
                    "comparison_context_sha256 must be a lowercase SHA-256 digest"
                )
            if any(
                result.comparison_context_sha256
                != self.comparison_context_sha256
                for result in self.results
            ):
                raise ValueError("batch results mix comparison contexts")
        elif self.comparison_context_sha256 and not _is_sha256(
            self.comparison_context_sha256
        ):
            raise ValueError("comparison_context_sha256 is invalid")
        for field_name in (
            "requested_count",
            "successful_count",
            "cache_hit_count",
            "failed_count",
            "skipped_count",
            "max_parallel_candidates",
            "total_cpu_budget",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.max_parallel_candidates <= 0 or self.total_cpu_budget <= 0:
            raise ValueError("batch concurrency budgets must be positive")
        if self.requested_count != len(self.results):
            raise ValueError("requested_count must equal the result count")
        skipped_statuses = {
            GcsimFarmingEvaluationStatus.SKIPPED_CANCELLED,
            GcsimFarmingEvaluationStatus.SKIPPED_DEADLINE,
        }
        successful_count = sum(result.success for result in self.results)
        cache_hit_count = sum(result.cache_hit for result in self.results)
        skipped_count = sum(
            result.status in skipped_statuses for result in self.results
        )
        failed_count = sum(
            not result.success and result.status not in skipped_statuses
            for result in self.results
        )
        if (
            self.successful_count != successful_count
            or self.cache_hit_count != cache_hit_count
            or self.skipped_count != skipped_count
            or self.failed_count != failed_count
        ):
            raise ValueError("batch counters do not match typed results")
        ranked = tuple(
            sorted(
                (result for result in self.results if result.success),
                key=lambda result: (
                    -float(result.summary.dps_mean),
                    result.candidate_keys,
                ),
            )
        )
        expected_best = ranked[0] if ranked else None
        if self.best_result != expected_best:
            raise ValueError("best_result does not match successful result ranking")
        if self.best_evaluation != (
            None if expected_best is None else expected_best.evaluation
        ):
            raise ValueError("best_evaluation does not match best_result")
        if self.status is GcsimFarmingBatchStatus.COMPLETED and (
            failed_count or skipped_count or successful_count != self.requested_count
        ):
            raise ValueError("completed batch must contain only successful results")
        if self.status is GcsimFarmingBatchStatus.COMPLETED_WITH_ERRORS and (
            failed_count <= 0 or skipped_count > 0
        ):
            raise ValueError(
                "completed_with_errors requires failures and no skipped results"
            )
        for field_name in ("deadline_seconds", "elapsed_seconds"):
            value = getattr(self, field_name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{field_name} must be finite and non-negative")
        if self.deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive")
        if any(not isinstance(error, str) for error in self.cache_errors):
            raise ValueError("cache_errors must contain strings")

    @property
    def best_found(self) -> bool:
        return self.best_result is not None

    @property
    def ranked_results(self) -> tuple[GcsimFarmingEvaluationResult, ...]:
        return tuple(
            sorted(
                (item for item in self.results if item.success),
                key=lambda item: (
                    -float(item.summary.dps_mean),
                    item.candidate_keys,
                ),
            )
        )

    @property
    def ranked_evaluations(self) -> tuple[CandidateEvaluation, ...]:
        return tuple(
            result.evaluation
            for result in sorted(
                (item for item in self.results if item.evaluation is not None),
                key=lambda item: (
                    -item.evaluation.expected_dps,  # type: ignore[union-attr]
                    item.candidate_keys,
                ),
            )
            if result.evaluation is not None
        )


class GcsimFarmingEvaluationScheduler:
    """Synchronous coordinator intended to run outside the UI thread."""

    def __init__(
        self,
        requests: Iterable[GcsimFarmingEvaluationRequest],
        budget: GcsimFarmingSchedulerBudget,
        *,
        cache_store: GcsimOptimizerCacheStore | None = None,
        enable_cache: bool = True,
        session_factory: FarmingSessionFactory | None = None,
    ) -> None:
        self.requests = tuple(requests)
        self.budget = budget
        identities = tuple(request.identity.identity_sha256 for request in self.requests)
        if len(set(identities)) != len(identities):
            raise ValueError("farming evaluation request identities must be unique")
        candidate_scopes = tuple(request.candidate_keys for request in self.requests)
        if len(set(candidate_scopes)) != len(candidate_scopes):
            raise ValueError("farming evaluation candidate scopes must be unique")
        comparison_scopes = {
            (
                request.comparison_context_sha256,
                request.investment_signature,
                request.engine_binding_sha256,
                request.artifact_sha256,
                request.catalog_fingerprint,
                request.expected_iterations,
                _sha256_comparison_environment(request.environment),
                request.comparison_shell_sha256,
            )
            for request in self.requests
        }
        if len(comparison_scopes) > 1:
            raise ValueError(
                "farming evaluation requests must share one comparison context, "
                "investment, engine, config shell, worker, and environment identity"
            )
        too_large = tuple(
            request.candidate_keys
            for request in self.requests
            if request.worker_count > budget.total_cpu_budget
        )
        if too_large:
            raise ValueError(
                "candidate worker_count exceeds total_cpu_budget: "
                f"{too_large!r}"
            )
        self._cache_store = (
            (cache_store or GcsimOptimizerCacheStore()) if enable_cache else None
        )
        self._session_factory = session_factory
        self._cancel_event = Event()
        self._lock = Lock()
        self._active_sessions: dict[int, FarmingEvaluationSession] = {}
        self._started = False

    def cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            sessions = tuple(self._active_sessions.values())
        for session in sessions:
            try:
                session.cancel()
            except Exception:
                # The worker wrapper will still return a typed internal error.
                pass

    def run(self) -> GcsimFarmingBatchResult:
        with self._lock:
            if self._started:
                raise RuntimeError("GcsimFarmingEvaluationScheduler instances are one-shot")
            self._started = True
        started = perf_counter()
        deadline = monotonic() + self.budget.overall_deadline_seconds
        pending = list(range(len(self.requests)))
        results_by_index: dict[int, GcsimFarmingEvaluationResult] = {}
        active_threads: dict[int, Thread] = {}
        active_workers: dict[int, int] = {}
        completed_queue: Queue[tuple[int, GcsimFarmingEvaluationResult]] = Queue()
        cache_errors: list[str] = []
        deadline_reached = False
        verified_artifacts: dict[
            tuple[str, str], _VerifiedArtifactIdentity
        ] = {}
        artifact_snapshot_directories: list[TemporaryDirectory[str]] = []

        # The normal production path hashes each distinct executable once per
        # batch, then every session checks a cheap immutable file-stat witness.
        # Direct/custom sessions retain their own fail-closed identity policy.
        if self._session_factory is None:
            grouped: dict[str, list[int]] = {}
            for index in pending:
                path = str(Path(self.requests[index].artifact_path).resolve())
                grouped.setdefault(path, []).append(index)
            for path_text, indices in grouped.items():
                if self._cancel_event.is_set() or monotonic() >= deadline:
                    deadline_reached = not self._cancel_event.is_set()
                    break
                artifact = Path(path_text)
                if not artifact.is_file():
                    for index in indices:
                        results_by_index[index] = _result_for_request(
                            self.requests[index],
                            GcsimFarmingEvaluationStatus.ARTIFACT_MISSING,
                            error=f"Bound GCSIM artifact is missing: {artifact}",
                        )
                        pending.remove(index)
                    continue
                snapshot_directory = TemporaryDirectory(
                    prefix="gcsim-farming-engine-"
                )
                snapshot_path = (
                    Path(snapshot_directory.name)
                    / f"gcsim-farming-engine{artifact.suffix}"
                )
                try:
                    digest, interrupted = _snapshot_artifact_until(
                        artifact,
                        snapshot_path,
                        cancel_event=self._cancel_event,
                        deadline=deadline,
                    )
                    stat = snapshot_path.stat()
                except OSError as exc:
                    snapshot_directory.cleanup()
                    for index in indices:
                        results_by_index[index] = _result_for_request(
                            self.requests[index],
                            GcsimFarmingEvaluationStatus.ARTIFACT_MISSING,
                            error=f"Could not hash bound GCSIM artifact: {exc}",
                        )
                        pending.remove(index)
                    continue
                if interrupted:
                    snapshot_directory.cleanup()
                    deadline_reached = interrupted == "deadline"
                    break
                keep_snapshot = False
                for index in indices:
                    request = self.requests[index]
                    if digest != request.artifact_sha256:
                        results_by_index[index] = _result_for_request(
                            request,
                            GcsimFarmingEvaluationStatus.ARTIFACT_IDENTITY_MISMATCH,
                            artifact_sha256=digest,
                            error=(
                                "GCSIM artifact SHA-256 changed after the farming "
                                "request was bound "
                                f"(expected {request.artifact_sha256}, observed {digest})."
                            ),
                        )
                        pending.remove(index)
                    else:
                        keep_snapshot = True
                        verified_artifacts[(path_text, request.artifact_sha256)] = (
                            _VerifiedArtifactIdentity(
                                path=path_text,
                                execution_path=str(snapshot_path.resolve()),
                                sha256=digest,
                                size=stat.st_size,
                                mtime_ns=stat.st_mtime_ns,
                            )
                        )
                if keep_snapshot:
                    artifact_snapshot_directories.append(snapshot_directory)
                else:
                    snapshot_directory.cleanup()

        # Cache lookup happens before process scheduling but remains subject to
        # the same cancellation/deadline boundary.
        if self._cache_store is not None:
            for index in tuple(pending):
                if self._cancel_event.is_set() or monotonic() >= deadline:
                    deadline_reached = not self._cancel_event.is_set()
                    break
                cached = _read_cached_result(self._cache_store, self.requests[index])
                if cached is not None:
                    results_by_index[index] = cached
                    pending.remove(index)

        def worker(
            index: int,
            session: FarmingEvaluationSession,
        ) -> None:
            try:
                result = session.run()
                if not _result_matches_request(result, self.requests[index]):
                    result = _result_for_request(
                        self.requests[index],
                        GcsimFarmingEvaluationStatus.INTERNAL_ERROR,
                        error=(
                            "Farming evaluation session returned result provenance "
                            "for a different request."
                        ),
                    )
            except Exception as exc:
                result = _result_for_request(
                    self.requests[index],
                    GcsimFarmingEvaluationStatus.INTERNAL_ERROR,
                    error=f"Farming evaluation session raised: {exc}",
                )
            completed_queue.put((index, result))

        def launch_available() -> None:
            nonlocal pending, deadline_reached
            while (
                pending
                and len(active_threads) < self.budget.max_parallel_candidates
                and not self._cancel_event.is_set()
                and monotonic() < deadline
            ):
                used_cpu = sum(active_workers.values())
                available_cpu = self.budget.total_cpu_budget - used_cpu
                fitting_position = next(
                    (
                        position
                        for position, index in enumerate(pending)
                        if self.requests[index].worker_count <= available_cpu
                    ),
                    None,
                )
                if fitting_position is None:
                    break
                index = pending.pop(fitting_position)
                try:
                    if self._session_factory is None:
                        request = self.requests[index]
                        artifact_key = (
                            str(Path(request.artifact_path).resolve()),
                            request.artifact_sha256,
                        )
                        verified = verified_artifacts.get(artifact_key)
                        if verified is None:
                            raise RuntimeError(
                                "scheduler has no verified artifact witness"
                            )
                        session = GcsimFarmingEvaluationSession(
                            request,
                            _verified_artifact=verified,
                        )
                    else:
                        session = self._session_factory(self.requests[index])
                except Exception as exc:
                    results_by_index[index] = _result_for_request(
                        self.requests[index],
                        GcsimFarmingEvaluationStatus.INTERNAL_ERROR,
                        error=f"Could not create farming evaluation session: {exc}",
                    )
                    continue
                if self._cancel_event.is_set() or monotonic() >= deadline:
                    if not self._cancel_event.is_set():
                        deadline_reached = True
                    try:
                        session.cancel()
                    except Exception:
                        pass
                    skipped_status = (
                        GcsimFarmingEvaluationStatus.SKIPPED_CANCELLED
                        if self._cancel_event.is_set()
                        else GcsimFarmingEvaluationStatus.SKIPPED_DEADLINE
                    )
                    results_by_index[index] = _result_for_request(
                        self.requests[index],
                        skipped_status,
                        error=(
                            "Candidate was not started before cancellation."
                            if skipped_status
                            is GcsimFarmingEvaluationStatus.SKIPPED_CANCELLED
                            else "Candidate was not started before the overall deadline."
                        ),
                    )
                    continue
                thread = Thread(
                    target=worker,
                    args=(index, session),
                    name=f"gcsim-farming-{index}",
                    daemon=True,
                )
                with self._lock:
                    self._active_sessions[index] = session
                # Close the small race between the pre-launch check and
                # publishing the session to an external cancel() caller.
                if self._cancel_event.is_set() or monotonic() >= deadline:
                    if not self._cancel_event.is_set():
                        deadline_reached = True
                    try:
                        session.cancel()
                    except Exception:
                        pass
                active_threads[index] = thread
                active_workers[index] = self.requests[index].worker_count
                thread.start()

        launch_available()
        stop_signalled = False
        while active_threads or pending:
            if self._cancel_event.is_set() or monotonic() >= deadline:
                if not self._cancel_event.is_set():
                    deadline_reached = True
                if not stop_signalled:
                    stop_signalled = True
                    self.cancel()
                skip_status = (
                    GcsimFarmingEvaluationStatus.SKIPPED_CANCELLED
                    if self._cancel_event.is_set() and not deadline_reached
                    else GcsimFarmingEvaluationStatus.SKIPPED_DEADLINE
                )
                for index in pending:
                    results_by_index[index] = _result_for_request(
                        self.requests[index],
                        skip_status,
                        error=(
                            "Candidate was not started before cancellation."
                            if skip_status is GcsimFarmingEvaluationStatus.SKIPPED_CANCELLED
                            else "Candidate was not started before the overall deadline."
                        ),
                    )
                pending.clear()

            if not active_threads:
                launch_available()
                if not active_threads:
                    break
            remaining = max(0.0, deadline - monotonic())
            wait_seconds = min(PROCESS_POLL_INTERVAL_SECONDS, remaining)
            if stop_signalled or wait_seconds <= 0:
                wait_seconds = PROCESS_POLL_INTERVAL_SECONDS
            try:
                index, result = completed_queue.get(timeout=wait_seconds)
            except Empty:
                launch_available()
                continue
            thread = active_threads.pop(index)
            active_workers.pop(index)
            with self._lock:
                self._active_sessions.pop(index, None)
            thread.join(timeout=0)
            results_by_index[index] = result
            if result.success and not result.cache_hit and self._cache_store is not None:
                cache_error, cache_deadline = _put_cache_until_deadline(
                    self._cache_store,
                    self.requests[index],
                    result,
                    deadline=deadline,
                )
                if cache_error:
                    cache_errors.append(
                        f"{self.requests[index].identity.identity_sha256}: "
                        f"{cache_error}"
                    )
                if cache_deadline:
                    deadline_reached = True
                    stop_signalled = True
                    self.cancel()
            launch_available()

        # Drain results that completed in the cancellation race before the last
        # active map update.  Normally the loop already consumed every row.
        while active_threads:
            index, result = completed_queue.get()
            thread = active_threads.pop(index)
            active_workers.pop(index, None)
            with self._lock:
                self._active_sessions.pop(index, None)
            thread.join(timeout=0)
            results_by_index[index] = result

        if monotonic() >= deadline and not self._cancel_event.is_set():
            deadline_reached = True
        ordered_results = tuple(
            results_by_index[index]
            for index in range(len(self.requests))
        )
        successful = tuple(result for result in ordered_results if result.success)
        best_result = next(
            iter(
                sorted(
                    successful,
                    key=lambda item: (
                        -float(item.summary.dps_mean),
                        item.candidate_keys,
                    ),
                )
            ),
            None,
        )
        best_evaluation = None if best_result is None else best_result.evaluation
        skipped_statuses = {
            GcsimFarmingEvaluationStatus.SKIPPED_CANCELLED,
            GcsimFarmingEvaluationStatus.SKIPPED_DEADLINE,
        }
        failed_count = sum(
            not result.success and result.status not in skipped_statuses
            for result in ordered_results
        )
        if self._cancel_event.is_set() and not deadline_reached:
            batch_status = GcsimFarmingBatchStatus.CANCELLED
        elif deadline_reached:
            batch_status = GcsimFarmingBatchStatus.DEADLINE_REACHED
        elif failed_count:
            batch_status = GcsimFarmingBatchStatus.COMPLETED_WITH_ERRORS
        else:
            batch_status = GcsimFarmingBatchStatus.COMPLETED
        batch_result = GcsimFarmingBatchResult(
            status=batch_status,
            comparison_context_sha256=(
                self.requests[0].comparison_context_sha256
                if self.requests
                else ""
            ),
            results=ordered_results,
            best_result=best_result,
            best_evaluation=best_evaluation,
            requested_count=len(self.requests),
            successful_count=len(successful),
            cache_hit_count=sum(result.cache_hit for result in ordered_results),
            failed_count=failed_count,
            skipped_count=sum(result.status in skipped_statuses for result in ordered_results),
            max_parallel_candidates=self.budget.max_parallel_candidates,
            total_cpu_budget=self.budget.total_cpu_budget,
            deadline_seconds=self.budget.overall_deadline_seconds,
            elapsed_seconds=round(perf_counter() - started, 6),
            cache_errors=tuple(cache_errors),
        )
        for snapshot_directory in artifact_snapshot_directories:
            snapshot_directory.cleanup()
        return batch_result


def run_gcsim_farming_evaluations(
    requests: Iterable[GcsimFarmingEvaluationRequest],
    budget: GcsimFarmingSchedulerBudget,
    *,
    cache_store: GcsimOptimizerCacheStore | None = None,
    enable_cache: bool = True,
    session_factory: FarmingSessionFactory | None = None,
) -> GcsimFarmingBatchResult:
    return GcsimFarmingEvaluationScheduler(
        requests,
        budget,
        cache_store=cache_store,
        enable_cache=enable_cache,
        session_factory=session_factory,
    ).run()


def _read_cached_result(
    store: GcsimOptimizerCacheStore,
    request: GcsimFarmingEvaluationRequest,
) -> GcsimFarmingEvaluationResult | None:
    payload = store.get(request.cache_identity)
    if payload is None:
        return None
    try:
        if int(payload.get("schema_version", 0)) != GCSIM_FARMING_EVALUATION_CACHE_SCHEMA:
            return None
        identity = request.identity
        if payload.get("request_identity_sha256") != identity.identity_sha256:
            return None
        if payload.get("comparison_context_sha256") != identity.comparison_context_sha256:
            return None
        if payload.get("expected_iterations") != identity.expected_iterations:
            return None
        raw_candidate_keys = payload.get("candidate_keys", ())
        if not isinstance(raw_candidate_keys, Sequence) or isinstance(
            raw_candidate_keys,
            (str, bytes),
        ):
            return None
        cached_candidate_keys = tuple(tuple(key) for key in raw_candidate_keys)
        if cached_candidate_keys != request.candidate_keys:
            return None
        if payload.get("engine_binding_sha256") != identity.engine_binding_sha256:
            return None
        if payload.get("artifact_sha256") != identity.artifact_sha256:
            return None
        if payload.get("source_config_sha256") != identity.source_config_sha256:
            return None
        summary_payload = payload.get("summary")
        if not isinstance(summary_payload, Mapping):
            return None
        dps_mean = _finite_nonnegative(summary_payload.get("dps_mean"))
        iterations = _positive_integer(summary_payload.get("iterations"))
        if dps_mean is None or iterations is None:
            return None
        if iterations != request.expected_iterations:
            return None
        dps_sd_raw = summary_payload.get("dps_sd")
        dps_sd = None if dps_sd_raw is None else _finite_nonnegative(dps_sd_raw)
        if dps_sd_raw is not None and dps_sd is None:
            return None
        dps_se = None if dps_sd is None else dps_sd / math.sqrt(iterations)
        summary = GcsimResultSummary(
            schema_version=str(summary_payload.get("schema_version", "")),
            sim_version=str(summary_payload.get("sim_version", "")),
            iterations=iterations,
            dps_mean=dps_mean,
            dps_sd=dps_sd,
            dps_se=dps_se,
            duration_mean=_optional_finite(summary_payload.get("duration_mean")),
            total_damage_mean=_optional_finite(summary_payload.get("total_damage_mean")),
            warnings=_string_tuple(summary_payload.get("warnings")),
            failed_actions=_string_tuple(summary_payload.get("failed_actions")),
            incomplete_characters=_string_tuple(
                summary_payload.get("incomplete_characters")
            ),
        )
        evaluation = (
            None
            if request.candidate is None
            else CandidateEvaluation(
                candidate=request.candidate,
                expected_dps=dps_mean,
                investment_signature=request.investment_signature,
                standard_error=dps_se,
                novelty_score=request.novelty_score,
                novelty_tags=request.novelty_tags,
            )
        )
    except (TypeError, ValueError):
        return None
    return _result_for_request(
        request,
        GcsimFarmingEvaluationStatus.CACHED,
        summary=summary,
        evaluation=evaluation,
        cache_hit=True,
    )


def _result_for_request(
    request: GcsimFarmingEvaluationRequest,
    status: GcsimFarmingEvaluationStatus,
    *,
    started: float | None = None,
    artifact_sha256: str | None = None,
    run_dir: str | Path = "",
    config_path: str | Path = "",
    result_path: str | Path = "",
    command: Sequence[str] = (),
    returncode: int | None = None,
    stdout: str = "",
    stderr: str = "",
    summary: GcsimResultSummary | None = None,
    evaluation: CandidateEvaluation | None = None,
    cache_hit: bool = False,
    error: str = "",
) -> GcsimFarmingEvaluationResult:
    identity = request.identity
    return GcsimFarmingEvaluationResult(
        status=status,
        success=status in {
            GcsimFarmingEvaluationStatus.PASSED,
            GcsimFarmingEvaluationStatus.CACHED,
        },
        request_identity_sha256=identity.identity_sha256,
        cache_key=request.cache_identity.cache_key,
        candidate_keys=request.candidate_keys,
        comparison_context_sha256=identity.comparison_context_sha256,
        expected_iterations=request.expected_iterations,
        evaluation=evaluation,
        summary=summary or GcsimResultSummary(),
        cache_hit=cache_hit,
        engine_binding_sha256=identity.engine_binding_sha256,
        artifact_sha256=artifact_sha256 or identity.artifact_sha256,
        source_config_sha256=identity.source_config_sha256,
        run_dir=str(run_dir) if str(run_dir) else "",
        config_path=str(config_path) if str(config_path) else "",
        result_path=str(result_path) if str(result_path) else "",
        command=tuple(str(part) for part in command),
        returncode=returncode,
        stdout=_trim_probe_text(stdout),
        stderr=_trim_probe_text(stderr),
        elapsed_seconds=(
            0.0 if started is None else round(perf_counter() - started, 6)
        ),
        error=_trim_probe_text(error),
    )


def _create_run_dir(
    request: GcsimFarmingEvaluationRequest,
) -> Path | tuple[GcsimFarmingEvaluationStatus, str]:
    if request.run_dir:
        path = Path(request.run_dir)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        path = DEFAULT_GCSIM_FARMING_RUNS_DIR / (
            f"run-{stamp}-{request.identity.identity_sha256[:12]}-{uuid4().hex[:8]}"
        )
    try:
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return (
            GcsimFarmingEvaluationStatus.RUN_DIR_EXISTS,
            f"Farming evaluation run directory already exists: {path}",
        )
    except OSError as exc:
        return (
            GcsimFarmingEvaluationStatus.RUN_DIR_FAILED,
            f"Could not create farming evaluation run directory {path}: {exc}",
        )
    return path


def _summary_error(
    summary: GcsimResultSummary,
    *,
    expected_iterations: int | None = None,
) -> str:
    if summary.dps_mean is None or not math.isfinite(summary.dps_mean) or summary.dps_mean < 0:
        return "Ordinary GCSIM result has no finite non-negative mean DPS."
    if summary.iterations is None or summary.iterations <= 0:
        return "Ordinary GCSIM result has no positive iteration count."
    if (
        expected_iterations is not None
        and summary.iterations != expected_iterations
    ):
        return (
            "Ordinary GCSIM result iteration count does not match the frozen "
            f"request (expected {expected_iterations}, observed "
            f"{summary.iterations})."
        )
    if summary.dps_sd is not None and (
        not math.isfinite(summary.dps_sd) or summary.dps_sd < 0
    ):
        return "Ordinary GCSIM result has an invalid DPS standard deviation."
    if summary.incomplete_characters:
        return (
            "Ordinary GCSIM result reports incomplete character implementations: "
            + ", ".join(summary.incomplete_characters)
        )
    return ""


def _popen_process(
    command: Sequence[str],
    cwd: Path,
    env: Mapping[str, str],
) -> FarmingProcess:
    creationflags = 0
    if os.name == "nt":
        creationflags = int(getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
    return subprocess.Popen(
        list(command),
        cwd=str(cwd),
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )


def _stop_and_collect(process: FarmingProcess) -> tuple[str, str]:
    if process.poll() is None:
        try:
            process.terminate()
        except OSError:
            pass
    try:
        return process.communicate(timeout=PROCESS_TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        try:
            return process.communicate(timeout=PROCESS_TERMINATE_GRACE_SECONDS)
        except (OSError, subprocess.TimeoutExpired):
            return "", ""
    except OSError:
        return "", ""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_sha_for_session(
    path: Path,
    *,
    expected_sha256: str,
    verified: _VerifiedArtifactIdentity | None,
) -> str:
    """Validate the private batch snapshot that will actually be executed."""

    resolved = str(path.resolve())
    if (
        verified is not None
        and verified.path == resolved
        and verified.sha256 == expected_sha256
    ):
        execution_path = Path(verified.execution_path)
        stat = execution_path.stat()
        if stat.st_size == verified.size and stat.st_mtime_ns == verified.mtime_ns:
            return verified.sha256
        return _sha256_file(execution_path)
    return _sha256_file(path)


def _snapshot_artifact_until(
    source: Path,
    destination: Path,
    *,
    cancel_event: Event,
    deadline: float,
) -> tuple[str, str]:
    """Copy, hash, and later execute the same private artifact bytes."""

    digest = hashlib.sha256()
    with source.open("rb") as source_handle, destination.open("xb") as target_handle:
        while True:
            if cancel_event.is_set():
                return "", "cancelled"
            if monotonic() >= deadline:
                return "", "deadline"
            chunk = source_handle.read(1024 * 1024)
            if not chunk:
                break
            target_handle.write(chunk)
            digest.update(chunk)
        target_handle.flush()
        os.fsync(target_handle.fileno())
    if cancel_event.is_set():
        return "", "cancelled"
    if monotonic() >= deadline:
        return "", "deadline"
    os.chmod(destination, source.stat().st_mode | 0o100)
    return digest.hexdigest(), ""


def _sha256_file_until(
    path: Path,
    *,
    cancel_event: Event,
    deadline: float,
) -> tuple[str, str]:
    """Hash once per batch while respecting its cancellation/deadline."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            if cancel_event.is_set():
                return "", "cancelled"
            if monotonic() >= deadline:
                return "", "deadline"
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    if cancel_event.is_set():
        return "", "cancelled"
    if monotonic() >= deadline:
        return "", "deadline"
    return digest.hexdigest(), ""


def _put_cache_until_deadline(
    cache_store: GcsimOptimizerCacheStore,
    request: GcsimFarmingEvaluationRequest,
    result: GcsimFarmingEvaluationResult,
    *,
    deadline: float,
) -> tuple[str, bool]:
    """Persist without letting a slow cache backend hold the scheduler open."""

    remaining = deadline - monotonic()
    if remaining <= 0:
        return "", True
    completed: Queue[str] = Queue(maxsize=1)

    def write() -> None:
        error = ""
        try:
            cache_store.put(
                request.cache_identity,
                result.to_cache_payload(),
            )
        except (GcsimOptimizerCacheError, ValueError) as exc:
            error = str(exc)
        except Exception as exc:  # defensive boundary for injected cache stores
            error = f"cache backend raised: {exc}"
        completed.put(error)

    thread = Thread(
        target=write,
        name=f"gcsim-farming-cache-{request.identity.identity_sha256[:12]}",
        daemon=True,
    )
    thread.start()
    thread.join(timeout=max(deadline - monotonic(), 0.0))
    if thread.is_alive():
        return "", True
    try:
        error = completed.get_nowait()
    except Empty:
        error = "cache writer completed without a result"
    return error, monotonic() >= deadline


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_environment(environment: Mapping[str, str]) -> str:
    normalized = tuple(sorted((str(key), str(value)) for key, value in environment.items()))
    return hashlib.sha256(_canonical_json(normalized).encode("utf-8")).hexdigest()


def freeze_gcsim_farming_environment(
    overrides: Mapping[str, str] | None,
    *,
    worker_count: int,
) -> dict[str, str]:
    """Freeze the exact process environment used by an evaluation request.

    The previous implementation mixed caller overrides with ``os.environ`` at
    process-start time.  That made two executions with the same request
    identity observably different if the ambient environment changed while a
    batch was queued.  We instead snapshot the ambient environment once, apply
    the caller overrides case-insensitively, and bind the canonical result to
    both the request identity and the process launch.
    """

    if overrides is not None and not isinstance(overrides, Mapping):
        raise ValueError("environment overrides must be a mapping")
    ambient = tuple(
        (str(key), str(value))
        for key, value in os.environ.items()
        if str(key).casefold() in _GCSIM_FARMING_AMBIENT_ENV_ALLOWLIST
    )
    supplied = tuple((str(key), str(value)) for key, value in (overrides or {}).items())
    _validate_environment_pairs(ambient, field_name="ambient environment")
    _validate_environment_pairs(supplied, field_name="environment overrides")

    values_by_folded_key: dict[str, tuple[str, str]] = {
        key.casefold(): (key, value)
        for key, value in ambient
        if key.casefold() != "gomaxprocs"
    }
    for key, value in supplied:
        if key.casefold() == "gomaxprocs":
            continue
        values_by_folded_key[key.casefold()] = (key, value)
    values_by_folded_key["gomaxprocs"] = ("GOMAXPROCS", str(worker_count))
    return dict(sorted(values_by_folded_key.values(), key=lambda item: item[0]))


def normalize_gcsim_farming_frozen_environment(
    environment: Mapping[str, str] | None,
    *,
    worker_count: int,
) -> dict[str, str]:
    if environment is None or not isinstance(environment, Mapping):
        raise ValueError("a frozen environment must be a mapping")
    pairs = tuple((str(key), str(value)) for key, value in environment.items())
    _validate_environment_pairs(pairs, field_name="frozen environment")
    values_by_folded_key = {key.casefold(): (key, value) for key, value in pairs}
    values_by_folded_key.pop("gomaxprocs", None)
    values_by_folded_key["gomaxprocs"] = ("GOMAXPROCS", str(worker_count))
    return dict(sorted(values_by_folded_key.values(), key=lambda item: item[0]))


def _validate_environment_pairs(
    pairs: Sequence[tuple[str, str]],
    *,
    field_name: str,
) -> None:
    folded_keys: set[str] = set()
    for key, value in pairs:
        if not key or "\x00" in key or "\x00" in value or "=" in key:
            raise ValueError(
                f"{field_name} keys must be non-empty, NUL-free, and contain no '='; "
                "values must be NUL-free"
            )
        folded = key.casefold()
        if folded in folded_keys:
            raise ValueError(f"{field_name} keys must be case-insensitively unique")
        folded_keys.add(folded)


def _comparison_shell_sha256(config_text: str) -> str:
    """Hash the invariant rotation/target shell of one screened candidate."""

    validate_gcsim_farming_static_config(config_text)
    comment_free = build_gcsim_comment_free_view(config_text)
    rows: list[str] = []
    for raw_line in comment_free.splitlines():
        row = raw_line.strip()
        if not row or _COMPARISON_VARIABLE_ROW_RE.fullmatch(row):
            continue
        if row.casefold().startswith("options"):
            row = _CONFIG_WORKERS_TOKEN_RE.sub("workers=<cpu-budget>", row)
        rows.append(row)
    return hashlib.sha256(_canonical_json(tuple(rows)).encode("utf-8")).hexdigest()


def _sha256_comparison_environment(environment: Mapping[str, str]) -> str:
    """Freeze caller-controlled environment while allowing worker allocation."""

    normalized = tuple(
        sorted(
            (str(key), str(value))
            for key, value in environment.items()
            if str(key).casefold() != "gomaxprocs"
        )
    )
    return hashlib.sha256(_canonical_json(normalized).encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdef" for character in value)


def _finite_nonnegative(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _optional_finite(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive_integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0 or not number.is_integer():
        return None
    return int(number)


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("cached summary list must be a sequence")
    if any(not isinstance(item, str) for item in value):
        raise ValueError("cached summary list must contain only strings")
    return tuple(value)


def _validate_request_worker_binding(
    config_text: str,
    environment: Mapping[str, str],
    worker_count: int,
    expected_iterations: int,
) -> None:
    options_matches = tuple(_CONFIG_OPTIONS_LINE_RE.finditer(config_text))
    if len(options_matches) != 1:
        raise ValueError(
            "config_text must contain exactly one canonical options line"
        )
    worker_matches = tuple(_CONFIG_WORKERS_TOKEN_RE.finditer(config_text))
    expected_worker_token = f"workers={worker_count}"
    if (
        len(worker_matches) != 1
        or worker_matches[0].group(0) != expected_worker_token
        or not (
            options_matches[0].start("body")
            <= worker_matches[0].start()
            < options_matches[0].end("body")
        )
    ):
        raise ValueError(
            "config_text must contain exactly one canonical "
            f"{expected_worker_token} token inside its options line"
        )
    iteration_matches = tuple(_CONFIG_ITERATION_TOKEN_RE.finditer(config_text))
    expected_iteration_token = f"iteration={expected_iterations}"
    if (
        len(iteration_matches) != 1
        or iteration_matches[0].group(0) != expected_iteration_token
        or not (
            options_matches[0].start("body")
            <= iteration_matches[0].start()
            < options_matches[0].end("body")
        )
    ):
        raise ValueError(
            "config_text must contain exactly one canonical "
            f"{expected_iteration_token} token inside its options line"
        )
    gomaxprocs_items = tuple(
        (key, value)
        for key, value in environment.items()
        if str(key).casefold() == "gomaxprocs"
    )
    if gomaxprocs_items != (("GOMAXPROCS", str(worker_count)),):
        raise ValueError(
            "environment must contain exactly one canonical GOMAXPROCS value "
            "equal to worker_count"
        )


def _canonical_config_iterations(config_text: str) -> int:
    options_matches = tuple(_CONFIG_OPTIONS_LINE_RE.finditer(config_text))
    iteration_matches = tuple(_CONFIG_ITERATION_TOKEN_RE.finditer(config_text))
    if len(options_matches) != 1 or len(iteration_matches) != 1:
        raise ValueError(
            "config_text must contain exactly one canonical iteration token"
        )
    match = iteration_matches[0]
    if not (
        options_matches[0].start("body")
        <= match.start()
        < options_matches[0].end("body")
    ):
        raise ValueError("iteration token must be inside the canonical options line")
    token = match.group(0)
    canonical = re.fullmatch(r"iteration=([1-9][0-9]*)", token)
    if canonical is None:
        raise ValueError("iteration token must use canonical iteration=N syntax")
    return int(canonical.group(1))


def _validate_candidate_keys(candidate_keys: EvaluationCandidateKeys) -> None:
    if not candidate_keys or len(candidate_keys) > 4:
        raise ValueError("candidate_keys must contain one to four wearer rows")
    if len(set(candidate_keys)) != len(candidate_keys):
        raise ValueError("candidate_keys must be unique")
    wearer_ids: list[str] = []
    for key in candidate_keys:
        if len(key) != 5 or any(
            not isinstance(item, str) or item != item.strip()
            for item in key
        ):
            raise ValueError("each candidate key must contain five trimmed strings")
        if any(not key[index] for index in (0, 1, 2, 4)):
            raise ValueError(
                "candidate wearer/set/layout/profile keys must be non-empty"
            )
        if key[3] and key[3] not in ARTIFACT_MAIN_STAT_SLOTS:
            raise ValueError(f"invalid candidate offpiece slot: {key[3]!r}")
        wearer_ids.append(key[0])
    if len(set(wearer_ids)) != len(wearer_ids):
        raise ValueError("joint candidate wearer ids must be unique")


def _validate_bound_candidate_keys(
    engine_context: GcsimOptimizerEngineContext,
    candidate_keys: EvaluationCandidateKeys,
) -> None:
    try:
        _validate_candidate_keys(candidate_keys)
    except ValueError as exc:
        raise GcsimFarmingEvaluationError(str(exc)) from exc
    for wearer_id, set_key, _layout_id, offpiece_slot, _profile_id in candidate_keys:
        capability = engine_context.catalog.get(set_key)
        if capability is None:
            raise GcsimFarmingEvaluationError(
                f"Candidate set is absent from the bound catalog: {set_key!r}."
            )
        if capability.key != set_key:
            raise GcsimFarmingEvaluationError(
                "Candidate set key must use the catalog's canonical spelling."
            )
        if not capability.optimizer_four_piece_ready:
            raise GcsimFarmingEvaluationError(
                f"Candidate set is not optimizer-ready: {capability.key!r}."
            )
        if capability.max_rarity == 4 and not offpiece_slot:
            raise GcsimFarmingEvaluationError(
                "A four-star 4p candidate requires an explicit five-star "
                f"offpiece slot for wearer {wearer_id!r}."
            )
        if capability.max_rarity == 5 and offpiece_slot:
            raise GcsimFarmingEvaluationError(
                "A five-star 4p candidate must not carry a four-star offpiece "
                f"variant for wearer {wearer_id!r}."
            )


def _result_matches_request(
    result: GcsimFarmingEvaluationResult,
    request: GcsimFarmingEvaluationRequest,
) -> bool:
    identity = request.identity
    return (
        result.request_identity_sha256 == identity.identity_sha256
        and result.cache_key == request.cache_identity.cache_key
        and result.candidate_keys == request.candidate_keys
        and result.comparison_context_sha256
        == identity.comparison_context_sha256
        and result.expected_iterations == request.expected_iterations
        and result.engine_binding_sha256 == identity.engine_binding_sha256
        and result.source_config_sha256 == identity.source_config_sha256
        and (
            result.artifact_sha256 == identity.artifact_sha256
            or result.status
            is GcsimFarmingEvaluationStatus.ARTIFACT_IDENTITY_MISMATCH
        )
        and _result_evaluation_matches_request(result, request)
    )


def _result_evaluation_matches_request(
    result: GcsimFarmingEvaluationResult,
    request: GcsimFarmingEvaluationRequest,
) -> bool:
    if not result.success:
        return result.evaluation is None
    if request.candidate is None:
        return result.evaluation is None
    evaluation = result.evaluation
    return (
        evaluation is not None
        and evaluation.candidate == request.candidate
        and evaluation.investment_signature == request.investment_signature
        and evaluation.expected_dps == result.summary.dps_mean
        and evaluation.standard_error == result.summary.dps_se
        and evaluation.novelty_score == request.novelty_score
        and evaluation.novelty_tags == request.novelty_tags
    )


__all__ = [
    "CandidateKey",
    "DEFAULT_GCSIM_FARMING_CANDIDATE_TIMEOUT_SECONDS",
    "DEFAULT_GCSIM_FARMING_RUNS_DIR",
    "GCSIM_FARMING_EVALUATION_CACHE_MODE",
    "GCSIM_FARMING_EVALUATION_CONTRACT",
    "GcsimFarmingBatchResult",
    "GcsimFarmingBatchStatus",
    "GcsimFarmingEvaluationError",
    "GcsimFarmingEvaluationIdentity",
    "GcsimFarmingEvaluationRequest",
    "GcsimFarmingEvaluationResult",
    "GcsimFarmingEvaluationScheduler",
    "GcsimFarmingEvaluationSession",
    "GcsimFarmingEvaluationStatus",
    "GcsimFarmingSchedulerBudget",
    "freeze_gcsim_farming_environment",
    "normalize_gcsim_farming_frozen_environment",
    "prepare_bound_gcsim_farming_evaluation",
    "prepare_bound_gcsim_farming_joint_evaluation",
    "run_gcsim_farming_evaluations",
]
