"""Reduced exhaustive real-account package oracle for Milestones 3A and 10."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import product
from math import prod

from .optimizer_artifact_database import (
    GcsimOptimizerArtifactRecord,
    evaluate_gcsim_optimizer_artifact_eligibility,
)
from .optimizer_artifact_materializer import (
    GcsimOptimizerCompiledTeamCandidate,
    GcsimOptimizerMaterializedBuild,
    GcsimOptimizerSimulationWitnessBucket,
    add_gcsim_optimizer_simulation_witness,
    compile_gcsim_optimizer_team_candidate,
    materialize_gcsim_optimizer_wearer_build,
)
from .optimizer_oracle import (
    GcsimOptimizerOracleScore,
    GcsimOptimizerReducedOracleError,
    GcsimOptimizerReducedOracleLimits,
)
from .optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimFourPieceTargetPackage,
    GcsimOptimizerAccountAssignmentWitness,
    GcsimOptimizerOperation,
    GcsimOptimizerWearerArtifactAssignment,
    GcsimOptimizerWearerIdentity,
    GcsimOptimizerWearerTarget,
    GcsimTwoPlusTwoTargetPackage,
)
from .optimizer_run_input import GcsimOptimizerRunInput


GCSIM_OPTIMIZER_ACCOUNT_FOUR_PIECE_ORACLE_SCHEMA_VERSION = 1
GCSIM_OPTIMIZER_ACCOUNT_PACKAGE_ORACLE_SCHEMA_VERSION = (
    GCSIM_OPTIMIZER_ACCOUNT_FOUR_PIECE_ORACLE_SCHEMA_VERSION
)

AccountOracleEvaluator = Callable[
    [GcsimOptimizerCompiledTeamCandidate],
    GcsimOptimizerOracleScore,
]


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAccountOracleWearerCoverage:
    wearer: GcsimOptimizerWearerIdentity
    eligible_artifact_ids_by_slot: tuple[tuple[str, tuple[int, ...]], ...]
    excluded_artifacts: tuple[tuple[int, str], ...]
    excluded_artifact_counts: tuple[tuple[str, int], ...]
    raw_cartesian_assignment_count: int
    legal_build_count: int
    five_piece_build_count: int
    offpiece_build_counts: tuple[tuple[str, int], ...]
    package_shape_build_counts: tuple[tuple[str, int], ...]
    materialization_rejection_count: int
    schema_version: int = (
        GCSIM_OPTIMIZER_ACCOUNT_FOUR_PIECE_ORACLE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_ACCOUNT_FOUR_PIECE_ORACLE_SCHEMA_VERSION
        ):
            raise GcsimOptimizerReducedOracleError(
                "unsupported account oracle coverage schema"
            )
        if tuple(
            slot for slot, _artifact_ids in self.eligible_artifact_ids_by_slot
        ) != GCSIM_OPTIMIZER_ARTIFACT_SLOTS:
            raise GcsimOptimizerReducedOracleError(
                "eligible artifact coverage must use canonical slot order"
            )
        if tuple(
            slot for slot, _count in self.offpiece_build_counts
        ) != GCSIM_OPTIMIZER_ARTIFACT_SLOTS:
            raise GcsimOptimizerReducedOracleError(
                "offpiece coverage must use canonical slot order"
            )
        for _slot, artifact_ids in self.eligible_artifact_ids_by_slot:
            if tuple(sorted(artifact_ids)) != artifact_ids:
                raise GcsimOptimizerReducedOracleError(
                    "eligible artifact IDs must use deterministic order"
                )
            if len(set(artifact_ids)) != len(artifact_ids):
                raise GcsimOptimizerReducedOracleError(
                    "eligible artifact IDs must be unique"
                )
        if tuple(sorted(self.excluded_artifacts)) != self.excluded_artifacts:
            raise GcsimOptimizerReducedOracleError(
                "excluded artifacts must use deterministic ID order"
            )
        excluded_ids = tuple(
            artifact_id for artifact_id, _reason in self.excluded_artifacts
        )
        if len(set(excluded_ids)) != len(excluded_ids):
            raise GcsimOptimizerReducedOracleError(
                "an artifact may have only one oracle exclusion reason"
            )
        expected_excluded_counts = tuple(
            sorted(
                Counter(
                    reason for _artifact_id, reason in self.excluded_artifacts
                ).items()
            )
        )
        if self.excluded_artifact_counts != expected_excluded_counts:
            raise GcsimOptimizerReducedOracleError(
                "excluded artifact summary differs from exact rows"
            )
        for field_name in (
            "raw_cartesian_assignment_count",
            "legal_build_count",
            "five_piece_build_count",
            "materialization_rejection_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        for reason, count in self.excluded_artifact_counts:
            if not reason:
                raise GcsimOptimizerReducedOracleError(
                    "excluded artifact reason must not be empty"
                )
            _require_non_negative_int(count, "excluded artifact count")
        for _slot, count in self.offpiece_build_counts:
            _require_non_negative_int(count, "offpiece build count")
        for shape, count in self.package_shape_build_counts:
            if not shape:
                raise GcsimOptimizerReducedOracleError(
                    "package shape must not be empty"
                )
            _require_non_negative_int(count, "package shape count")
        if (
            self.package_shape_build_counts
            and sum(
                count
                for _shape, count in self.package_shape_build_counts
            )
            != self.legal_build_count
        ):
            raise GcsimOptimizerReducedOracleError(
                "package shape coverage differs from legal builds"
            )
        if (
            self.five_piece_build_count
            + sum(count for _slot, count in self.offpiece_build_counts)
            != self.legal_build_count
        ):
            raise GcsimOptimizerReducedOracleError(
                "wearer legal-build shape coverage is incoherent"
            )
        expected_raw_count = prod(
            len(artifact_ids)
            for _slot, artifact_ids in self.eligible_artifact_ids_by_slot
        )
        if expected_raw_count != self.raw_cartesian_assignment_count:
            raise GcsimOptimizerReducedOracleError(
                "wearer raw Cartesian coverage is incoherent"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "wearer": self.wearer.to_dict(),
            "eligible_artifact_ids_by_slot": {
                slot: list(artifact_ids)
                for slot, artifact_ids in self.eligible_artifact_ids_by_slot
            },
            "excluded_artifacts": [
                {"artifact_id": artifact_id, "reason": reason}
                for artifact_id, reason in self.excluded_artifacts
            ],
            "excluded_artifact_counts": dict(self.excluded_artifact_counts),
            "raw_cartesian_assignment_count": (
                self.raw_cartesian_assignment_count
            ),
            "legal_build_count": self.legal_build_count,
            "five_piece_build_count": self.five_piece_build_count,
            "offpiece_build_counts": dict(self.offpiece_build_counts),
            "package_shape_build_counts": dict(
                self.package_shape_build_counts
            ),
            "materialization_rejection_count": (
                self.materialization_rejection_count
            ),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAccountOracleCoverage:
    wearer_coverage: tuple[GcsimOptimizerAccountOracleWearerCoverage, ...]
    joint_cartesian_state_count: int
    joint_conflict_count: int
    joint_disjoint_assignment_count: int
    compiled_rejection_count: int
    unique_simulation_count: int
    equivalent_assignment_count: int
    schema_version: int = (
        GCSIM_OPTIMIZER_ACCOUNT_FOUR_PIECE_ORACLE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_ACCOUNT_FOUR_PIECE_ORACLE_SCHEMA_VERSION
        ):
            raise GcsimOptimizerReducedOracleError(
                "unsupported account oracle aggregate schema"
            )
        wearer_coverage = tuple(self.wearer_coverage)
        if tuple(item.wearer.team_slot for item in wearer_coverage) != (
            1,
            2,
            3,
            4,
        ):
            raise GcsimOptimizerReducedOracleError(
                "account oracle coverage requires four canonical wearers"
            )
        object.__setattr__(self, "wearer_coverage", wearer_coverage)
        for field_name in (
            "joint_cartesian_state_count",
            "joint_conflict_count",
            "joint_disjoint_assignment_count",
            "compiled_rejection_count",
            "unique_simulation_count",
            "equivalent_assignment_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        if (
            self.joint_conflict_count
            + self.joint_disjoint_assignment_count
            != self.joint_cartesian_state_count
        ):
            raise GcsimOptimizerReducedOracleError(
                "joint account oracle coverage is incoherent"
            )
        expected_joint_count = prod(
            item.legal_build_count for item in wearer_coverage
        )
        if expected_joint_count != self.joint_cartesian_state_count:
            raise GcsimOptimizerReducedOracleError(
                "joint Cartesian coverage differs from wearer domains"
            )
        compiled_count = (
            self.joint_disjoint_assignment_count
            - self.compiled_rejection_count
        )
        if compiled_count < 0 or (
            self.unique_simulation_count + self.equivalent_assignment_count
            != compiled_count
        ):
            raise GcsimOptimizerReducedOracleError(
                "compiled/equivalent account oracle coverage is incoherent"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "wearer_coverage": [
                item.to_dict() for item in self.wearer_coverage
            ],
            "joint_cartesian_state_count": self.joint_cartesian_state_count,
            "joint_conflict_count": self.joint_conflict_count,
            "joint_disjoint_assignment_count": (
                self.joint_disjoint_assignment_count
            ),
            "compiled_rejection_count": self.compiled_rejection_count,
            "unique_simulation_count": self.unique_simulation_count,
            "equivalent_assignment_count": self.equivalent_assignment_count,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAccountOracleEvaluation:
    first_joint_ordinal: int
    candidate: GcsimOptimizerCompiledTeamCandidate
    score: GcsimOptimizerOracleScore
    witness_bucket: GcsimOptimizerSimulationWitnessBucket
    schema_version: int = (
        GCSIM_OPTIMIZER_ACCOUNT_FOUR_PIECE_ORACLE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_ACCOUNT_FOUR_PIECE_ORACLE_SCHEMA_VERSION
        ):
            raise GcsimOptimizerReducedOracleError(
                "unsupported account oracle evaluation schema"
            )
        if (
            isinstance(self.first_joint_ordinal, bool)
            or not isinstance(self.first_joint_ordinal, int)
            or self.first_joint_ordinal <= 0
        ):
            raise GcsimOptimizerReducedOracleError(
                "first_joint_ordinal must be positive"
            )
        if not isinstance(
            self.candidate,
            GcsimOptimizerCompiledTeamCandidate,
        ):
            raise GcsimOptimizerReducedOracleError(
                "candidate must be a compiled team candidate"
            )
        if not isinstance(self.score, GcsimOptimizerOracleScore):
            raise GcsimOptimizerReducedOracleError(
                "score must be a typed oracle score"
            )
        if (
            self.witness_bucket.simulation_sha256
            != self.candidate.simulation_sha256
        ):
            raise GcsimOptimizerReducedOracleError(
                "witness bucket belongs to another simulation"
            )

    @property
    def candidate_identity_sha256(self) -> str:
        return self.candidate.simulation_sha256

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "first_joint_ordinal": self.first_joint_ordinal,
            "candidate": self.candidate.to_dict(),
            "score": self.score.to_dict(),
            "witness_bucket": self.witness_bucket.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerAccountFourPieceOracleResult:
    run_input_sha256: str
    targets: tuple[GcsimOptimizerWearerTarget, ...]
    execution_identity_sha256: str
    limits: GcsimOptimizerReducedOracleLimits
    coverage: GcsimOptimizerAccountOracleCoverage
    evaluations: tuple[GcsimOptimizerAccountOracleEvaluation, ...]
    winner: GcsimOptimizerAccountOracleEvaluation
    schema_version: int = (
        GCSIM_OPTIMIZER_ACCOUNT_FOUR_PIECE_ORACLE_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != GCSIM_OPTIMIZER_ACCOUNT_FOUR_PIECE_ORACLE_SCHEMA_VERSION
        ):
            raise GcsimOptimizerReducedOracleError(
                "unsupported account oracle result schema"
            )
        _require_sha256(self.run_input_sha256, "run_input_sha256")
        _require_sha256(
            self.execution_identity_sha256,
            "execution_identity_sha256",
        )
        targets = tuple(self.targets)
        if (
            len(targets) != 4
            or tuple(item.wearer.team_slot for item in targets)
            != (1, 2, 3, 4)
        ):
            raise GcsimOptimizerReducedOracleError(
                "account oracle result requires four canonical targets"
            )
        evaluations = tuple(self.evaluations)
        if not evaluations:
            raise GcsimOptimizerReducedOracleError(
                "account oracle result requires successful evaluations"
            )
        if self.winner not in evaluations:
            raise GcsimOptimizerReducedOracleError(
                "account oracle winner must belong to evaluations"
            )
        if self.coverage.unique_simulation_count != len(evaluations):
            raise GcsimOptimizerReducedOracleError(
                "account oracle evaluation count differs from coverage"
            )
        object.__setattr__(self, "targets", targets)
        object.__setattr__(self, "evaluations", evaluations)

    @property
    def winner_candidate_sha256(self) -> str:
        return self.winner.candidate_identity_sha256

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_input_sha256": self.run_input_sha256,
            "targets": [item.to_dict() for item in self.targets],
            "execution_identity_sha256": self.execution_identity_sha256,
            "limits": self.limits.to_dict(),
            "coverage": self.coverage.to_dict(),
            "evaluations": [item.to_dict() for item in self.evaluations],
            "winner_candidate_sha256": self.winner_candidate_sha256,
        }


def run_gcsim_optimizer_account_four_piece_oracle(
    run_input: GcsimOptimizerRunInput,
    *,
    targets: Sequence[GcsimOptimizerWearerTarget],
    execution_identity_sha256: str,
    evaluator: AccountOracleEvaluator,
    limits: GcsimOptimizerReducedOracleLimits | None = None,
) -> GcsimOptimizerAccountFourPieceOracleResult:
    """Exhaustively evaluate a deliberately reduced real-account domain.

    The historical function name remains compatible with Milestone 3A; each
    wearer target may now be either a complete 4p package or a canonical
    distinct-set 2p+2p package.
    """

    if not isinstance(run_input, GcsimOptimizerRunInput):
        raise GcsimOptimizerReducedOracleError("run_input must be typed")
    if (
        run_input.request.operation
        is not GcsimOptimizerOperation.ACCOUNT_ARTIFACTS
    ):
        raise GcsimOptimizerReducedOracleError(
            "account oracle requires an account-artifacts request"
        )
    _require_sha256(
        execution_identity_sha256,
        "execution_identity_sha256",
    )
    if not callable(evaluator):
        raise GcsimOptimizerReducedOracleError("evaluator must be callable")
    oracle_limits = limits or GcsimOptimizerReducedOracleLimits()
    if not isinstance(oracle_limits, GcsimOptimizerReducedOracleLimits):
        raise GcsimOptimizerReducedOracleError("limits must be typed")
    target_rows = tuple(targets)
    expected_wearers = run_input.request.source_simulation.wearers
    if (
        len(target_rows) != 4
        or tuple(item.wearer for item in target_rows) != expected_wearers
        or any(
            not isinstance(
                item.package,
                (
                    GcsimFourPieceTargetPackage,
                    GcsimTwoPlusTwoTargetPackage,
                ),
            )
            for item in target_rows
        )
    ):
        raise GcsimOptimizerReducedOracleError(
            "account package oracle targets must cover the frozen team in order"
        )

    wearer_builds: list[tuple[GcsimOptimizerMaterializedBuild, ...]] = []
    wearer_coverages: list[GcsimOptimizerAccountOracleWearerCoverage] = []
    for target in target_rows:
        builds, coverage = _enumerate_wearer_builds(
            run_input,
            target=target,
            limits=oracle_limits,
        )
        if not builds:
            raise GcsimOptimizerReducedOracleError(
                "reduced account oracle has no legal build for "
                f"{target.wearer.gcsim_character_key}"
            )
        wearer_builds.append(builds)
        wearer_coverages.append(coverage)

    joint_cartesian_count = prod(len(items) for items in wearer_builds)
    if joint_cartesian_count > oracle_limits.max_joint_cartesian_states:
        raise GcsimOptimizerReducedOracleError(
            "reduced account oracle joint domain exceeds "
            "max_joint_cartesian_states"
        )

    evaluations: list[GcsimOptimizerAccountOracleEvaluation] = []
    evaluation_index_by_simulation: dict[str, int] = {}
    conflict_count = 0
    disjoint_count = 0
    compiled_rejection_count = 0
    objective_name = ""
    for joint_ordinal, build_rows in enumerate(
        product(*wearer_builds),
        start=1,
    ):
        artifact_ids = tuple(
            artifact_id
            for build in build_rows
            for artifact_id in build.assignment.artifact_ids
        )
        if len(set(artifact_ids)) != len(artifact_ids):
            conflict_count += 1
            continue
        disjoint_count += 1
        witness = GcsimOptimizerAccountAssignmentWitness(
            request_sha256=run_input.request.request_sha256,
            artifact_database_input_sha256=(
                run_input.artifact_database.artifact_database_input_sha256
            ),
            wearer_assignments=tuple(
                build.assignment for build in build_rows
            ),
        )
        compiled = compile_gcsim_optimizer_team_candidate(
            run_input,
            assignment_witness=witness,
            targets=target_rows,
            execution_identity_sha256=execution_identity_sha256,
        )
        if not compiled.ready or compiled.candidate is None:
            compiled_rejection_count += 1
            continue
        candidate = compiled.candidate
        existing_index = evaluation_index_by_simulation.get(
            candidate.simulation_sha256
        )
        if existing_index is not None:
            existing = evaluations[existing_index]
            bucket = add_gcsim_optimizer_simulation_witness(
                existing.witness_bucket,
                candidate,
                max_stored_witnesses=(
                    oracle_limits.max_stored_replacement_witnesses
                ),
            )
            evaluations[existing_index] = (
                GcsimOptimizerAccountOracleEvaluation(
                    first_joint_ordinal=existing.first_joint_ordinal,
                    candidate=existing.candidate,
                    score=existing.score,
                    witness_bucket=bucket,
                )
            )
            continue
        try:
            score = evaluator(candidate)
        except Exception as exc:
            raise GcsimOptimizerReducedOracleError(
                "account oracle evaluator failed at joint ordinal "
                f"{joint_ordinal}: {exc}"
            ) from exc
        if not isinstance(score, GcsimOptimizerOracleScore):
            raise GcsimOptimizerReducedOracleError(
                "account oracle evaluator must return GcsimOptimizerOracleScore"
            )
        if objective_name and score.objective_name != objective_name:
            raise GcsimOptimizerReducedOracleError(
                "account oracle evaluations must share one objective"
            )
        objective_name = score.objective_name
        bucket = add_gcsim_optimizer_simulation_witness(
            None,
            candidate,
            max_stored_witnesses=(
                oracle_limits.max_stored_replacement_witnesses
            ),
        )
        evaluation_index_by_simulation[candidate.simulation_sha256] = len(
            evaluations
        )
        evaluations.append(
            GcsimOptimizerAccountOracleEvaluation(
                first_joint_ordinal=joint_ordinal,
                candidate=candidate,
                score=score,
                witness_bucket=bucket,
            )
        )

    if not evaluations:
        raise GcsimOptimizerReducedOracleError(
            "reduced account oracle produced no evaluable disjoint assignment"
        )
    evaluation_rows = tuple(evaluations)
    equivalent_count = sum(
        item.witness_bucket.observed_assignment_count - 1
        for item in evaluation_rows
    )
    coverage = GcsimOptimizerAccountOracleCoverage(
        wearer_coverage=tuple(wearer_coverages),
        joint_cartesian_state_count=joint_cartesian_count,
        joint_conflict_count=conflict_count,
        joint_disjoint_assignment_count=disjoint_count,
        compiled_rejection_count=compiled_rejection_count,
        unique_simulation_count=len(evaluation_rows),
        equivalent_assignment_count=equivalent_count,
    )
    winner = min(
        evaluation_rows,
        key=lambda item: (
            -item.score.objective_value,
            item.candidate_identity_sha256,
        ),
    )
    return GcsimOptimizerAccountFourPieceOracleResult(
        run_input_sha256=run_input.run_input_sha256,
        targets=target_rows,
        execution_identity_sha256=execution_identity_sha256,
        limits=oracle_limits,
        coverage=coverage,
        evaluations=evaluation_rows,
        winner=winner,
    )


def _enumerate_wearer_builds(
    run_input: GcsimOptimizerRunInput,
    *,
    target: GcsimOptimizerWearerTarget,
    limits: GcsimOptimizerReducedOracleLimits,
) -> tuple[
    tuple[GcsimOptimizerMaterializedBuild, ...],
    GcsimOptimizerAccountOracleWearerCoverage,
]:
    package = target.package
    if not isinstance(
        package,
        (
            GcsimFourPieceTargetPackage,
            GcsimTwoPlusTwoTargetPackage,
        ),
    ):
        raise GcsimOptimizerReducedOracleError(
            "account oracle received an incomplete package target"
        )
    package_uids = (
        (package.set_ref.set_uid,)
        if isinstance(package, GcsimFourPieceTargetPackage)
        else (
            package.set_a.set_uid,
            package.set_b.set_uid,
        )
    )
    override = next(
        (
            item
            for item in run_input.request.four_star_overrides
            if item.wearer == target.wearer
        ),
        None,
    )
    slot_rows: dict[str, list[GcsimOptimizerArtifactRecord]] = {
        slot: [] for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
    }
    excluded = Counter()
    excluded_artifacts: list[tuple[int, str]] = []
    for artifact in run_input.artifact_database.artifacts:
        eligibility = evaluate_gcsim_optimizer_artifact_eligibility(
            artifact,
            wearer=target.wearer,
            four_star_override=override,
            package_set_uids=package_uids,
        )
        if not eligibility.eligible:
            excluded[eligibility.reason] += 1
            excluded_artifacts.append(
                (artifact.artifact_id, eligibility.reason)
            )
            continue
        if artifact.position_key not in slot_rows:
            excluded["artifact_slot_invalid"] += 1
            excluded_artifacts.append(
                (artifact.artifact_id, "artifact_slot_invalid")
            )
            continue
        slot_rows[artifact.position_key].append(artifact)
    for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS:
        slot_rows[slot].sort(key=lambda item: item.artifact_id)
        if len(slot_rows[slot]) > limits.max_artifacts_per_slot:
            raise GcsimOptimizerReducedOracleError(
                "reduced account oracle slot pool exceeds "
                f"max_artifacts_per_slot for {target.wearer.gcsim_character_key}."
                f"{slot}"
            )
    raw_count = prod(
        len(slot_rows[slot]) for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
    )
    if raw_count > limits.max_cartesian_builds_per_wearer:
        raise GcsimOptimizerReducedOracleError(
            "reduced account oracle wearer domain exceeds "
            "max_cartesian_builds_per_wearer"
        )

    builds: list[GcsimOptimizerMaterializedBuild] = []
    five_piece_count = 0
    offpiece_counts = Counter()
    package_shape_counts = Counter()
    rejection_count = 0
    pools = tuple(
        slot_rows[slot] for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
    )
    for artifacts in product(*pools):
        counts = Counter(artifact.set_uid for artifact in artifacts)
        if isinstance(package, GcsimFourPieceTargetPackage):
            target_count = counts[package.set_ref.set_uid]
            if target_count < 4:
                continue
        else:
            count_a = counts[package.set_a.set_uid]
            count_b = counts[package.set_b.set_uid]
            if count_a < 2 or count_b < 2:
                continue
        assignment = GcsimOptimizerWearerArtifactAssignment(
            wearer=target.wearer,
            artifact_ids_by_slot={
                slot: artifact.artifact_id
                for slot, artifact in zip(
                    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
                    artifacts,
                    strict=True,
                )
            },
        )
        materialized = materialize_gcsim_optimizer_wearer_build(
            run_input,
            assignment=assignment,
            target=target,
        )
        if not materialized.ready or materialized.build is None:
            rejection_count += 1
            continue
        builds.append(materialized.build)
        if isinstance(package, GcsimFourPieceTargetPackage):
            package_shape_counts[
                "5p" if target_count == 5 else "4p+1"
            ] += 1
            if target_count == 5:
                five_piece_count += 1
            else:
                offpiece_slot = next(
                    slot
                    for slot, artifact in zip(
                        GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
                        artifacts,
                        strict=True,
                    )
                    if artifact.set_uid != package.set_ref.set_uid
                )
                offpiece_counts[offpiece_slot] += 1
        else:
            count_a = counts[package.set_a.set_uid]
            count_b = counts[package.set_b.set_uid]
            package_shape_counts[
                "2+2+1"
                if count_a == 2 and count_b == 2
                else "3+2"
            ] += 1
            free_slot = _pair_free_slot(
                artifacts,
                package=package,
            )
            offpiece_counts[free_slot] += 1
        if len(builds) > limits.max_legal_builds_per_wearer:
            raise GcsimOptimizerReducedOracleError(
                "reduced account oracle legal build domain exceeds "
                "max_legal_builds_per_wearer"
            )
    builds.sort(key=lambda item: item.assignment.artifact_ids)
    coverage = GcsimOptimizerAccountOracleWearerCoverage(
        wearer=target.wearer,
        eligible_artifact_ids_by_slot=tuple(
            (
                slot,
                tuple(item.artifact_id for item in slot_rows[slot]),
            )
            for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
        ),
        excluded_artifacts=tuple(excluded_artifacts),
        excluded_artifact_counts=tuple(sorted(excluded.items())),
        raw_cartesian_assignment_count=raw_count,
        legal_build_count=len(builds),
        five_piece_build_count=five_piece_count,
        offpiece_build_counts=tuple(
            (slot, offpiece_counts[slot])
            for slot in GCSIM_OPTIMIZER_ARTIFACT_SLOTS
        ),
        package_shape_build_counts=tuple(
            sorted(package_shape_counts.items())
        ),
        materialization_rejection_count=rejection_count,
    )
    return tuple(builds), coverage


def _pair_free_slot(artifacts, *, package):
    remaining = {
        package.set_a.set_uid: 2,
        package.set_b.set_uid: 2,
    }
    free_slot = None
    for slot, artifact in zip(
        GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
        artifacts,
        strict=True,
    ):
        required = remaining.get(artifact.set_uid, 0)
        if required:
            remaining[artifact.set_uid] = required - 1
        elif free_slot is None:
            free_slot = slot
    if free_slot is None or any(remaining.values()):
        raise GcsimOptimizerReducedOracleError(
            "2p+2p build does not have one deterministic free slot"
        )
    return free_slot


run_gcsim_optimizer_account_package_oracle = (
    run_gcsim_optimizer_account_four_piece_oracle
)
GcsimOptimizerAccountPackageOracleResult = (
    GcsimOptimizerAccountFourPieceOracleResult
)


def _require_non_negative_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GcsimOptimizerReducedOracleError(
            f"{field_name} must be a non-negative integer"
        )


def _require_sha256(value: object, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise GcsimOptimizerReducedOracleError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


__all__ = [
    "GCSIM_OPTIMIZER_ACCOUNT_FOUR_PIECE_ORACLE_SCHEMA_VERSION",
    "GCSIM_OPTIMIZER_ACCOUNT_PACKAGE_ORACLE_SCHEMA_VERSION",
    "AccountOracleEvaluator",
    "GcsimOptimizerAccountFourPieceOracleResult",
    "GcsimOptimizerAccountPackageOracleResult",
    "GcsimOptimizerAccountOracleCoverage",
    "GcsimOptimizerAccountOracleEvaluation",
    "GcsimOptimizerAccountOracleWearerCoverage",
    "run_gcsim_optimizer_account_four_piece_oracle",
    "run_gcsim_optimizer_account_package_oracle",
]
