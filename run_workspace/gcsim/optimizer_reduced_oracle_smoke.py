"""Explicit local real-engine smoke for Milestone 3 reduced account oracle.

This module is intentionally outside the unit suite.  It uses the committed
synthetic prepared-team fixture, creates a one-build-per-wearer in-memory
artifact domain, and runs exactly one compiled oracle candidate through the
active GCSIM artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tempfile

from .artifact_runner import run_active_gcsim_artifact
from .farming_profile_config import apply_gcsim_screening_runtime_options
from .optimizer_account_oracle import (
    run_gcsim_optimizer_account_four_piece_oracle,
)
from .optimizer_artifact_database import (
    GcsimOptimizerArtifactDatabaseInput,
    GcsimOptimizerArtifactRecord,
)
from .optimizer_config_shell import build_gcsim_optimizer_config_shell
from .optimizer_engine_context import (
    GcsimOptimizerEngineContextError,
    load_active_gcsim_optimizer_engine_context,
)
from .optimizer_oracle import GcsimOptimizerOracleScore
from .optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimFourPieceTargetPackage,
    GcsimOptimizerAccountScope,
    GcsimOptimizerFourStarEligibilityOverride,
    GcsimOptimizerOperation,
    GcsimOptimizerOperationRequest,
    GcsimOptimizerSetReference,
    GcsimOptimizerSourceSimulationIdentity,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWearerSetPool,
    GcsimOptimizerWearerTarget,
    GcsimOptimizerWorkPlan,
)
from .optimizer_run_input import build_gcsim_optimizer_run_input
from .prepared_config_adapter import (
    CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH,
    DEFAULT_PREPARED_CHASCA_TEAM_FIXTURE_PATH,
    build_prepared_team_full_config_report_from_json,
)


@dataclass(frozen=True, slots=True)
class GcsimOptimizerReducedOracleSmokeResult:
    status: str
    success: bool
    evaluated_simulations: int = 0
    disjoint_assignments: int = 0
    dps_mean: float | None = None
    dps_se: float | None = None
    iterations: int | None = None
    winner_simulation_sha256: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "success": self.success,
            "evaluated_simulations": self.evaluated_simulations,
            "disjoint_assignments": self.disjoint_assignments,
            "dps_mean": self.dps_mean,
            "dps_se": self.dps_se,
            "iterations": self.iterations,
            "winner_simulation_sha256": self.winner_simulation_sha256,
            "error": self.error,
        }


def run_optimizer_reduced_oracle_real_smoke(
    *,
    iterations: int = 10,
    timeout_seconds: int = 120,
) -> GcsimOptimizerReducedOracleSmokeResult:
    try:
        engine = load_active_gcsim_optimizer_engine_context()
        prepared = build_prepared_team_full_config_report_from_json(
            DEFAULT_PREPARED_CHASCA_TEAM_FIXTURE_PATH,
            rotation_shell_path=(
                CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH
            ),
            write_config=False,
        )
        if not prepared.ready:
            return _failed(
                "prepared_config_not_ready",
                str(prepared.issues),
            )
        config = apply_gcsim_screening_runtime_options(
            prepared.assembly.config_text,
            iterations=iterations,
            workers=1,
        )
        wearers = tuple(
            GcsimOptimizerWearerIdentity(
                team_slot=index,
                account_character_id=30_000 + index,
                gcsim_character_key=key,
            )
            for index, key in enumerate(
                ("chasca", "ororon", "furina", "bennett"),
                start=1,
            )
        )
        source = GcsimOptimizerSourceSimulationIdentity(
            engine_id=engine.engine_id,
            engine_version=engine.engine_version,
            optimizer_contract_version=engine.optimizer_contract_version,
            artifact_sha256=engine.artifact_sha256,
            engine_tree_sha256=engine.engine_tree_sha256,
            engine_binding_sha256=engine.binding_sha256,
            catalog_fingerprint=engine.catalog.source_fingerprint,
            prepared_config_sha256=_sha256_text(config),
            rotation_sha256=_sha256_file(
                CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH
            ),
            target_sha256=_sha256_text(
                "target lvl=100 resist=0.1 radius=2 pos=0,2.4 hp=999999999;"
            ),
            simulation_options_sha256=_sha256_text(
                f"iteration={iterations};workers=1"
            ),
            wearers=wearers,
        )
        shell_result = build_gcsim_optimizer_config_shell(
            config,
            source_simulation=source,
            engine_context=engine,
        )
        if not shell_result.ready or shell_result.shell is None:
            return _failed(
                "config_shell_not_ready",
                str(shell_result.issues),
            )
        source_keys = tuple(
            sorted(
                item.key
                for item in engine.catalog.sets
                if item.max_rarity == 4 and item.complete_four_piece_modeled
            )
        )[:4]
        if len(source_keys) != 4:
            return _failed(
                "fixture_set_missing",
                "active catalog has fewer than four modeled 4-star sets",
            )
        set_refs = tuple(
            GcsimOptimizerSetReference(
                set_uid=key,
                gcsim_set_key=key,
                engine_binding_sha256=engine.binding_sha256,
                catalog_fingerprint=engine.catalog.source_fingerprint,
            )
            for key in source_keys
        )
        missing_sets = tuple(
            set_ref.gcsim_set_key
            for set_ref in set_refs
            if engine.catalog.get(set_ref.gcsim_set_key) is None
        )
        if missing_sets:
            return _failed(
                "fixture_set_missing",
                f"active catalog is missing: {missing_sets!r}",
            )
        artifacts = _smoke_artifacts(set_refs)
        database_sha256 = _sha256_text(
            json.dumps(
                [item.to_dict() for item in artifacts],
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        database = GcsimOptimizerArtifactDatabaseInput(
            database_path="<in-memory-reduced-real-smoke>",
            artifact_database_input_sha256=database_sha256,
            engine_binding_sha256=engine.binding_sha256,
            catalog_fingerprint=engine.catalog.source_fingerprint,
            artifact_columns=(
                "id",
                "set_uid",
                "pos",
                "rarity",
                "level",
                "main_property_type",
                "main_property_name",
                "main_property_value",
            ),
            substat_columns=(
                "artifact_id",
                "slot_index",
                "property_type",
                "property_name",
                "value",
                "times",
            ),
            artifacts=artifacts,
            raw_substat_row_count=0,
            issues=(),
        )
        request = GcsimOptimizerOperationRequest(
            operation=GcsimOptimizerOperation.ACCOUNT_ARTIFACTS,
            source_simulation=source,
            work_plan=GcsimOptimizerWorkPlan(
                operation=GcsimOptimizerOperation.ACCOUNT_ARTIFACTS,
                plan_id="m3_real_smoke",
                plan_version=1,
                parameters={"iterations": iterations},
            ),
            account_scope=GcsimOptimizerAccountScope.SELECTED_SET_POOLS,
            selected_set_pools=tuple(
                GcsimOptimizerWearerSetPool(wearer, (set_ref,))
                for wearer, set_ref in zip(wearers, set_refs, strict=True)
            ),
            four_star_overrides=tuple(
                GcsimOptimizerFourStarEligibilityOverride(
                    wearer=wearer,
                    allowed_set_uids=(set_ref.set_uid,),
                )
                for wearer, set_ref in zip(wearers, set_refs, strict=True)
            ),
            artifact_database_input_sha256=database_sha256,
        )
        run_input_result = build_gcsim_optimizer_run_input(
            request=request,
            config_shell=shell_result.shell,
            artifact_database=database,
            engine_context=engine,
        )
        if not run_input_result.ready or run_input_result.run_input is None:
            return _failed(
                "run_input_not_ready",
                str(run_input_result.issues),
            )
        targets = tuple(
            GcsimOptimizerWearerTarget(
                wearer,
                GcsimFourPieceTargetPackage(set_ref),
            )
            for wearer, set_ref in zip(wearers, set_refs, strict=True)
        )
        with tempfile.TemporaryDirectory(prefix="gtt-m3-oracle-smoke-") as temp:
            run_root = Path(temp)

            def evaluate(candidate):
                artifact_result = run_active_gcsim_artifact(
                    candidate.config_text,
                    run_dir=run_root / candidate.simulation_sha256,
                    timeout_seconds=timeout_seconds,
                )
                if (
                    not artifact_result.success
                    or artifact_result.summary.dps_mean is None
                ):
                    raise RuntimeError(
                        artifact_result.error
                        or artifact_result.stderr
                        or artifact_result.status
                    )
                result_path = Path(artifact_result.result_path)
                return GcsimOptimizerOracleScore(
                    objective_name="real_gcsim_dps",
                    objective_value=artifact_result.summary.dps_mean,
                    standard_error=artifact_result.summary.dps_se,
                    iterations=artifact_result.summary.iterations,
                    evidence_sha256=_sha256_file(result_path),
                )

            oracle = run_gcsim_optimizer_account_four_piece_oracle(
                run_input_result.run_input,
                targets=targets,
                execution_identity_sha256=_sha256_text(
                    f"m3-real-smoke:{iterations}:workers=1"
                ),
                evaluator=evaluate,
            )
        return GcsimOptimizerReducedOracleSmokeResult(
            status="passed",
            success=True,
            evaluated_simulations=len(oracle.evaluations),
            disjoint_assignments=(
                oracle.coverage.joint_disjoint_assignment_count
            ),
            dps_mean=oracle.winner.score.objective_value,
            dps_se=oracle.winner.score.standard_error,
            iterations=oracle.winner.score.iterations,
            winner_simulation_sha256=oracle.winner_candidate_sha256,
        )
    except (OSError, ValueError, RuntimeError, GcsimOptimizerEngineContextError) as exc:
        return _failed("failed", str(exc))


def _smoke_artifacts(
    set_refs: tuple[GcsimOptimizerSetReference, ...],
) -> tuple[GcsimOptimizerArtifactRecord, ...]:
    main_types = (2, 5, 6, 40, 20)
    main_names = ("HP", "ATK", "ATK%", "Pyro DMG", "CRIT Rate")
    main_values = ("3571", "232", "34.8%", "34.8%", "23.2%")
    artifacts: list[GcsimOptimizerArtifactRecord] = []
    artifact_id = 1
    for set_ref in set_refs:
        for position, slot in enumerate(
            GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
            start=1,
        ):
            artifacts.append(
                GcsimOptimizerArtifactRecord(
                    artifact_id=artifact_id,
                    set_uid=set_ref.set_uid,
                    gcsim_set_key=set_ref.gcsim_set_key,
                    set_mapping_status="ready",
                    position=position,
                    position_key=slot,
                    rarity=4,
                    level=16,
                    main_property_type=main_types[position - 1],
                    main_property_name=main_names[position - 1],
                    main_property_value=main_values[position - 1],
                    main_numeric_value=float(
                        main_values[position - 1].rstrip("%")
                    ),
                    substats=(),
                    calculation_valid=True,
                    default_eligible=False,
                    issues=(),
                    raw_columns=(
                        ("id", artifact_id),
                        ("set_uid", set_ref.set_uid),
                        ("pos", position),
                        ("rarity", 4),
                        ("level", 16),
                        ("main_property_type", main_types[position - 1]),
                        ("main_property_name", main_names[position - 1]),
                        ("main_property_value", main_values[position - 1]),
                    ),
                )
            )
            artifact_id += 1
    return tuple(artifacts)


def _failed(
    status: str,
    error: str,
) -> GcsimOptimizerReducedOracleSmokeResult:
    return GcsimOptimizerReducedOracleSmokeResult(
        status=status,
        success=False,
        error=error,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> int:
    result = run_optimizer_reduced_oracle_real_smoke()
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
