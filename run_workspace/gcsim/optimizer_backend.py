"""Bound Phase-1 backend entry point for one theoretical 4p candidate."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Any, Mapping

from .optimizer_cache import (
    GcsimOptimizerCacheIdentity,
    build_gcsim_optimizer_cache_identity_from_sha256,
)
from .optimizer_candidate import (
    GcsimOptimizerCandidateConfigResult,
    prepare_gcsim_four_piece_optimizer_candidate,
)
from .optimizer_config import (
    GcsimFiveStarMainStatLayout,
    apply_gcsim_optimizer_worker_budget,
)
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_runner import (
    DEFAULT_GCSIM_OPTIMIZER_SIMULATION_TIMEOUT_SECONDS,
    DEFAULT_GCSIM_OPTIMIZER_TIMEOUT_SECONDS,
    GcsimOptimizerRunRequest,
)


PINNED_GCSIM_OPTIMIZER_CONTRACT_VERSION = "gcsim-v2.42.2"


class GcsimBoundOptimizerError(RuntimeError):
    """Raised when a bound operation would violate its engine contract."""


@dataclass(frozen=True, slots=True)
class GcsimBoundOptimizerExecution:
    request: GcsimOptimizerRunRequest
    cache_identity: GcsimOptimizerCacheIdentity


@dataclass(frozen=True, slots=True)
class GcsimBoundOptimizerCandidate:
    engine_context: GcsimOptimizerEngineContext
    candidate: GcsimOptimizerCandidateConfigResult

    @property
    def ready(self) -> bool:
        return self.engine_context.trusted and self.candidate.ready

    def prepared_config(self, *, worker_count: int | None = None) -> str:
        if not self.ready:
            raise GcsimBoundOptimizerError(
                "Bound optimizer candidate is not ready for execution."
            )
        resolved_workers = resolve_gcsim_optimizer_worker_count(worker_count)
        return apply_gcsim_optimizer_worker_budget(
            self.candidate.config_text,
            resolved_workers,
        )

    def build_run_request(
        self,
        *,
        worker_count: int | None = None,
        run_dir: str | Path | None = None,
        optimizer_timeout_seconds: float = DEFAULT_GCSIM_OPTIMIZER_TIMEOUT_SECONDS,
        simulation_timeout_seconds: float = (
            DEFAULT_GCSIM_OPTIMIZER_SIMULATION_TIMEOUT_SECONDS
        ),
        overall_timeout_seconds: float | None = None,
        optimizer_options: Mapping[str, int | float] | None = None,
        verbose: bool = False,
        environment: Mapping[str, str] | None = None,
        environment_is_frozen: bool = False,
    ) -> GcsimOptimizerRunRequest:
        resolved_workers = resolve_gcsim_optimizer_worker_count(worker_count)
        resolved_environment = {
            str(key): str(value)
            for key, value in (environment or {}).items()
        }
        resolved_environment["GOMAXPROCS"] = str(resolved_workers)
        return GcsimOptimizerRunRequest(
            config_text=self.prepared_config(worker_count=resolved_workers),
            artifact_path=self.engine_context.artifact_path,
            run_dir=run_dir,
            optimizer_timeout_seconds=optimizer_timeout_seconds,
            simulation_timeout_seconds=simulation_timeout_seconds,
            overall_timeout_seconds=overall_timeout_seconds,
            optimizer_options=dict(optimizer_options or {}),
            verbose=verbose,
            environment=resolved_environment,
            environment_is_frozen=environment_is_frozen,
            expected_artifact_sha256=self.engine_context.artifact_sha256,
            engine_binding_sha256=self.engine_context.binding_sha256,
        )

    def build_cache_identity(
        self,
        request: GcsimOptimizerRunRequest,
        *,
        mode: str = "theoretical_4p_candidate",
    ) -> GcsimOptimizerCacheIdentity:
        if request.config_text is None or request.config_path is not None:
            raise GcsimBoundOptimizerError(
                "Bound cache identity requires the exact in-memory run request."
            )
        if (
            Path(str(request.artifact_path)).resolve()
            != Path(self.engine_context.artifact_path).resolve()
            or request.expected_artifact_sha256
            != self.engine_context.artifact_sha256
            or request.engine_binding_sha256
            != self.engine_context.binding_sha256
        ):
            raise GcsimBoundOptimizerError(
                "Run request does not belong to this bound engine context."
            )
        config = request.config_text
        return build_gcsim_optimizer_cache_identity_from_sha256(
            engine_sha256=self.engine_context.artifact_sha256,
            engine_version=self.engine_context.engine_version,
            source_config_text=config,
            mode=mode,
            optimizer_options=request.optimizer_options,
            catalog_fingerprint=self.engine_context.catalog.source_fingerprint,
            candidate_key=hashlib.sha256(config.encode("utf-8")).hexdigest(),
        )

    def build_execution(
        self,
        *,
        worker_count: int | None = None,
        run_dir: str | Path | None = None,
        optimizer_timeout_seconds: float = DEFAULT_GCSIM_OPTIMIZER_TIMEOUT_SECONDS,
        simulation_timeout_seconds: float = (
            DEFAULT_GCSIM_OPTIMIZER_SIMULATION_TIMEOUT_SECONDS
        ),
        overall_timeout_seconds: float | None = None,
        optimizer_options: Mapping[str, int | float] | None = None,
        verbose: bool = False,
        environment: Mapping[str, str] | None = None,
        environment_is_frozen: bool = False,
        mode: str = "theoretical_4p_candidate",
    ) -> GcsimBoundOptimizerExecution:
        """Build one request and its cache identity from the exact same spec."""

        request = self.build_run_request(
            worker_count=worker_count,
            run_dir=run_dir,
            optimizer_timeout_seconds=optimizer_timeout_seconds,
            simulation_timeout_seconds=simulation_timeout_seconds,
            overall_timeout_seconds=overall_timeout_seconds,
            optimizer_options=optimizer_options,
            verbose=verbose,
            environment=environment,
            environment_is_frozen=environment_is_frozen,
        )
        return GcsimBoundOptimizerExecution(
            request=request,
            cache_identity=self.build_cache_identity(request, mode=mode),
        )


def prepare_bound_gcsim_four_piece_optimizer_candidate(
    config_text: str,
    *,
    engine_context: GcsimOptimizerEngineContext,
    set_assignments: Mapping[str, str],
    main_stat_layouts: Mapping[
        str,
        GcsimFiveStarMainStatLayout | Mapping[str, Any],
    ],
    four_star_offpiece_slots: Mapping[str, str] | None = None,
    require_full_team: bool = True,
) -> GcsimBoundOptimizerCandidate:
    """Prepare a candidate whose catalog and executable share one identity."""

    if not engine_context.trusted:
        raise GcsimBoundOptimizerError(
            "Optimizer engine context is not resealed and cannot be executed."
        )
    if (
        engine_context.optimizer_contract_version
        != PINNED_GCSIM_OPTIMIZER_CONTRACT_VERSION
    ):
        raise GcsimBoundOptimizerError(
            "Unsupported GCSIM optimizer renderer contract: "
            f"{engine_context.optimizer_contract_version!r}; expected "
            f"{PINNED_GCSIM_OPTIMIZER_CONTRACT_VERSION!r}."
        )
    candidate = prepare_gcsim_four_piece_optimizer_candidate(
        config_text,
        set_assignments=set_assignments,
        main_stat_layouts=main_stat_layouts,
        set_catalog=engine_context.catalog,
        four_star_offpiece_slots=four_star_offpiece_slots,
        require_full_team=require_full_team,
    )
    return GcsimBoundOptimizerCandidate(
        engine_context=engine_context,
        candidate=candidate,
    )


def resolve_gcsim_optimizer_worker_count(requested: int | None = None) -> int:
    """Resolve the single-process Auto policy: logical CPUs minus one."""

    logical_cpus = os.cpu_count() or 1
    if requested is None:
        return max(1, logical_cpus - 1)
    if isinstance(requested, bool) or not isinstance(requested, int):
        raise GcsimBoundOptimizerError("worker_count must be an integer or None")
    if requested <= 0:
        raise GcsimBoundOptimizerError("worker_count must be positive")
    if requested > logical_cpus:
        raise GcsimBoundOptimizerError(
            f"worker_count cannot exceed detected logical CPUs ({logical_cpus})"
        )
    return requested


__all__ = [
    "GcsimBoundOptimizerCandidate",
    "GcsimBoundOptimizerExecution",
    "GcsimBoundOptimizerError",
    "PINNED_GCSIM_OPTIMIZER_CONTRACT_VERSION",
    "prepare_bound_gcsim_four_piece_optimizer_candidate",
    "resolve_gcsim_optimizer_worker_count",
]
