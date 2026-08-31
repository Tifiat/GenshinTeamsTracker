"""Validate the clean GOB-7 staged common-context acceptance receipt.

This audit starts no engine and performs no search. It validates the ignored
product-run receipt, binds it to the frozen real request and migration leader,
and retains only a compact non-private acceptance summary.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from run_workspace.gcsim.optimizer_go_contracts import canonical_sha256
from tools.experiments.gcsim_optimizer_go_gob4_audit import REQUEST_PATH, ROOT


RUN_RECEIPT_PATH = ROOT / ".codex_tmp" / "gob7-staged-20260830" / "gob7-result.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "gcsim_optimizer_go_v1"
REFERENCE_PATH = FIXTURE_DIR / "gob5_python_reference_v1.json"
RECEIPT_PATH = FIXTURE_DIR / "gob7_common_n1000_acceptance_receipt_v1.json"
PRODUCT_BOUNDARY_MS = 190_000.0


def main() -> None:
    request = json.loads(REQUEST_PATH.read_text(encoding="utf-8"))
    result = json.loads(RUN_RECEIPT_PATH.read_text(encoding="utf-8"))
    reference = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    search = result["search"]
    screen = result["screening"]
    final = result["verification"]
    wearer_keys = [row["wearer_key"] for row in request["wearers"]]
    reference_assignment = [reference["assignments"][key] for key in wearer_keys]
    current_assignment = search["initial"]["assignment"]
    formula_leader_assignment = search["leader"]["assignment"]
    screen_assignments = [row["assignment"] for row in screen["candidates"]]
    final_assignments = [row["assignment"] for row in final["candidates"]]
    winner = final["winner"]
    measured_order = sorted(
        final["candidates"], key=lambda row: (-row["measured_dps"], row["assignment_sha256"])
    )
    runner_up = measured_order[1]
    combined_top_se = math.hypot(winner["standard_error"], runner_up["standard_error"])
    current = next(row for row in final["candidates"] if row["assignment"] == current_assignment)
    winner_ids = [value for wearer in winner["assignment"] for value in wearer]
    engine_path = Path(request["engine"]["binary_path"])
    engine_sha256 = hashlib.sha256(engine_path.read_bytes()).hexdigest()
    checks = {
        "all_mode": result["mode"] == "all",
        "formula_pool_is_frozen_24": len(search["finalists"]) == 24,
        "screen_is_current_plus_24": len(screen["candidates"]) == 25,
        "screen_is_common_n128": screen["iterations"] == 128,
        "screen_cpu_partition_is_4x4": (
            screen["parallelism"] == 4 and screen["workers"] == 4
        ),
        "final_count_is_bounded": 1 <= len(final["candidates"]) <= 7,
        "final_is_common_n1000": final["iterations"] == 1000,
        "final_cpu_partition_is_3x5": (
            final["parallelism"] == 3 and final["workers"] == 5
        ),
        "known_rank24_reference_survives_screen": reference_assignment in screen_assignments,
        "known_rank24_reference_survives_final": reference_assignment in final_assignments,
        "known_rank24_reference_is_measured_winner": winner["assignment"] == reference_assignment,
        "formula_leader_is_mandatory_finalist": formula_leader_assignment in final_assignments,
        "current_is_mandatory_finalist": current_assignment in final_assignments,
        "winner_has_exact_twenty_unique_ids": len(winner_ids) == 20 and len(set(winner_ids)) == 20,
        "winner_improves_same_context_current": winner["measured_dps"] > current["measured_dps"],
        "winner_has_finite_positive_se": 0 < winner["standard_error"] < winner["measured_dps"],
        "top_two_overlap_is_reportable_not_hidden": (
            winner["measured_dps"] - runner_up["measured_dps"]
            <= 1.96 * combined_top_se
        ),
        "cold_product_runtime_below_190_seconds": result["total_elapsed_ms"] < PRODUCT_BOUNDARY_MS,
        "bound_engine_identity_unchanged": engine_sha256 == request["engine"]["artifact_sha256"],
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"GOB-7 acceptance failed: {failed!r}")
    improvement = winner["measured_dps"] - current["measured_dps"]
    receipt = {
        "schema_version": 1,
        "schema_kind": "gtt_optimizer_gob7_common_n1000_acceptance_receipt_v1",
        "status": "PASS",
        "checks": checks,
        "request_sha256": canonical_sha256(request),
        "engine_artifact_sha256": engine_sha256,
        "product_run": {
            "formula_pool": len(search["finalists"]),
            "screen_iterations": screen["iterations"],
            "screen_candidates": len(screen["candidates"]),
            "screen_processes": len(screen["candidates"]),
            "final_iterations": final["iterations"],
            "final_candidates": len(final["candidates"]),
            "final_processes": len(final["candidates"]),
            "search_seconds": result["search_elapsed_ms"] / 1000.0,
            "screen_seconds": screen["total_elapsed_ms"] / 1000.0,
            "final_seconds": final["total_elapsed_ms"] / 1000.0,
            "total_seconds": result["total_elapsed_ms"] / 1000.0,
            "product_boundary_seconds": PRODUCT_BOUNDARY_MS / 1000.0,
        },
        "winner": {
            "formula_rank": next(
                index + 1
                for index, row in enumerate(search["finalists"])
                if row["assignment"] == winner["assignment"]
            ),
            "formula_dps": winner["formula_dps"],
            "measured_dps": winner["measured_dps"],
            "standard_error": winner["standard_error"],
            "formula_residual_dps": winner["formula_residual_dps"],
            "assignment": dict(zip(wearer_keys, winner["assignment"], strict=True)),
            "assignment_sha256": winner["assignment_sha256"],
            "config_sha256": winner["config_sha256"],
            "engine_result_sha256": winner["engine_result_sha256"],
        },
        "current": {
            "measured_dps": current["measured_dps"],
            "standard_error": current["standard_error"],
            "assignment_sha256": current["assignment_sha256"],
        },
        "runner_up": {
            "measured_dps": runner_up["measured_dps"],
            "standard_error": runner_up["standard_error"],
            "assignment_sha256": runner_up["assignment_sha256"],
            "winner_gap_dps": winner["measured_dps"] - runner_up["measured_dps"],
            "winner_gap_combined_se": combined_top_se,
        },
        "improvement": {
            "dps": improvement,
            "percent": 100.0 * improvement / current["measured_dps"],
        },
        "engine_executions_in_accepted_product_run": len(screen["candidates"]) + len(final["candidates"]),
        "n1000_executions_in_accepted_product_run": len(final["candidates"]),
        "ui_calls": 0,
        "first_loss": None,
        "interpretation": (
            "The 24-row formula pool cannot be truncated by formula rank: the retained "
            "rank-24 migration leader won common n=1000. A common n=128 screen retained "
            "it, then at most seven mandatory/measured finalists received common n=1000. "
            "The accepted clean attempt finished below 190 seconds and returns exact IDs."
        ),
        "next_stage": "GOB-8_Selected_UI_and_clean_new_user_acceptance",
    }
    RECEIPT_PATH.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
