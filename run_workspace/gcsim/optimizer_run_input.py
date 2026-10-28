"""Immutable optimizer run input assembled from Milestone 0R/1 contracts.

Milestone 2 freezes the already loaded database boundary together with the
prepared config shell and account request.  The resulting object never owns a
SQLite connection and exposes a deterministic hash over calculation-relevant
artifact fields separately from the Milestone 1 raw all-row database hash.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Mapping

from .artifact_set_catalog import GcsimArtifactSetCapability
from .optimizer_artifact_database import (
    GcsimOptimizerArtifactDatabaseInput,
    GcsimOptimizerArtifactRecord,
)
from .optimizer_config_shell import GcsimOptimizerConfigShell
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_product_contracts import (
    GcsimOptimizerOperation,
    GcsimOptimizerOperationRequest,
)
from .optimizer_two_piece_signatures import (
    GcsimOptimizerTwoPieceEffectDescriptor,
    GcsimOptimizerTwoPieceProofKind,
    GcsimOptimizerTwoPieceSignatureError,
    build_gcsim_optimizer_guaranteed_two_piece_stat_effects,
)


GCSIM_OPTIMIZER_RUN_INPUT_SCHEMA_VERSION = 2
OPTIMIZER_RUN_INPUT_READY = "ready"
OPTIMIZER_RUN_INPUT_NOT_READY = "not_ready"


@dataclass(frozen=True, slots=True)
class GcsimOptimizerRunInputIssue:
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class GcsimOptimizerRunInput:
    request: GcsimOptimizerOperationRequest
    config_shell: GcsimOptimizerConfigShell
    artifact_database: GcsimOptimizerArtifactDatabaseInput
    optimizer_artifact_input_sha256: str
    run_input_sha256: str
    engine_binding_sha256: str
    catalog_fingerprint: str
    set_capabilities: tuple[GcsimArtifactSetCapability, ...]
    guaranteed_two_piece_stat_effects: tuple[
        GcsimOptimizerTwoPieceEffectDescriptor, ...
    ] = ()
    schema_version: int = GCSIM_OPTIMIZER_RUN_INPUT_SCHEMA_VERSION
    _artifact_by_id: Mapping[int, GcsimOptimizerArtifactRecord] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )
    _set_capability_by_key: Mapping[str, GcsimArtifactSetCapability] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_RUN_INPUT_SCHEMA_VERSION:
            raise ValueError("unsupported optimizer run input schema")
        if not isinstance(self.request, GcsimOptimizerOperationRequest):
            raise TypeError("request must be typed")
        if not isinstance(self.config_shell, GcsimOptimizerConfigShell):
            raise TypeError("config_shell must be typed")
        if not isinstance(
            self.artifact_database,
            GcsimOptimizerArtifactDatabaseInput,
        ):
            raise TypeError("artifact_database must be typed")
        for field_name in (
            "optimizer_artifact_input_sha256",
            "run_input_sha256",
            "engine_binding_sha256",
            "catalog_fingerprint",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        artifact_lookup = {
            artifact.artifact_id: artifact
            for artifact in self.artifact_database.artifacts
        }
        if self._artifact_by_id and dict(self._artifact_by_id) != artifact_lookup:
            raise ValueError("_artifact_by_id differs from frozen database rows")
        object.__setattr__(
            self,
            "_artifact_by_id",
            MappingProxyType(artifact_lookup),
        )
        capabilities = tuple(self.set_capabilities)
        if any(
            not isinstance(item, GcsimArtifactSetCapability)
            for item in capabilities
        ):
            raise TypeError("set_capabilities must be typed")
        capability_lookup = {
            item.key.casefold(): item for item in capabilities
        }
        if len(capability_lookup) != len(capabilities):
            raise ValueError("set_capabilities contain duplicate keys")
        if (
            self._set_capability_by_key
            and dict(self._set_capability_by_key) != capability_lookup
        ):
            raise ValueError(
                "_set_capability_by_key differs from frozen capabilities"
            )
        object.__setattr__(self, "set_capabilities", capabilities)
        object.__setattr__(
            self,
            "_set_capability_by_key",
            MappingProxyType(capability_lookup),
        )
        guaranteed_effects = tuple(self.guaranteed_two_piece_stat_effects)
        if any(
            not isinstance(item, GcsimOptimizerTwoPieceEffectDescriptor)
            or item.proof_kind
            is not GcsimOptimizerTwoPieceProofKind.STATIC_STAT
            for item in guaranteed_effects
        ):
            raise TypeError(
                "guaranteed_two_piece_stat_effects must contain only typed "
                "static-stat proofs"
            )
        if guaranteed_effects != tuple(
            sorted(guaranteed_effects, key=lambda item: item.set_key)
        ) or len({item.set_key for item in guaranteed_effects}) != len(
            guaranteed_effects
        ):
            raise ValueError(
                "guaranteed two-piece stat effects must be sorted and unique"
            )
        if any(
            item.engine_binding_sha256 != self.engine_binding_sha256
            or item.catalog_fingerprint != self.catalog_fingerprint
            or item.set_key not in capability_lookup
            for item in guaranteed_effects
        ):
            raise ValueError(
                "guaranteed two-piece stat effects differ from the frozen "
                "engine/catalog"
            )
        object.__setattr__(
            self,
            "guaranteed_two_piece_stat_effects",
            guaranteed_effects,
        )
        if (
            build_gcsim_optimizer_relevant_artifact_sha256(
                self.artifact_database
            )
            != self.optimizer_artifact_input_sha256
        ):
            raise ValueError(
                "optimizer_artifact_input_sha256 differs from artifact rows"
            )
        expected_run_hash = _canonical_sha256(self.identity_payload())
        if expected_run_hash != self.run_input_sha256:
            raise ValueError("run_input_sha256 differs from frozen inputs")

    def artifact_by_id(
        self,
        artifact_id: int,
    ) -> GcsimOptimizerArtifactRecord | None:
        return self._artifact_by_id.get(artifact_id)

    def set_capability(
        self,
        gcsim_set_key: str,
    ) -> GcsimArtifactSetCapability | None:
        return self._set_capability_by_key.get(gcsim_set_key.casefold())

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_sha256": self.request.request_sha256,
            "source_simulation_sha256": (
                self.request.source_simulation.identity_sha256
            ),
            "config_shell_sha256": self.config_shell.shell_sha256,
            "artifact_database_input_sha256": (
                self.artifact_database.artifact_database_input_sha256
            ),
            "optimizer_artifact_input_sha256": (
                self.optimizer_artifact_input_sha256
            ),
            "engine_binding_sha256": self.engine_binding_sha256,
            "catalog_fingerprint": self.catalog_fingerprint,
            "guaranteed_two_piece_stat_effects_sha256": _canonical_sha256(
                [item.to_dict() for item in self.guaranteed_two_piece_stat_effects]
            ),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self.identity_payload(),
            "run_input_sha256": self.run_input_sha256,
            "request": self.request.to_dict(),
            "config_shell": self.config_shell.to_dict(),
            "artifact_database": self.artifact_database.to_dict(),
            "set_capabilities": [
                item.to_dict() for item in self.set_capabilities
            ],
            "guaranteed_two_piece_stat_effects": [
                item.to_dict()
                for item in self.guaranteed_two_piece_stat_effects
            ],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerRunInputResult:
    status: str
    ready: bool
    run_input: GcsimOptimizerRunInput | None = None
    issues: tuple[GcsimOptimizerRunInputIssue, ...] = ()

    def __post_init__(self) -> None:
        expected_status = (
            OPTIMIZER_RUN_INPUT_READY
            if self.ready
            else OPTIMIZER_RUN_INPUT_NOT_READY
        )
        if self.status != expected_status:
            raise ValueError("run input status/readiness is incoherent")
        if self.ready != (self.run_input is not None and not self.issues):
            raise ValueError("run input result readiness is incoherent")

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "ready": self.ready,
            "run_input": (
                None if self.run_input is None else self.run_input.to_dict()
            ),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def build_gcsim_optimizer_run_input(
    *,
    request: GcsimOptimizerOperationRequest,
    config_shell: GcsimOptimizerConfigShell,
    artifact_database: GcsimOptimizerArtifactDatabaseInput,
    engine_context: GcsimOptimizerEngineContext,
) -> GcsimOptimizerRunInputResult:
    """Bind request, shell, engine, and all frozen artifact rows."""

    issue = _preflight_issue(
        request=request,
        config_shell=config_shell,
        artifact_database=artifact_database,
        engine_context=engine_context,
    )
    if issue is not None:
        return _not_ready(issue)
    optimizer_hash = build_gcsim_optimizer_relevant_artifact_sha256(
        artifact_database
    )
    try:
        guaranteed_effects = (
            build_gcsim_optimizer_guaranteed_two_piece_stat_effects(
                engine_context
            )
        )
    except (GcsimOptimizerTwoPieceSignatureError, OSError, UnicodeError) as exc:
        return _not_ready(
            GcsimOptimizerRunInputIssue(
                "guaranteed_set_stat_proof_unavailable",
                "Could not freeze guaranteed static set-stat proof: "
                f"{type(exc).__name__}: {exc}",
            )
        )
    guaranteed_effects_sha256 = _canonical_sha256(
        [item.to_dict() for item in guaranteed_effects]
    )
    identity_payload = {
        "schema_version": GCSIM_OPTIMIZER_RUN_INPUT_SCHEMA_VERSION,
        "request_sha256": request.request_sha256,
        "source_simulation_sha256": request.source_simulation.identity_sha256,
        "config_shell_sha256": config_shell.shell_sha256,
        "artifact_database_input_sha256": (
            artifact_database.artifact_database_input_sha256
        ),
        "optimizer_artifact_input_sha256": optimizer_hash,
        "engine_binding_sha256": engine_context.binding_sha256,
        "catalog_fingerprint": engine_context.catalog.source_fingerprint,
        "guaranteed_two_piece_stat_effects_sha256": (
            guaranteed_effects_sha256
        ),
    }
    run_input = GcsimOptimizerRunInput(
        request=request,
        config_shell=config_shell,
        artifact_database=artifact_database,
        optimizer_artifact_input_sha256=optimizer_hash,
        run_input_sha256=_canonical_sha256(identity_payload),
        engine_binding_sha256=engine_context.binding_sha256,
        catalog_fingerprint=engine_context.catalog.source_fingerprint,
        set_capabilities=engine_context.catalog.sets,
        guaranteed_two_piece_stat_effects=guaranteed_effects,
    )
    return GcsimOptimizerRunInputResult(
        status=OPTIMIZER_RUN_INPUT_READY,
        ready=True,
        run_input=run_input,
    )


def build_gcsim_optimizer_relevant_artifact_sha256(
    artifact_database: GcsimOptimizerArtifactDatabaseInput,
) -> str:
    """Hash only exact stored fields that can affect materialization."""

    if not isinstance(
        artifact_database,
        GcsimOptimizerArtifactDatabaseInput,
    ):
        raise TypeError("artifact_database must be typed")
    payload = {
        "schema_version": GCSIM_OPTIMIZER_RUN_INPUT_SCHEMA_VERSION,
        "artifacts": [
            {
                "id": artifact.artifact_id,
                "set_uid": artifact.set_uid,
                "position": artifact.position,
                "rarity": artifact.rarity,
                "level": artifact.level,
                "main_property_type": artifact.main_property_type,
                "main_property_name": artifact.main_property_name,
                "main_property_value": _json_sqlite_value(
                    artifact.main_property_value
                ),
                "substats": [
                    {
                        "slot_index": substat.slot_index,
                        "property_type": substat.property_type,
                        "property_name": substat.property_name,
                        "value": _json_sqlite_value(substat.stored_value),
                        "times": substat.times,
                    }
                    for substat in artifact.substats
                ],
            }
            for artifact in artifact_database.artifacts
        ],
    }
    return _canonical_sha256(payload)


def _preflight_issue(
    *,
    request: GcsimOptimizerOperationRequest,
    config_shell: GcsimOptimizerConfigShell,
    artifact_database: GcsimOptimizerArtifactDatabaseInput,
    engine_context: GcsimOptimizerEngineContext,
) -> GcsimOptimizerRunInputIssue | None:
    if not isinstance(request, GcsimOptimizerOperationRequest):
        return GcsimOptimizerRunInputIssue(
            "request_invalid",
            "request must be a GcsimOptimizerOperationRequest.",
        )
    if request.operation is not GcsimOptimizerOperation.ACCOUNT_ARTIFACTS:
        return GcsimOptimizerRunInputIssue(
            "request_operation_invalid",
            "Milestone 2 real-artifact input requires account_artifacts.",
        )
    if not isinstance(config_shell, GcsimOptimizerConfigShell):
        return GcsimOptimizerRunInputIssue(
            "config_shell_invalid",
            "config_shell must be a GcsimOptimizerConfigShell.",
        )
    if not isinstance(
        artifact_database,
        GcsimOptimizerArtifactDatabaseInput,
    ):
        return GcsimOptimizerRunInputIssue(
            "artifact_database_invalid",
            "artifact_database must be typed.",
        )
    if not isinstance(engine_context, GcsimOptimizerEngineContext):
        return GcsimOptimizerRunInputIssue(
            "engine_context_invalid",
            "engine_context must be typed.",
        )
    if not engine_context.trusted or engine_context.issues:
        return GcsimOptimizerRunInputIssue(
            "engine_context_untrusted",
            "A trusted issue-free optimizer engine context is required.",
        )
    if request.source_simulation.identity_sha256 != (
        config_shell.source_simulation_sha256
    ):
        return GcsimOptimizerRunInputIssue(
            "source_simulation_mismatch",
            "Request and config shell source simulation identities differ.",
        )
    if request.source_simulation.prepared_config_sha256 != (
        config_shell.source_config_sha256
    ):
        return GcsimOptimizerRunInputIssue(
            "source_config_mismatch",
            "Request and config shell prepared config identities differ.",
        )
    if request.source_simulation.wearers != config_shell.wearers:
        return GcsimOptimizerRunInputIssue(
            "source_wearers_mismatch",
            "Request and config shell wearer identities differ.",
        )
    if request.artifact_database_input_sha256 != (
        artifact_database.artifact_database_input_sha256
    ):
        return GcsimOptimizerRunInputIssue(
            "artifact_database_identity_mismatch",
            "Request and frozen artifact database identities differ.",
        )
    binding_values = {
        request.source_simulation.engine_binding_sha256,
        artifact_database.engine_binding_sha256,
        engine_context.binding_sha256,
    }
    if len(binding_values) != 1:
        return GcsimOptimizerRunInputIssue(
            "engine_binding_mismatch",
            "Request, database, and active engine bindings differ.",
        )
    catalog_values = {
        request.source_simulation.catalog_fingerprint,
        artifact_database.catalog_fingerprint,
        engine_context.catalog.source_fingerprint,
    }
    if len(catalog_values) != 1:
        return GcsimOptimizerRunInputIssue(
            "catalog_binding_mismatch",
            "Request, database, and active set catalogs differ.",
        )
    return None


def _not_ready(
    issue: GcsimOptimizerRunInputIssue,
) -> GcsimOptimizerRunInputResult:
    return GcsimOptimizerRunInputResult(
        status=OPTIMIZER_RUN_INPUT_NOT_READY,
        ready=False,
        issues=(issue,),
    )


def _json_sqlite_value(value: object) -> object:
    if isinstance(value, bytes):
        return {"sqlite_blob_hex": value.hex()}
    return value


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_sha256(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


__all__ = [
    "GCSIM_OPTIMIZER_RUN_INPUT_SCHEMA_VERSION",
    "GcsimOptimizerRunInput",
    "GcsimOptimizerRunInputIssue",
    "GcsimOptimizerRunInputResult",
    "OPTIMIZER_RUN_INPUT_NOT_READY",
    "OPTIMIZER_RUN_INPUT_READY",
    "build_gcsim_optimizer_relevant_artifact_sha256",
    "build_gcsim_optimizer_run_input",
]
