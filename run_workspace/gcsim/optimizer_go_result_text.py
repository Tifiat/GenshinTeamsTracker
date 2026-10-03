"""Human-readable result text, separate from transport and search."""

from __future__ import annotations

from typing import Any, Mapping
from .optimizer_rotation_policy import ROTATION_AUTO_BOUNDED_WARNING


def format_gcsim_optimizer_go_selected_result(payload: Mapping[str, Any]) -> str:
    from localization import tr
    all_sets = payload.get("mode") == "all_sets"
    if not payload.get("success"):
        title = "Selected Sets cancelled" if payload.get("status") == "cancelled" else "Selected Sets failed"
        if all_sets:
            title = tr("gcsim.optimizer.all_cancelled" if payload.get("status") == "cancelled" else "gcsim.optimizer.all_failed")
        if payload.get("error_code") == "finish_no_result":
            title = tr("gcsim.optimizer.finish_no_result_title")
        error_key = {
            "finish_no_result": "gcsim.optimizer.finish_no_result",
            "rotation_unbounded_dummy_target": (
                "gcsim.optimizer.rotation_unbounded_dummy_target"
            ),
        }.get(str(payload.get("error_code") or ""))
        reason = tr(error_key) if error_key else str(payload.get("error") or "-")
        return "\n".join(
            (
                title,
                tr("gcsim.optimizer.reason").format(reason=reason),
                f"Debug: {payload.get('run_dir') or '-'}",
            )
        )
    result = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
    measured = result.get("measured") if isinstance(result.get("measured"), Mapping) else {}
    assignments: dict[str, list[str]] = {}
    for row in result.get("winner") or ():
        assignments.setdefault(str(row.get("wearer_key") or "?"), []).append(
            f"{row.get('slot')}={row.get('artifact_id')}"
        )
    formula_only = result.get("ranking_basis", "gcsim") == "formula"
    lines = [tr("gcsim.optimizer.all_completed") if all_sets else "Selected Sets complete"]
    if formula_only:
        lines.append(f"Formula-only estimate: {result.get('formula_dps') or '-'}")
    else:
        lines.extend(
            (
                f"Final DPS: {measured.get('dps') or '-'}",
                f"Standard error: {measured.get('standard_error') or '-'}",
                f"Formula estimate: {result.get('formula_dps') or '-'}",
                f"Formula residual: {result.get('formula_residual') or '-'}",
            )
        )
    for wearer in sorted(assignments):
        lines.append(f"{wearer}: " + ", ".join(assignments[wearer]))
    energy = result.get("energy") if isinstance(result.get("energy"), Mapping) else None
    if energy is not None:
        lines.append(tr("gcsim.optimizer.energy_result_title"))
        for wearer in energy.get("wearers") or ():
            actual = float(wearer.get("artifact_er") or 0) * 100
            required = float(wearer.get("required_artifact_er") or 0) * 100
            margin = float(wearer.get("artifact_er_margin") or 0) * 100
            lines.append(
                tr("gcsim.optimizer.energy_result_row").format(
                    wearer=wearer.get("wearer_key") or "?",
                    actual=f"{actual:.1f}",
                    required=f"{required:.1f}",
                    margin=f"{margin:+.1f}",
                )
            )
    warnings = tuple(result.get("warnings") or ()) + tuple(
        payload.get("adapter_warnings") or ()
    )
    if formula_only:
        warnings = (
            "Formula-only ranking; no measured GCSIM DPS or standard error is available.",
            *warnings,
        )
    if warnings:
        lines.append(
            "Warnings: " + ", ".join(format_optimizer_warning(value) for value in warnings)
        )
    lines.append(f"Debug: {result.get('debug_receipt_path') or payload.get('run_dir') or '-'}")
    return "\n".join(lines)


def format_optimizer_warning(value: Any) -> str:
    from localization import tr

    code = str(value.get("code") or "") if isinstance(value, Mapping) else str(value)
    if code == ROTATION_AUTO_BOUNDED_WARNING:
        raw_duration = value.get("duration_seconds") if isinstance(value, Mapping) else 90
        try:
            duration = f"{float(raw_duration):g}"
        except (TypeError, ValueError):
            duration = "90"
        return tr("gcsim.optimizer.rotation_auto_bounded").format(
            duration=duration
        )
    return str(value)
