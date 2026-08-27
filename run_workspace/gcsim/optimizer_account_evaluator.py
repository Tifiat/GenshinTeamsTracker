"""Public exact account-candidate adapter for ordinary GCSIM evaluation.

This adapter deliberately does not reuse the legacy feedback-loop request
builder.  In particular, the legacy builder treats a real account off-piece
as the theoretical four-star-set off-piece variant and assumes every target
has ``package.set_ref``.  The functions here encode real 4p and 2p+2p account
packages without weakening the bound evaluator's provenance checks.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import Path

from .farming_evaluator import (
    CandidateKey,
    GcsimFarmingEvaluationRequest,
    prepare_bound_gcsim_farming_joint_evaluation,
)
from .farming_profile_config import apply_gcsim_screening_runtime_options
from .optimizer_config import GcsimFiveStarMainStatLayout
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_joint_proposals import GcsimOptimizerJointProposal
from .optimizer_main_response import gcsim_optimizer_main_layout_id
from .optimizer_product_contracts import (
    GcsimFourPieceTargetPackage,
    GcsimTwoPlusTwoTargetPackage,
)


GCSIM_OPTIMIZER_ACCOUNT_EVALUATOR_SCHEMA_VERSION = 1


class GcsimOptimizerAccountEvaluatorError(ValueError):
    """Fail-closed account evaluation adapter error."""


def build_gcsim_optimizer_account_candidate_keys(
    proposal: GcsimOptimizerJointProposal,
    *,
    engine_context: GcsimOptimizerEngineContext,
) -> tuple[tuple[CandidateKey, ...], tuple[str, ...]]:
    """Return bound evaluator keys and any canonical synthetic pair keys."""

    if not isinstance(proposal, GcsimOptimizerJointProposal):
        raise GcsimOptimizerAccountEvaluatorError(
            "proposal must be typed"
        )
    keys: list[CandidateKey] = []
    synthetic: set[str] = set()
    for candidate in proposal.wearer_candidates:
        main_by_slot = {
            item.artifact_slot: item.gcsim_key
            for item in candidate.materialized_build.stat_contributions
            if item.source_kind == "main"
        }
        try:
            layout = GcsimFiveStarMainStatLayout(
                sands=main_by_slot["sands"],
                goblet=main_by_slot["goblet"],
                circlet=main_by_slot["circlet"],
            )
        except KeyError as exc:
            raise GcsimOptimizerAccountEvaluatorError(
                "materialized account build has incomplete main stats"
            ) from exc
        package = candidate.target.package
        offpiece_slot = ""
        if isinstance(package, GcsimFourPieceTargetPackage):
            set_key = package.set_ref.gcsim_set_key
            capability = engine_context.catalog.get(set_key)
            if capability is None:
                raise GcsimOptimizerAccountEvaluatorError(
                    "account target set is absent from the bound catalog"
                )
            # This field is a theoretical 4-star package variant flag, not a
            # normal account off-piece.  It is empty for ordinary five-star
            # packages and only populated for an explicitly authorized 4-star
            # package accepted by the bound evaluator.
            if capability.max_rarity == 4:
                if candidate.offpiece_shape not in {
                    "flower",
                    "plume",
                    "sands",
                    "goblet",
                    "circlet",
                }:
                    raise GcsimOptimizerAccountEvaluatorError(
                        "four-star account target lacks an explicit "
                        "five-star offpiece"
                    )
                offpiece_slot = candidate.offpiece_shape
        elif isinstance(package, GcsimTwoPlusTwoTargetPackage):
            set_key = _synthetic_pair_key(
                package.set_a.gcsim_set_key,
                package.set_b.gcsim_set_key,
            )
            synthetic.add(set_key)
        else:  # pragma: no cover - target package union is closed.
            raise GcsimOptimizerAccountEvaluatorError(
                "unsupported account target package"
            )
        keys.append(
            (
                candidate.target.wearer.gcsim_character_key,
                set_key,
                gcsim_optimizer_main_layout_id(layout),
                offpiece_slot,
                candidate.materialized_build.compiled_block_sha256,
            )
        )
    return tuple(keys), tuple(sorted(synthetic))


def prepare_gcsim_optimizer_account_evaluation(
    proposal: GcsimOptimizerJointProposal,
    *,
    engine_context: GcsimOptimizerEngineContext,
    comparison_context_sha256: str,
    investment_signature: str,
    iterations: int,
    worker_count: int,
    timeout_seconds: float,
    environment: Mapping[str, str] | None = None,
    gtt_wave_scenario_path: str | Path | None = None,
    target_sha256: str = "",
) -> GcsimFarmingEvaluationRequest:
    """Bind one exact compiled account proposal at one fidelity tier."""

    candidate_keys, synthetic_set_keys = (
        build_gcsim_optimizer_account_candidate_keys(
            proposal,
            engine_context=engine_context,
        )
    )
    config = apply_gcsim_screening_runtime_options(
        proposal.compiled_candidate.config_text,
        iterations=iterations,
        workers=worker_count,
    )
    return prepare_bound_gcsim_farming_joint_evaluation(
        engine_context=engine_context,
        candidate_keys=candidate_keys,
        config_text=config,
        comparison_context_sha256=comparison_context_sha256,
        investment_signature=investment_signature,
        worker_count=worker_count,
        timeout_seconds=timeout_seconds,
        environment=environment,
        novelty_tags=proposal.diversity_labels,
        synthetic_set_keys=synthetic_set_keys,
        gtt_wave_scenario_path=gtt_wave_scenario_path,
        target_sha256=target_sha256,
    )


def _synthetic_pair_key(left: str, right: str) -> str:
    if left.casefold() == right.casefold():
        raise GcsimOptimizerAccountEvaluatorError(
            "2p+2p requires two distinct GCSIM set keys"
        )
    ordered = tuple(sorted((left, right)))
    digest = hashlib.sha256(
        ("\x00".join(ordered)).encode("utf-8")
    ).hexdigest()
    # Catalog set keys are alphanumeric.  Keep the same shape so the key is
    # safe in every existing candidate identity while remaining impossible to
    # confuse with an engine-owned real set.
    return f"gttpair{digest[:24]}"


__all__ = [
    "GCSIM_OPTIMIZER_ACCOUNT_EVALUATOR_SCHEMA_VERSION",
    "GcsimOptimizerAccountEvaluatorError",
    "build_gcsim_optimizer_account_candidate_keys",
    "prepare_gcsim_optimizer_account_evaluation",
]
