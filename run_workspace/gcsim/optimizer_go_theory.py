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
from .optimizer_go_selected import (
    GcsimOptimizerGoSelectedError,
    _format_optimizer_warning,
)


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
            raise GcsimOptimizerGoSelectedError(
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


def format_gcsim_optimizer_go_theory_result(payload: Mapping[str, Any]) -> str:
    from localization import tr

    if not payload.get("success"):
        cancelled = payload.get("status") == "cancelled"
        title = tr(
            "gcsim.optimizer.theory_cancelled"
            if cancelled
            else "gcsim.optimizer.theory_failed"
        )
        error_code = str(payload.get("error_code") or "")
        error_key = {
            "theory_profile_incomplete": "gcsim.optimizer.theory_profile_required",
            "theory_finite_energy_unsupported": (
                "gcsim.optimizer.theory_finite_energy_unsupported"
            ),
            "rotation_unbounded_dummy_target": (
                "gcsim.optimizer.rotation_unbounded_dummy_target"
            ),
        }.get(error_code)
        reason = tr(error_key) if error_key else str(payload.get("error") or "-")
        return "\n".join(
            (
                title,
                tr("gcsim.optimizer.reason").format(reason=reason),
                f"Debug: {payload.get('run_dir') or '-'}",
            )
        )
    result = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
    candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []
    coverage = result.get("coverage") if isinstance(result.get("coverage"), Mapping) else {}
    lines = [
        "Theory complete",
        "This is a farming target, not a build assembled from owned artifacts.",
        (
            "Coverage: {sets} sets, {packages} packages considered, "
            "{contexts} formula contexts checked."
        ).format(
            sets=coverage.get("catalog_sets", "-"),
            packages=coverage.get("packages_considered", "-"),
            contexts=coverage.get("contexts_evaluated", "-"),
        ),
    ]
    for candidate in candidates[:5]:
        if not isinstance(candidate, Mapping):
            continue
        lines.append("")
        lines.append(
            f"Top-{candidate.get('rank', '?')} · formula DPS {float(candidate.get('formula_dps') or 0):,.0f}"
        )
        packages = candidate.get("packages") if isinstance(candidate.get("packages"), list) else []
        allocations = candidate.get("allocations") if isinstance(candidate.get("allocations"), list) else []
        package_by_wearer = {
            str(row.get("wearer_key") or ""): row
            for row in packages
            if isinstance(row, Mapping)
        }
        for allocation in allocations:
            if not isinstance(allocation, Mapping):
                continue
            wearer = str(allocation.get("wearer_key") or "?")
            package = package_by_wearer.get(wearer, {})
            sets = package.get("sets") if isinstance(package.get("sets"), list) else []
            set_text = " + ".join(
                f"{row.get('set_uid')} {row.get('count')}p"
                for row in sets
                if isinstance(row, Mapping)
            ) or "-"
            mains = allocation.get("main_stats") if isinstance(allocation.get("main_stats"), Mapping) else {}
            main_text = "/".join(
                str(mains.get(slot) or "-") for slot in ("sands", "goblet", "circlet")
            )
            substats = allocation.get("substats") if isinstance(allocation.get("substats"), list) else []
            useful = ", ".join(
                f"{row.get('stat_key')}≈{float(row.get('roll_units') or 0):g} rolls"
                for row in substats
                if isinstance(row, Mapping) and float(row.get("roll_units") or 0) > 0
            ) or "any remaining stat"
            lines.append(f"{wearer}: {set_text}; mains {main_text}; {useful}")
        undistinguished = candidate.get("undistinguished_set_slots")
        if isinstance(undistinguished, list) and undistinguished:
            lines.append(
                tr("gcsim.optimizer.theory_undistinguished_slots").format(
                    wearers=", ".join(str(value) for value in undistinguished)
                )
            )
    warnings = tuple(result.get("warnings") or ()) + tuple(
        payload.get("adapter_warnings") or ()
    )
    if warnings:
        lines.extend(
            ("", "Warnings: " + ", ".join(_format_optimizer_warning(value) for value in warnings))
        )
    lines.append(f"Debug: {result.get('debug_receipt_path') or payload.get('run_dir') or '-'}")
    return "\n".join(lines)


__all__ = [
    "GCSIM_OPTIMIZER_GO_THEORY_RESULT_KIND",
    "GcsimOptimizerGoTheoryRequest",
    "GcsimOptimizerGoTheorySession",
    "format_gcsim_optimizer_go_theory_result",
    "theory_available",
]
