"""Cancellable two-stage runner for prepared GCSIM optimizer configs.

The optimizer config renderer intentionally lives outside this module.  This
boundary accepts already-prepared config text (or a path to it), copies that
input into a session-owned directory, and runs the upstream workflow:

1. ``gcsim -substatOptim -c optimizer-input.txt -out optimized.txt``
2. ``gcsim -c optimized.txt -out result.json``

``GcsimOptimizerSession.run`` is synchronous so callers can choose their own
worker/threading model.  ``cancel`` is thread-safe and terminates the active
``Popen`` process; no Qt dependency or unsafe thread termination is involved.
Every completed session keeps its inputs, outputs, and per-stage diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
from threading import Event, Lock
from time import monotonic, perf_counter
from types import MappingProxyType
from typing import Callable, Mapping, Protocol, Sequence
from uuid import uuid4

from .artifact_runner import (
    GcsimResultParseError,
    GcsimResultSummary,
    parse_gcsim_result_payload,
)
from .engine_store import (
    DEFAULT_GCSIM_ENGINE_STORE_DIR,
    GcsimEngineStore,
    GcsimEngineStoreError,
    PROJECT_ROOT,
)
from .runtime_probe import _trim_probe_text


DEFAULT_GCSIM_OPTIMIZER_RUNS_DIR = PROJECT_ROOT / "data" / "gcsim" / "optimizer-runs"
DEFAULT_GCSIM_OPTIMIZER_TIMEOUT_SECONDS = 30 * 60
DEFAULT_GCSIM_OPTIMIZER_SIMULATION_TIMEOUT_SECONDS = 5 * 60
DEFAULT_GCSIM_OPTIMIZER_INPUT_FILENAME = "optimizer-input.txt"
DEFAULT_GCSIM_OPTIMIZED_CONFIG_FILENAME = "optimized.txt"
DEFAULT_GCSIM_OPTIMIZER_RESULT_FILENAME = "result.json"
DEFAULT_GCSIM_OPTIMIZER_EXECUTABLE_FILENAME = "gcsim-verified.exe"
PROCESS_POLL_INTERVAL_SECONDS = 0.1
PROCESS_TERMINATE_GRACE_SECONDS = 1.0
_GCSIM_OPTIMIZER_AMBIENT_ENV_ALLOWLIST = frozenset(
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
GCSIM_OPTIMIZER_OPTION_KEYS = (
    "total_liquid_substats",
    "indiv_liquid_cap",
    "fixed_substats_count",
    "fine_tune",
    "show_substat_scalars",
)
GCSIM_OPTIMIZER_BOOLEAN_OPTION_KEYS = frozenset(
    {"fine_tune", "show_substat_scalars"}
)


class GcsimOptimizerRunStatus(str, Enum):
    """Terminal status of a two-stage optimizer run."""

    PASSED = "passed"
    CANCELLED = "cancelled"
    INVALID_REQUEST = "invalid_request"
    INPUT_MISSING = "input_missing"
    INPUT_INVALID = "input_invalid"
    INPUT_READ_FAILED = "input_read_failed"
    RUN_DIR_EXISTS = "run_dir_exists"
    RUN_DIR_FAILED = "run_dir_failed"
    NO_ACTIVE_ENGINE = "no_active_engine"
    ACTIVE_ENGINE_INVALID = "active_engine_invalid"
    ARTIFACT_PATH_MISSING = "artifact_path_missing"
    ARTIFACT_MISSING = "artifact_missing"
    ARTIFACT_NOT_FILE = "artifact_not_file"
    ARTIFACT_IDENTITY_MISMATCH = "artifact_identity_mismatch"
    OPTIMIZER_START_FAILED = "optimizer_start_failed"
    OPTIMIZER_TIMEOUT = "optimizer_timeout"
    OPTIMIZER_FAILED = "optimizer_failed"
    OPTIMIZED_CONFIG_MISSING = "optimized_config_missing"
    OPTIMIZED_CONFIG_INVALID = "optimized_config_invalid"
    SIMULATION_START_FAILED = "simulation_start_failed"
    SIMULATION_TIMEOUT = "simulation_timeout"
    SIMULATION_FAILED = "simulation_failed"
    RESULT_MISSING = "result_missing"
    RESULT_INVALID = "result_invalid"
    EVIDENCE_CHANGED = "evidence_changed"


class GcsimOptimizerSessionStatus(str, Enum):
    """Observable lifecycle state for a one-shot optimizer session."""

    IDLE = "idle"
    PREPARING = "preparing"
    OPTIMIZING = "optimizing"
    SIMULATING = "simulating"
    CANCELLING = "cancelling"
    PASSED = "passed"
    CANCELLED = "cancelled"
    FAILED = "failed"


_TERMINAL_SESSION_STATUSES = frozenset(
    {
        GcsimOptimizerSessionStatus.PASSED,
        GcsimOptimizerSessionStatus.CANCELLED,
        GcsimOptimizerSessionStatus.FAILED,
    }
)


class GcsimOptimizerStageName(str, Enum):
    OPTIMIZE = "optimize"
    SIMULATE = "simulate"


class GcsimOptimizerStageStatus(str, Enum):
    PASSED = "passed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    START_FAILED = "start_failed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class GcsimOptimizerRunRequest:
    """Inputs for one isolated optimizer session.

    Exactly one of ``config_text`` and ``config_path`` must be provided.
    ``artifact_path`` is primarily useful for a pinned artifact or tests; when
    omitted, the executable is resolved from the active engine manifest.

    An explicit ``run_dir`` must not exist.  This prevents two callers from
    overwriting one another's optimizer artifacts.  With no explicit path, a
    unique child of ``data/gcsim/optimizer-runs`` is created.
    """

    config_text: str | None = None
    config_path: str | Path | None = None
    artifact_path: str | Path | None = None
    store_dir: str | Path | None = None
    run_dir: str | Path | None = None
    optimizer_timeout_seconds: float = DEFAULT_GCSIM_OPTIMIZER_TIMEOUT_SECONDS
    simulation_timeout_seconds: float = (
        DEFAULT_GCSIM_OPTIMIZER_SIMULATION_TIMEOUT_SECONDS
    )
    overall_timeout_seconds: float | None = None
    optimizer_options: Mapping[str, int | float] = field(default_factory=dict)
    verbose: bool = False
    environment: Mapping[str, str] = field(default_factory=dict, repr=False)
    environment_is_frozen: bool = field(default=False, repr=False, compare=False)
    expected_artifact_sha256: str = ""
    engine_binding_sha256: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.optimizer_options, Mapping):
            object.__setattr__(
                self,
                "optimizer_options",
                MappingProxyType(dict(self.optimizer_options)),
            )
        if isinstance(self.environment, Mapping):
            resolved_environment = (
                normalize_gcsim_optimizer_frozen_environment(self.environment)
                if self.environment_is_frozen
                else freeze_gcsim_optimizer_environment(self.environment)
            )
            object.__setattr__(
                self,
                "environment",
                MappingProxyType(resolved_environment),
            )
            object.__setattr__(self, "environment_is_frozen", True)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerStageDiagnostic:
    name: GcsimOptimizerStageName
    status: GcsimOptimizerStageStatus
    command: tuple[str, ...] = ()
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    elapsed_seconds: float = 0.0
    error: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", tuple(str(part) for part in self.command))
        if not isinstance(self.name, GcsimOptimizerStageName):
            raise ValueError("optimizer stage name must be typed")
        if not isinstance(self.status, GcsimOptimizerStageStatus):
            raise ValueError("optimizer stage status must be typed")
        if (
            isinstance(self.elapsed_seconds, bool)
            or not isinstance(self.elapsed_seconds, (int, float))
            or not math.isfinite(self.elapsed_seconds)
            or self.elapsed_seconds < 0
        ):
            raise ValueError("optimizer stage elapsed_seconds must be finite and non-negative")
        if self.returncode is not None and (
            isinstance(self.returncode, bool) or not isinstance(self.returncode, int)
        ):
            raise ValueError("optimizer stage returncode must be an integer or None")
        if self.status is GcsimOptimizerStageStatus.PASSED:
            if self.returncode != 0 or not self.command or self.error:
                raise ValueError("passed optimizer stage evidence is inconsistent")
        elif not self.error:
            raise ValueError("non-passed optimizer stage requires an error")

    def to_dict(self) -> dict:
        return {
            "name": self.name.value,
            "status": self.status.value,
            "command": list(self.command),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "elapsed_seconds": self.elapsed_seconds,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerRunResult:
    status: GcsimOptimizerRunStatus
    success: bool
    session_status: GcsimOptimizerSessionStatus
    engine_id: str = ""
    engine_path: str = ""
    artifact_path: str = ""
    artifact_source: str = ""
    artifact_sha256: str = ""
    engine_binding_sha256: str = ""
    run_dir: str = ""
    input_config_path: str = ""
    optimized_config_path: str = ""
    result_path: str = ""
    input_config_bytes: bytes = field(default=b"", repr=False)
    optimized_config_bytes: bytes = field(default=b"", repr=False)
    result_json_bytes: bytes = field(default=b"", repr=False)
    input_config_sha256: str = ""
    optimized_config_sha256: str = ""
    result_json_sha256: str = ""
    optimize: GcsimOptimizerStageDiagnostic | None = None
    simulate: GcsimOptimizerStageDiagnostic | None = None
    summary: GcsimResultSummary = field(default_factory=GcsimResultSummary)
    elapsed_seconds: float = 0.0
    error: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, GcsimOptimizerRunStatus):
            raise ValueError("optimizer result status must be typed")
        if not isinstance(self.session_status, GcsimOptimizerSessionStatus):
            raise ValueError("optimizer session status must be typed")
        if not isinstance(self.success, bool):
            raise ValueError("optimizer result success must be a bool")
        expected_session = (
            GcsimOptimizerSessionStatus.PASSED
            if self.status is GcsimOptimizerRunStatus.PASSED
            else GcsimOptimizerSessionStatus.CANCELLED
            if self.status is GcsimOptimizerRunStatus.CANCELLED
            else GcsimOptimizerSessionStatus.FAILED
        )
        if self.success is not (self.status is GcsimOptimizerRunStatus.PASSED):
            raise ValueError("optimizer result success does not match status")
        if self.session_status is not expected_session:
            raise ValueError("optimizer result session status does not match terminal status")
        if (
            isinstance(self.elapsed_seconds, bool)
            or not isinstance(self.elapsed_seconds, (int, float))
            or not math.isfinite(self.elapsed_seconds)
            or self.elapsed_seconds < 0
        ):
            raise ValueError("optimizer result elapsed_seconds must be finite and non-negative")
        for field_name in ("artifact_sha256", "engine_binding_sha256"):
            value = getattr(self, field_name)
            if value and not _is_sha256(value):
                raise ValueError(f"optimizer result {field_name} is invalid")
        snapshot_fields = (
            ("input_config_bytes", "input_config_sha256"),
            ("optimized_config_bytes", "optimized_config_sha256"),
            ("result_json_bytes", "result_json_sha256"),
        )
        for bytes_field, hash_field in snapshot_fields:
            payload = getattr(self, bytes_field)
            digest = getattr(self, hash_field)
            if not isinstance(payload, bytes):
                raise ValueError(f"optimizer result {bytes_field} must be bytes")
            if payload or digest:
                if not payload or not _is_sha256(digest):
                    raise ValueError(
                        f"optimizer result {bytes_field}/{hash_field} is incomplete"
                    )
                if hashlib.sha256(payload).hexdigest() != digest:
                    raise ValueError(
                        f"optimizer result {hash_field} differs from its byte snapshot"
                    )
        if self.optimize is not None and (
            not isinstance(self.optimize, GcsimOptimizerStageDiagnostic)
            or self.optimize.name is not GcsimOptimizerStageName.OPTIMIZE
        ):
            raise ValueError("optimizer result optimize diagnostic is invalid")
        if self.simulate is not None and (
            not isinstance(self.simulate, GcsimOptimizerStageDiagnostic)
            or self.simulate.name is not GcsimOptimizerStageName.SIMULATE
        ):
            raise ValueError("optimizer result simulate diagnostic is invalid")
        if self.simulate is not None and (
            self.optimize is None
            or self.optimize.status is not GcsimOptimizerStageStatus.PASSED
        ):
            raise ValueError("simulation evidence requires a passed optimizer stage")
        if self.status is GcsimOptimizerRunStatus.PASSED:
            if (
                self.optimize is None
                or self.optimize.status is not GcsimOptimizerStageStatus.PASSED
                or self.simulate is None
                or self.simulate.status is not GcsimOptimizerStageStatus.PASSED
                or not self.artifact_path
                or not self.artifact_sha256
                or not self.run_dir
                or not self.input_config_path
                or not self.optimized_config_path
                or not self.result_path
                or not self.input_config_bytes
                or not self.optimized_config_bytes
                or not self.result_json_bytes
                or self.error
            ):
                raise ValueError("passed optimizer result lacks complete execution evidence")
            summary_error = _optimizer_result_summary_error(self.summary)
            if summary_error:
                raise ValueError(summary_error)
        elif not self.error:
            raise ValueError("non-passed optimizer result requires an error")

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "success": self.success,
            "session_status": self.session_status.value,
            "engine_id": self.engine_id,
            "engine_path": self.engine_path,
            "artifact_path": self.artifact_path,
            "artifact_source": self.artifact_source,
            "artifact_sha256": self.artifact_sha256,
            "engine_binding_sha256": self.engine_binding_sha256,
            "run_dir": self.run_dir,
            "input_config_path": self.input_config_path,
            "optimized_config_path": self.optimized_config_path,
            "result_path": self.result_path,
            "input_config_sha256": self.input_config_sha256,
            "optimized_config_sha256": self.optimized_config_sha256,
            "result_json_sha256": self.result_json_sha256,
            "optimize": None if self.optimize is None else self.optimize.to_dict(),
            "simulate": None if self.simulate is None else self.simulate.to_dict(),
            "summary": self.summary.to_dict(),
            "elapsed_seconds": self.elapsed_seconds,
            "error": self.error,
        }


class OptimizerProcess(Protocol):
    returncode: int | None

    def communicate(self, timeout: float | None = None) -> tuple[str, str]: ...

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


OptimizerProcessFactory = Callable[
    [Sequence[str], Path, Mapping[str, str]],
    OptimizerProcess,
]
OptimizerStatusCallback = Callable[[GcsimOptimizerSessionStatus], None]


@dataclass(frozen=True, slots=True)
class _ArtifactResolution:
    status: GcsimOptimizerRunStatus | None
    artifact_path: Path | None = None
    artifact_source: str = ""
    artifact_sha256: str = ""
    engine_id: str = ""
    engine_path: str = ""
    error: str = ""


class GcsimOptimizerSession:
    """A one-shot, synchronously executed, externally cancellable session."""

    def __init__(
        self,
        request: GcsimOptimizerRunRequest,
        *,
        process_factory: OptimizerProcessFactory | None = None,
        on_status: OptimizerStatusCallback | None = None,
    ) -> None:
        self.request = request
        self._process_factory = process_factory or _popen_process
        self._on_status = on_status
        self._cancel_event = Event()
        self._lock = Lock()
        self._current_process: OptimizerProcess | None = None
        self._status = GcsimOptimizerSessionStatus.IDLE
        self._started = False

    @property
    def status(self) -> GcsimOptimizerSessionStatus:
        with self._lock:
            return self._status

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def cancel(self) -> None:
        """Request cancellation and wake a running ``communicate`` call.

        The run thread owns the terminate/kill grace-period handling.  Calling
        ``terminate`` here makes cancellation responsive even while that thread
        is waiting for process output.
        """

        self._cancel_event.set()
        self._transition(GcsimOptimizerSessionStatus.CANCELLING)
        with self._lock:
            process = self._current_process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                # The run thread will observe cancellation and attempt kill.
                pass

    def run(self) -> GcsimOptimizerRunResult:
        with self._lock:
            if self._started:
                raise RuntimeError("GcsimOptimizerSession instances are one-shot.")
            self._started = True
        started = perf_counter()
        wall_started = monotonic()
        self._transition(GcsimOptimizerSessionStatus.PREPARING)

        if self.cancel_requested:
            return self._terminal_result(
                GcsimOptimizerRunStatus.CANCELLED,
                started=started,
                error="GCSIM optimizer run was cancelled before preparation.",
            )

        validation_error = _validate_request(self.request)
        if validation_error:
            return self._terminal_result(
                GcsimOptimizerRunStatus.INVALID_REQUEST,
                started=started,
                error=validation_error,
            )
        overall_deadline = (
            None
            if self.request.overall_timeout_seconds is None
            else wall_started + float(self.request.overall_timeout_seconds)
        )

        run_dir_result = _create_isolated_run_dir(self.request.run_dir)
        if isinstance(run_dir_result, tuple):
            status, error = run_dir_result
            return self._terminal_result(status, started=started, error=error)
        run_dir = run_dir_result
        input_path = run_dir / DEFAULT_GCSIM_OPTIMIZER_INPUT_FILENAME
        optimized_path = run_dir / DEFAULT_GCSIM_OPTIMIZED_CONFIG_FILENAME
        result_path = run_dir / DEFAULT_GCSIM_OPTIMIZER_RESULT_FILENAME

        config_result = _read_request_config(self.request)
        if isinstance(config_result, tuple):
            status, error = config_result
            return self._terminal_result(
                status,
                started=started,
                run_dir=run_dir,
                input_path=input_path,
                optimized_path=optimized_path,
                result_path=result_path,
                error=error,
            )
        input_bytes = config_result.encode("utf-8")
        try:
            input_path.write_bytes(input_bytes)
        except OSError as exc:
            return self._terminal_result(
                GcsimOptimizerRunStatus.INPUT_READ_FAILED,
                started=started,
                run_dir=run_dir,
                input_path=input_path,
                optimized_path=optimized_path,
                result_path=result_path,
                error=f"Could not write isolated optimizer input: {exc}",
            )

        artifact = _resolve_artifact(self.request)
        if artifact.status is not None:
            return self._terminal_result(
                artifact.status,
                started=started,
                artifact=artifact,
                run_dir=run_dir,
                input_path=input_path,
                optimized_path=optimized_path,
                result_path=result_path,
                error=artifact.error,
            )
        assert artifact.artifact_path is not None

        snapshot = _snapshot_verified_artifact(
            artifact.artifact_path,
            run_dir=run_dir,
            expected_sha256=artifact.artifact_sha256,
        )
        if isinstance(snapshot, tuple):
            snapshot_status, snapshot_error = snapshot
            return self._terminal_result(
                snapshot_status,
                started=started,
                artifact=artifact,
                run_dir=run_dir,
                input_path=input_path,
                optimized_path=optimized_path,
                result_path=result_path,
                error=snapshot_error,
            )
        execution_artifact_path = snapshot

        env = dict(self.request.environment)
        option_text = format_gcsim_optimizer_options(self.request.optimizer_options)
        optimize_command_parts = [
            str(execution_artifact_path),
            "-substatOptim",
        ]
        if option_text:
            optimize_command_parts.extend(("-options", option_text))
        if self.request.verbose:
            optimize_command_parts.append("-v")
        optimize_command_parts.extend(
            ("-c", input_path.name, "-out", optimized_path.name)
        )
        optimize_command = tuple(optimize_command_parts)
        self._transition(GcsimOptimizerSessionStatus.OPTIMIZING)
        optimize_timeout = _effective_stage_timeout(
            float(self.request.optimizer_timeout_seconds),
            overall_deadline=overall_deadline,
        )
        if optimize_timeout <= 0:
            optimize = _stage_timeout_before_start(
                GcsimOptimizerStageName.OPTIMIZE,
                optimize_command,
                reason="GCSIM optimizer overall deadline was reached before optimization.",
            )
        else:
            optimize = self._run_stage(
                GcsimOptimizerStageName.OPTIMIZE,
                optimize_command,
                cwd=run_dir,
                env=env,
                timeout_seconds=optimize_timeout,
            )
        if optimize.status is not GcsimOptimizerStageStatus.PASSED:
            status = _stage_terminal_status(optimize, optimize_stage=True)
            return self._terminal_result(
                status,
                started=started,
                artifact=artifact,
                run_dir=run_dir,
                input_path=input_path,
                optimized_path=optimized_path,
                result_path=result_path,
                optimize=optimize,
                error=optimize.error,
            )
        if self.cancel_requested:
            return self._terminal_result(
                GcsimOptimizerRunStatus.CANCELLED,
                started=started,
                artifact=artifact,
                run_dir=run_dir,
                input_path=input_path,
                optimized_path=optimized_path,
                result_path=result_path,
                optimize=optimize,
                error="GCSIM optimizer run was cancelled after optimization.",
            )
        if not optimized_path.is_file():
            return self._terminal_result(
                GcsimOptimizerRunStatus.OPTIMIZED_CONFIG_MISSING,
                started=started,
                artifact=artifact,
                run_dir=run_dir,
                input_path=input_path,
                optimized_path=optimized_path,
                result_path=result_path,
                optimize=optimize,
                error="GCSIM optimizer did not create the expected optimized config.",
            )
        try:
            optimized_bytes = optimized_path.read_bytes()
            optimized_bytes.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return self._terminal_result(
                GcsimOptimizerRunStatus.OPTIMIZED_CONFIG_INVALID,
                started=started,
                artifact=artifact,
                run_dir=run_dir,
                input_path=input_path,
                optimized_path=optimized_path,
                result_path=result_path,
                optimize=optimize,
                error=f"Could not snapshot optimized config: {exc}",
            )
        if not optimized_bytes or b"\x00" in optimized_bytes:
            return self._terminal_result(
                GcsimOptimizerRunStatus.OPTIMIZED_CONFIG_INVALID,
                started=started,
                artifact=artifact,
                run_dir=run_dir,
                input_path=input_path,
                optimized_path=optimized_path,
                result_path=result_path,
                optimize=optimize,
                error="Optimized config is empty or contains NUL.",
            )

        simulate_command = (
            str(execution_artifact_path),
            "-c",
            optimized_path.name,
            "-out",
            result_path.name,
        )
        self._transition(GcsimOptimizerSessionStatus.SIMULATING)
        simulation_timeout = _effective_stage_timeout(
            float(self.request.simulation_timeout_seconds),
            overall_deadline=overall_deadline,
        )
        if simulation_timeout <= 0:
            simulate = _stage_timeout_before_start(
                GcsimOptimizerStageName.SIMULATE,
                simulate_command,
                reason="GCSIM optimizer overall deadline was reached before simulation.",
            )
        else:
            simulate = self._run_stage(
                GcsimOptimizerStageName.SIMULATE,
                simulate_command,
                cwd=run_dir,
                env=env,
                timeout_seconds=simulation_timeout,
            )
        if simulate.status is not GcsimOptimizerStageStatus.PASSED:
            status = _stage_terminal_status(simulate, optimize_stage=False)
            return self._terminal_result(
                status,
                started=started,
                artifact=artifact,
                run_dir=run_dir,
                input_path=input_path,
                optimized_path=optimized_path,
                result_path=result_path,
                optimize=optimize,
                simulate=simulate,
                error=simulate.error,
            )
        if self.cancel_requested:
            return self._terminal_result(
                GcsimOptimizerRunStatus.CANCELLED,
                started=started,
                artifact=artifact,
                run_dir=run_dir,
                input_path=input_path,
                optimized_path=optimized_path,
                result_path=result_path,
                optimize=optimize,
                simulate=simulate,
                error="GCSIM optimizer run was cancelled after simulation.",
            )
        if not result_path.is_file():
            return self._terminal_result(
                GcsimOptimizerRunStatus.RESULT_MISSING,
                started=started,
                artifact=artifact,
                run_dir=run_dir,
                input_path=input_path,
                optimized_path=optimized_path,
                result_path=result_path,
                optimize=optimize,
                simulate=simulate,
                error="GCSIM simulation did not create the expected result JSON.",
            )
        try:
            final_input_bytes = input_path.read_bytes()
            final_optimized_bytes = optimized_path.read_bytes()
            result_bytes = result_path.read_bytes()
        except OSError as exc:
            return self._terminal_result(
                GcsimOptimizerRunStatus.RESULT_INVALID,
                started=started,
                artifact=artifact,
                run_dir=run_dir,
                input_path=input_path,
                optimized_path=optimized_path,
                result_path=result_path,
                optimize=optimize,
                simulate=simulate,
                error=f"Could not snapshot optimizer evidence: {exc}",
            )
        if final_input_bytes != input_bytes or final_optimized_bytes != optimized_bytes:
            return self._terminal_result(
                GcsimOptimizerRunStatus.EVIDENCE_CHANGED,
                started=started,
                artifact=artifact,
                run_dir=run_dir,
                input_path=input_path,
                optimized_path=optimized_path,
                result_path=result_path,
                optimize=optimize,
                simulate=simulate,
                error="Optimizer input or optimized config changed during execution.",
            )
        try:
            result_payload = json.loads(result_bytes.decode("utf-8"))
            summary = parse_gcsim_result_payload(result_payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return self._terminal_result(
                GcsimOptimizerRunStatus.RESULT_INVALID,
                started=started,
                artifact=artifact,
                run_dir=run_dir,
                input_path=input_path,
                optimized_path=optimized_path,
                result_path=result_path,
                optimize=optimize,
                simulate=simulate,
                error=f"Could not parse GCSIM result JSON: {exc}",
            )
        except GcsimResultParseError as exc:
            return self._terminal_result(
                GcsimOptimizerRunStatus.RESULT_INVALID,
                started=started,
                artifact=artifact,
                run_dir=run_dir,
                input_path=input_path,
                optimized_path=optimized_path,
                result_path=result_path,
                optimize=optimize,
                simulate=simulate,
                error=str(exc),
            )
        summary_error = _optimizer_result_summary_error(summary)
        if summary_error:
            return self._terminal_result(
                GcsimOptimizerRunStatus.RESULT_INVALID,
                started=started,
                artifact=artifact,
                run_dir=run_dir,
                input_path=input_path,
                optimized_path=optimized_path,
                result_path=result_path,
                optimize=optimize,
                simulate=simulate,
                summary=summary,
                error=summary_error,
            )

        return self._terminal_result(
            GcsimOptimizerRunStatus.PASSED,
            started=started,
            artifact=artifact,
            run_dir=run_dir,
            input_path=input_path,
            optimized_path=optimized_path,
            result_path=result_path,
            optimize=optimize,
            simulate=simulate,
            summary=summary,
            input_config_bytes=input_bytes,
            optimized_config_bytes=optimized_bytes,
            result_json_bytes=result_bytes,
        )

    def _run_stage(
        self,
        name: GcsimOptimizerStageName,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout_seconds: float,
    ) -> GcsimOptimizerStageDiagnostic:
        started = perf_counter()
        normalized_command = tuple(str(part) for part in command)
        if self.cancel_requested:
            return _stage_diagnostic(
                name,
                GcsimOptimizerStageStatus.CANCELLED,
                normalized_command,
                started=started,
                error=f"GCSIM {name.value} stage was cancelled before start.",
            )
        try:
            process = self._process_factory(normalized_command, cwd, env)
        except OSError as exc:
            return _stage_diagnostic(
                name,
                GcsimOptimizerStageStatus.START_FAILED,
                normalized_command,
                started=started,
                error=f"Could not start GCSIM {name.value} stage: {exc}",
            )

        with self._lock:
            self._current_process = process
        if self.cancel_requested and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

        deadline = monotonic() + timeout_seconds
        try:
            while True:
                if self.cancel_requested:
                    stdout, stderr = _stop_and_collect(process)
                    return _stage_diagnostic(
                        name,
                        GcsimOptimizerStageStatus.CANCELLED,
                        normalized_command,
                        started=started,
                        returncode=process.returncode,
                        stdout=stdout,
                        stderr=stderr,
                        error=f"GCSIM {name.value} stage was cancelled.",
                    )
                remaining = deadline - monotonic()
                if remaining <= 0:
                    stdout, stderr = _stop_and_collect(process)
                    return _stage_diagnostic(
                        name,
                        GcsimOptimizerStageStatus.TIMEOUT,
                        normalized_command,
                        started=started,
                        returncode=process.returncode,
                        stdout=stdout,
                        stderr=stderr,
                        error=f"GCSIM {name.value} stage timed out after {timeout_seconds:g} seconds.",
                    )
                try:
                    stdout, stderr = process.communicate(
                        timeout=min(PROCESS_POLL_INTERVAL_SECONDS, remaining)
                    )
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            with self._lock:
                if self._current_process is process:
                    self._current_process = None

        # Cancellation can race with the final communicate call: ``cancel``
        # may terminate the process after the loop's pre-communicate check but
        # before output collection returns.  Preserve the user's intent instead
        # of misclassifying the resulting negative exit code as an engine error.
        if self.cancel_requested:
            return _stage_diagnostic(
                name,
                GcsimOptimizerStageStatus.CANCELLED,
                normalized_command,
                started=started,
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
                error=f"GCSIM {name.value} stage was cancelled.",
            )
        if process.returncode != 0:
            return _stage_diagnostic(
                name,
                GcsimOptimizerStageStatus.FAILED,
                normalized_command,
                started=started,
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
                error=f"GCSIM {name.value} stage exited with {process.returncode}.",
            )
        return _stage_diagnostic(
            name,
            GcsimOptimizerStageStatus.PASSED,
            normalized_command,
            started=started,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def _terminal_result(
        self,
        status: GcsimOptimizerRunStatus,
        *,
        started: float,
        artifact: _ArtifactResolution | None = None,
        run_dir: Path | None = None,
        input_path: Path | None = None,
        optimized_path: Path | None = None,
        result_path: Path | None = None,
        optimize: GcsimOptimizerStageDiagnostic | None = None,
        simulate: GcsimOptimizerStageDiagnostic | None = None,
        summary: GcsimResultSummary | None = None,
        input_config_bytes: bytes = b"",
        optimized_config_bytes: bytes = b"",
        result_json_bytes: bytes = b"",
        error: str = "",
    ) -> GcsimOptimizerRunResult:
        if status is GcsimOptimizerRunStatus.PASSED:
            session_status = GcsimOptimizerSessionStatus.PASSED
        elif status is GcsimOptimizerRunStatus.CANCELLED:
            session_status = GcsimOptimizerSessionStatus.CANCELLED
        else:
            session_status = GcsimOptimizerSessionStatus.FAILED
        actual_session_status = self._transition(session_status)
        if (
            actual_session_status is GcsimOptimizerSessionStatus.CANCELLED
            and status is not GcsimOptimizerRunStatus.CANCELLED
        ):
            status = GcsimOptimizerRunStatus.CANCELLED
            session_status = GcsimOptimizerSessionStatus.CANCELLED
            error = error or "GCSIM optimizer run was cancelled before completion."
        else:
            session_status = actual_session_status
        artifact = artifact or _ArtifactResolution(status=None)
        return GcsimOptimizerRunResult(
            status=status,
            success=status is GcsimOptimizerRunStatus.PASSED,
            session_status=session_status,
            engine_id=artifact.engine_id,
            engine_path=artifact.engine_path,
            artifact_path="" if artifact.artifact_path is None else str(artifact.artifact_path),
            artifact_source=artifact.artifact_source,
            artifact_sha256=artifact.artifact_sha256,
            engine_binding_sha256=self.request.engine_binding_sha256,
            run_dir="" if run_dir is None else str(run_dir),
            input_config_path="" if input_path is None else str(input_path),
            optimized_config_path="" if optimized_path is None else str(optimized_path),
            result_path="" if result_path is None else str(result_path),
            input_config_bytes=input_config_bytes,
            optimized_config_bytes=optimized_config_bytes,
            result_json_bytes=result_json_bytes,
            input_config_sha256=(
                hashlib.sha256(input_config_bytes).hexdigest()
                if input_config_bytes
                else ""
            ),
            optimized_config_sha256=(
                hashlib.sha256(optimized_config_bytes).hexdigest()
                if optimized_config_bytes
                else ""
            ),
            result_json_sha256=(
                hashlib.sha256(result_json_bytes).hexdigest()
                if result_json_bytes
                else ""
            ),
            optimize=optimize,
            simulate=simulate,
            summary=summary or GcsimResultSummary(),
            elapsed_seconds=round(perf_counter() - started, 6),
            error=_trim_probe_text(error),
        )

    def _transition(
        self,
        status: GcsimOptimizerSessionStatus,
    ) -> GcsimOptimizerSessionStatus:
        changed = False
        with self._lock:
            current = self._status
            if current in _TERMINAL_SESSION_STATUSES:
                return current
            target = status
            if self._cancel_event.is_set() and target not in {
                GcsimOptimizerSessionStatus.CANCELLING,
                GcsimOptimizerSessionStatus.CANCELLED,
            }:
                target = (
                    GcsimOptimizerSessionStatus.CANCELLED
                    if target in _TERMINAL_SESSION_STATUSES
                    else GcsimOptimizerSessionStatus.CANCELLING
                )
            if target is not current:
                self._status = target
                changed = True
            actual = self._status
        if changed and self._on_status is not None:
            try:
                self._on_status(actual)
            except Exception:
                # Observers must not be able to break or mask an engine run.
                pass
        return actual


def run_gcsim_optimizer(
    request: GcsimOptimizerRunRequest,
    *,
    process_factory: OptimizerProcessFactory | None = None,
    on_status: OptimizerStatusCallback | None = None,
) -> GcsimOptimizerRunResult:
    """Convenience entry point for callers that do not need external cancel."""

    return GcsimOptimizerSession(
        request,
        process_factory=process_factory,
        on_status=on_status,
    ).run()


def _validate_request(request: GcsimOptimizerRunRequest) -> str:
    sources = int(request.config_text is not None) + int(request.config_path is not None)
    if sources != 1:
        return "Exactly one of config_text and config_path must be provided."
    for name, value in (
        ("optimizer_timeout_seconds", request.optimizer_timeout_seconds),
        ("simulation_timeout_seconds", request.simulation_timeout_seconds),
    ):
        try:
            timeout = float(value)
        except (TypeError, ValueError):
            return f"{name} must be a positive finite number."
        if not math.isfinite(timeout) or timeout <= 0:
            return f"{name} must be a positive finite number."
    if request.overall_timeout_seconds is not None:
        try:
            overall_timeout = float(request.overall_timeout_seconds)
        except (TypeError, ValueError):
            return "overall_timeout_seconds must be None or a positive finite number."
        if not math.isfinite(overall_timeout) or overall_timeout <= 0:
            return "overall_timeout_seconds must be None or a positive finite number."
    if not isinstance(request.verbose, bool):
        return "verbose must be a boolean."
    option_error = _optimizer_options_error(request.optimizer_options)
    if option_error:
        return option_error
    if not isinstance(request.environment, Mapping):
        return "environment must be a mapping."
    for field_name, value in (
        ("expected_artifact_sha256", request.expected_artifact_sha256),
        ("engine_binding_sha256", request.engine_binding_sha256),
    ):
        normalized = str(value or "").strip().casefold()
        if normalized and (
            len(normalized) != 64
            or any(char not in "0123456789abcdef" for char in normalized)
        ):
            return f"{field_name} must be an empty value or a SHA-256 hex digest."
    if request.engine_binding_sha256 and not request.expected_artifact_sha256:
        return (
            "engine_binding_sha256 requires expected_artifact_sha256 so the "
            "resolved executable is actually bound."
        )
    return ""


def freeze_gcsim_optimizer_environment(
    overrides: Mapping[str, str] | None,
) -> dict[str, str]:
    """Freeze the exact sanitized environment used by optimizer subprocesses."""

    if overrides is not None and not isinstance(overrides, Mapping):
        raise ValueError("optimizer environment overrides must be a mapping")
    ambient = tuple(
        (str(key), str(value))
        for key, value in os.environ.items()
        if str(key).casefold() in _GCSIM_OPTIMIZER_AMBIENT_ENV_ALLOWLIST
    )
    supplied = tuple(
        (str(key), str(value)) for key, value in (overrides or {}).items()
    )
    _validate_environment_pairs(ambient, field_name="ambient environment")
    _validate_environment_pairs(supplied, field_name="optimizer environment")
    values_by_folded_key: dict[str, tuple[str, str]] = {
        key.casefold(): (key, value) for key, value in ambient
    }
    for key, value in supplied:
        values_by_folded_key[key.casefold()] = (key, value)
    return dict(sorted(values_by_folded_key.values(), key=lambda item: item[0]))


def normalize_gcsim_optimizer_frozen_environment(
    environment: Mapping[str, str] | None,
) -> dict[str, str]:
    """Validate/canonicalize a previously frozen environment without ambient reads."""

    if environment is None or not isinstance(environment, Mapping):
        raise ValueError("a frozen optimizer environment must be a mapping")
    pairs = tuple((str(key), str(value)) for key, value in environment.items())
    _validate_environment_pairs(pairs, field_name="frozen optimizer environment")
    values_by_folded_key = {
        key.casefold(): (key, value) for key, value in pairs
    }
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


def _effective_stage_timeout(
    stage_timeout_seconds: float,
    *,
    overall_deadline: float | None,
) -> float:
    if overall_deadline is None:
        return stage_timeout_seconds
    return min(stage_timeout_seconds, max(overall_deadline - monotonic(), 0.0))


def format_gcsim_optimizer_options(options: Mapping[str, int | float]) -> str:
    """Return the canonical upstream ``-options`` value.

    Keys always follow the official CLI order, independently of input mapping
    insertion order.  Validation is performed by the request boundary before
    this helper is called; direct callers receive ``ValueError`` for the same
    invalid input instead of emitting a partially understood CLI string.
    """

    error = _optimizer_options_error(options)
    if error:
        raise ValueError(error)
    return ";".join(
        f"{key}={_canonical_integer(options[key])}"
        for key in GCSIM_OPTIMIZER_OPTION_KEYS
        if key in options
    )


def _optimizer_options_error(options: object) -> str:
    if not isinstance(options, Mapping):
        return "optimizer_options must be a mapping."
    unknown = sorted(str(key) for key in options if key not in GCSIM_OPTIMIZER_OPTION_KEYS)
    if unknown:
        return "Unknown GCSIM optimizer option(s): " + ", ".join(unknown)
    for key in GCSIM_OPTIMIZER_OPTION_KEYS:
        if key not in options:
            continue
        value = options[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"GCSIM optimizer option {key} must be a non-negative integer."
        number = float(value)
        if not math.isfinite(number) or number < 0 or not number.is_integer():
            return f"GCSIM optimizer option {key} must be a non-negative integer."
        if key in GCSIM_OPTIMIZER_BOOLEAN_OPTION_KEYS and int(number) not in (0, 1):
            return f"GCSIM optimizer option {key} must be 0 or 1."
    return ""


def _canonical_integer(value: int | float) -> str:
    return str(int(float(value)))


def _create_isolated_run_dir(
    requested: str | Path | None,
) -> Path | tuple[GcsimOptimizerRunStatus, str]:
    if requested is None:
        parent = DEFAULT_GCSIM_OPTIMIZER_RUNS_DIR
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        path = parent / f"run-{stamp}-{uuid4().hex[:8]}"
    else:
        if not str(requested).strip():
            return (
                GcsimOptimizerRunStatus.INVALID_REQUEST,
                "Explicit optimizer run_dir is empty.",
            )
        path = Path(requested).expanduser().resolve()
    if path.exists():
        return (
            GcsimOptimizerRunStatus.RUN_DIR_EXISTS,
            f"Optimizer run directory already exists: {path}",
        )
    try:
        path.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        return (
            GcsimOptimizerRunStatus.RUN_DIR_FAILED,
            f"Could not create optimizer run directory: {exc}",
        )
    return path


def _read_request_config(
    request: GcsimOptimizerRunRequest,
) -> str | tuple[GcsimOptimizerRunStatus, str]:
    if request.config_text is not None:
        text = str(request.config_text)
    else:
        assert request.config_path is not None
        if not str(request.config_path).strip():
            return GcsimOptimizerRunStatus.INPUT_MISSING, "Optimizer config path is empty."
        path = Path(request.config_path).expanduser().resolve()
        if not path.exists():
            return (
                GcsimOptimizerRunStatus.INPUT_MISSING,
                f"Optimizer config does not exist: {path}",
            )
        if not path.is_file():
            return (
                GcsimOptimizerRunStatus.INPUT_INVALID,
                f"Optimizer config is not a file: {path}",
            )
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            return (
                GcsimOptimizerRunStatus.INPUT_READ_FAILED,
                f"Could not read optimizer config: {exc}",
            )
    if not text.strip():
        return GcsimOptimizerRunStatus.INPUT_INVALID, "Optimizer config is empty."
    return text


def _resolve_artifact(request: GcsimOptimizerRunRequest) -> _ArtifactResolution:
    if request.artifact_path is not None:
        if not str(request.artifact_path).strip():
            return _ArtifactResolution(
                status=GcsimOptimizerRunStatus.ARTIFACT_PATH_MISSING,
                error="Explicit GCSIM artifact path is empty.",
            )
        path = Path(request.artifact_path).expanduser().resolve()
        if not path.exists():
            return _ArtifactResolution(
                status=GcsimOptimizerRunStatus.ARTIFACT_MISSING,
                artifact_path=path,
                artifact_source="explicit",
                error=f"GCSIM artifact is missing: {path}",
            )
        if not path.is_file():
            return _ArtifactResolution(
                status=GcsimOptimizerRunStatus.ARTIFACT_NOT_FILE,
                artifact_path=path,
                artifact_source="explicit",
                error=f"GCSIM artifact is not a file: {path}",
            )
        identity_error, artifact_sha256 = _verify_artifact_identity(path, request)
        if identity_error:
            return _ArtifactResolution(
                status=GcsimOptimizerRunStatus.ARTIFACT_IDENTITY_MISMATCH,
                artifact_path=path,
                artifact_source="explicit",
                artifact_sha256=artifact_sha256,
                error=identity_error,
            )
        return _ArtifactResolution(
            status=None,
            artifact_path=path,
            artifact_source="explicit",
            artifact_sha256=artifact_sha256,
        )

    store = GcsimEngineStore(request.store_dir or DEFAULT_GCSIM_ENGINE_STORE_DIR)
    try:
        active = store.get_active_engine()
    except GcsimEngineStoreError as exc:
        return _ArtifactResolution(
            status=GcsimOptimizerRunStatus.ACTIVE_ENGINE_INVALID,
            artifact_source="active_engine",
            error=str(exc),
        )
    if active is None:
        return _ArtifactResolution(
            status=GcsimOptimizerRunStatus.NO_ACTIVE_ENGINE,
            artifact_source="active_engine",
            error="No active GCSIM engine is configured.",
        )
    artifact_path: Path | None = None
    for key in ("artifact_relative_path", "artifact_path"):
        raw = str(active.manifest.metadata.get(key, "") or "").strip()
        if not raw:
            continue
        candidate = Path(raw)
        artifact_path = candidate if candidate.is_absolute() else active.path / candidate
        artifact_path = artifact_path.resolve()
        break
    if artifact_path is None:
        return _ArtifactResolution(
            status=GcsimOptimizerRunStatus.ARTIFACT_PATH_MISSING,
            artifact_source="active_engine",
            engine_id=active.engine_id,
            engine_path=str(active.path),
            error="Active GCSIM engine manifest does not contain an artifact path.",
        )
    if not artifact_path.exists():
        return _ArtifactResolution(
            status=GcsimOptimizerRunStatus.ARTIFACT_MISSING,
            artifact_path=artifact_path,
            artifact_source="active_engine",
            engine_id=active.engine_id,
            engine_path=str(active.path),
            error=f"Active GCSIM artifact is missing: {artifact_path}",
        )
    if not artifact_path.is_file():
        return _ArtifactResolution(
            status=GcsimOptimizerRunStatus.ARTIFACT_NOT_FILE,
            artifact_path=artifact_path,
            artifact_source="active_engine",
            engine_id=active.engine_id,
            engine_path=str(active.path),
            error=f"Active GCSIM artifact is not a file: {artifact_path}",
        )
    identity_error, artifact_sha256 = _verify_artifact_identity(
        artifact_path,
        request,
    )
    if identity_error:
        return _ArtifactResolution(
            status=GcsimOptimizerRunStatus.ARTIFACT_IDENTITY_MISMATCH,
            artifact_path=artifact_path,
            artifact_source="active_engine",
            artifact_sha256=artifact_sha256,
            engine_id=active.engine_id,
            engine_path=str(active.path),
            error=identity_error,
        )
    return _ArtifactResolution(
        status=None,
        artifact_path=artifact_path,
        artifact_source="active_engine",
        artifact_sha256=artifact_sha256,
        engine_id=active.engine_id,
        engine_path=str(active.path),
    )


def _verify_artifact_identity(
    path: Path,
    request: GcsimOptimizerRunRequest,
) -> tuple[str, str]:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        return f"Could not hash GCSIM artifact: {exc}", ""
    actual = digest.hexdigest()
    expected = str(request.expected_artifact_sha256 or "").strip().casefold()
    if expected and actual != expected:
        return (
            "GCSIM artifact SHA-256 does not match the bound optimizer engine "
            f"context (expected {expected}, observed {actual}).",
            actual,
        )
    return "", actual


def _snapshot_verified_artifact(
    source: Path,
    *,
    run_dir: Path,
    expected_sha256: str,
) -> Path | tuple[GcsimOptimizerRunStatus, str]:
    """Copy and hash the exact executable bytes that the session will launch."""

    destination = run_dir / DEFAULT_GCSIM_OPTIMIZER_EXECUTABLE_FILENAME
    digest = hashlib.sha256()
    try:
        source_mode = source.stat().st_mode
        with source.open("rb") as source_handle, destination.open("xb") as target_handle:
            for chunk in iter(lambda: source_handle.read(1024 * 1024), b""):
                digest.update(chunk)
                target_handle.write(chunk)
        destination.chmod(source_mode)
    except OSError as exc:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        return (
            GcsimOptimizerRunStatus.RUN_DIR_FAILED,
            f"Could not create a private verified GCSIM executable snapshot: {exc}",
        )
    observed = digest.hexdigest()
    if observed != expected_sha256:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        return (
            GcsimOptimizerRunStatus.ARTIFACT_IDENTITY_MISMATCH,
            "GCSIM artifact changed while preparing the optimizer session "
            f"(expected {expected_sha256}, copied {observed}).",
        )
    return destination


def _popen_process(
    command: Sequence[str],
    cwd: Path,
    env: Mapping[str, str],
) -> OptimizerProcess:
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


def _stop_and_collect(process: OptimizerProcess) -> tuple[str, str]:
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


def _stage_diagnostic(
    name: GcsimOptimizerStageName,
    status: GcsimOptimizerStageStatus,
    command: Sequence[str],
    *,
    started: float,
    returncode: int | None = None,
    stdout: str = "",
    stderr: str = "",
    error: str = "",
) -> GcsimOptimizerStageDiagnostic:
    return GcsimOptimizerStageDiagnostic(
        name=name,
        status=status,
        command=tuple(str(part) for part in command),
        returncode=returncode,
        stdout=_trim_probe_text(stdout),
        stderr=_trim_probe_text(stderr),
        elapsed_seconds=round(perf_counter() - started, 6),
        error=_trim_probe_text(error),
    )


def _stage_timeout_before_start(
    name: GcsimOptimizerStageName,
    command: Sequence[str],
    *,
    reason: str,
) -> GcsimOptimizerStageDiagnostic:
    started = perf_counter()
    return _stage_diagnostic(
        name,
        GcsimOptimizerStageStatus.TIMEOUT,
        command,
        started=started,
        error=reason,
    )


def _stage_terminal_status(
    diagnostic: GcsimOptimizerStageDiagnostic,
    *,
    optimize_stage: bool,
) -> GcsimOptimizerRunStatus:
    if diagnostic.status is GcsimOptimizerStageStatus.CANCELLED:
        return GcsimOptimizerRunStatus.CANCELLED
    if optimize_stage:
        if diagnostic.status is GcsimOptimizerStageStatus.START_FAILED:
            return GcsimOptimizerRunStatus.OPTIMIZER_START_FAILED
        if diagnostic.status is GcsimOptimizerStageStatus.TIMEOUT:
            return GcsimOptimizerRunStatus.OPTIMIZER_TIMEOUT
        return GcsimOptimizerRunStatus.OPTIMIZER_FAILED
    if diagnostic.status is GcsimOptimizerStageStatus.START_FAILED:
        return GcsimOptimizerRunStatus.SIMULATION_START_FAILED
    if diagnostic.status is GcsimOptimizerStageStatus.TIMEOUT:
        return GcsimOptimizerRunStatus.SIMULATION_TIMEOUT
    return GcsimOptimizerRunStatus.SIMULATION_FAILED


def _optimizer_result_summary_error(summary: GcsimResultSummary) -> str:
    if (
        summary.dps_mean is None
        or not math.isfinite(summary.dps_mean)
        or summary.dps_mean < 0
    ):
        return "GCSIM optimizer result has no finite non-negative mean DPS."
    if summary.iterations is None or summary.iterations <= 0:
        return "GCSIM optimizer result has no positive iteration count."
    if summary.dps_sd is not None and (
        not math.isfinite(summary.dps_sd) or summary.dps_sd < 0
    ):
        return "GCSIM optimizer result has an invalid DPS standard deviation."
    if summary.incomplete_characters:
        return (
            "GCSIM optimizer result reports incomplete character implementations: "
            + ", ".join(summary.incomplete_characters)
            + "."
        )
    return ""


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


__all__ = [
    "DEFAULT_GCSIM_OPTIMIZER_RUNS_DIR",
    "DEFAULT_GCSIM_OPTIMIZER_TIMEOUT_SECONDS",
    "DEFAULT_GCSIM_OPTIMIZER_SIMULATION_TIMEOUT_SECONDS",
    "GCSIM_OPTIMIZER_OPTION_KEYS",
    "GcsimOptimizerRunRequest",
    "GcsimOptimizerRunResult",
    "GcsimOptimizerRunStatus",
    "GcsimOptimizerSession",
    "GcsimOptimizerSessionStatus",
    "GcsimOptimizerStageDiagnostic",
    "GcsimOptimizerStageName",
    "GcsimOptimizerStageStatus",
    "OptimizerProcessFactory",
    "freeze_gcsim_optimizer_environment",
    "format_gcsim_optimizer_options",
    "normalize_gcsim_optimizer_frozen_environment",
    "run_gcsim_optimizer",
]
