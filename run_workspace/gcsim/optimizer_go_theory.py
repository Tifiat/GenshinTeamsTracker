"""Theory/farming-guidance adapter over the standalone Go optimizer.

The request preparation and verified set-source bundle are shared with All
Sets. Go returns theoretical main stats and roll allocation, never owned IDs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .optimizer_go_all import (
    GcsimOptimizerGoAllSetsRequest,
    GcsimOptimizerGoAllSetsSession,
    all_sets_available,
)
from .selected_team_config import VIRTUAL_ARTIFACT_POLICY_THEORY_BASELINE
from .optimizer_go_requests import GcsimOptimizerGoError


GCSIM_OPTIMIZER_GO_THEORY_RESULT_KIND = "gtt_gcsim_optimizer_theory_result_v1"


@dataclass(frozen=True, slots=True)
class GcsimOptimizerGoTheoryRequest(GcsimOptimizerGoAllSetsRequest):
    product_timeout_ms: int = 360_000


class GcsimOptimizerGoTheorySession(GcsimOptimizerGoAllSetsSession):
    run_mode = "theory"
    result_schema_kind = GCSIM_OPTIMIZER_GO_THEORY_RESULT_KIND
    result_filename = "theory-result.json"
    mode_label = "Theory"
    virtual_artifact_policy = VIRTUAL_ARTIFACT_POLICY_THEORY_BASELINE
    request_validation_mode = "validate-theory-request"

    def _prepare_formula_inputs(self, *, prepared, run_dir, started):
        if not self.request.infinite_energy_enabled:
            raise GcsimOptimizerGoError(
                "theory_finite_energy_unsupported",
                "Theory does not yet optimize energy requirements.",
            )
        return super()._prepare_formula_inputs(
            prepared=prepared, run_dir=run_dir, started=started
        )

    def _optimizer_command(self, binary, run_dir):
        return (
            str(binary),
            "optimize-theory",
            str(run_dir / "request.json"),
            str(run_dir / "set-sources.json"),
            str(run_dir / "theory"),
        )


def theory_available() -> bool:
    return all_sets_available()


__all__ = [
    "GCSIM_OPTIMIZER_GO_THEORY_RESULT_KIND",
    "GcsimOptimizerGoTheoryRequest",
    "GcsimOptimizerGoTheorySession",
    "theory_available",
]
