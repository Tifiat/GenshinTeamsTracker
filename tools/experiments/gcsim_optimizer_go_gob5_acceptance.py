"""GOB-5 real-account acceptance without GCSIM execution.

Runs the clean Go FGBS once against the frozen two-member compact panel, then
independently rescales the retained Python migration leader through the same IR.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

from tools.experiments.gcsim_optimizer_go_gob4_audit import (
    COMPACT_PATH,
    REQUEST_PATH,
    ROOT,
    _assignment_deltas,
    _evaluate_panel,
)


AUDIT_DIR = ROOT / ".codex_tmp" / "gob3e_real_panel"
BINARY_PATH = AUDIT_DIR / "gtt-optimizer-gob5.exe"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "gcsim_optimizer_go_v1"
REFERENCE_PATH = FIXTURE_DIR / "gob5_python_reference_v1.json"
RECEIPT_PATH = FIXTURE_DIR / "gob5_real_account_acceptance_receipt_v1.json"
PRODUCT_BOUNDARY_SECONDS = 190.0


def main() -> None:
    request = json.loads(REQUEST_PATH.read_text(encoding="utf-8"))
    compact = json.loads(COMPACT_PATH.read_text(encoding="utf-8"))
    reference = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    completed = subprocess.run(
        (str(BINARY_PATH), "search-fgbs", str(REQUEST_PATH), str(COMPACT_PATH)),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    go = json.loads(completed.stdout)
    result = go["result"]
    wearer_keys = [row["wearer_key"] for row in request["wearers"]]
    incumbent = [
        [row["artifact_id"] for row in wearer["current_artifacts"]]
        for wearer in request["wearers"]
    ]
    python_assignment = [
        reference["assignments"][wearer_key] for wearer_key in wearer_keys
    ]
    coordinates = sorted(
        {
            node["coordinate"]
            for member in compact["members"]
            for node in member["nodes"]
            if node["operation"] == "artifact_stat"
        }
    )
    python_leader_go_dps = _evaluate_panel(
        compact,
        coordinates,
        _assignment_deltas(request, coordinates, python_assignment),
    )
    finalist_assignments = [row["assignment"] for row in result["finalists"]]
    cross_actor_edges = sorted(
        {
            (row["provider_actor"], consumer)
            for row in result["response_ledger"]
            for consumer in row["consumer_actors"]
            if row["provider_actor"] != consumer
        }
    )
    expected_support_edges = sorted(
        {
            ("bennett", "chasca"),
            ("bennett", "furina"),
            ("bennett", "ororon"),
            ("furina", "bennett"),
            ("furina", "chasca"),
            ("furina", "ororon"),
        }
    )
    steps_have_counts = all(
        all(
            key in row
            for key in (
                "raw_physical_builds",
                "expanded",
                "guide_evaluations",
                "complete_evaluations",
                "frontier_discarded",
                "budget_unexpanded",
            )
        )
        for row in result["steps"]
    )
    checks = {
        "initial_assignment_is_current": result["initial"]["assignment"] == incumbent,
        "initial_is_retained_as_explicit_result_boundary": (
            result["initial"]["assignment"] == incumbent
            and result["initial"]["source"] == "incumbent"
        ),
        "python_leader_retained_in_finalists": python_assignment in finalist_assignments,
        "go_leader_no_worse_than_python_on_same_objective": (
            result["leader"]["dps"] + 1e-9 >= python_leader_go_dps
        ),
        "bounded_finalist_set_present": len(result["finalists"]) == 24,
        "support_response_edges_preserved": cross_actor_edges == expected_support_edges,
        "dependency_or_conflict_pairs_are_bounded": 0 < len(result["pair_actor_keys"]) <= 6,
        "uncertainty_prevents_unsafe_saturation_freeze": (
            len(result["opaque_reasons"]) > 0
            and result["saturation_frozen_wearers"] == []
        ),
        "all_search_counts_reported": steps_have_counts,
        "cold_search_below_product_boundary": (
            go["total_elapsed_ms"] / 1000.0 < PRODUCT_BOUNDARY_SECONDS
        ),
        "meaningful_runtime_margin": (
            go["total_elapsed_ms"] / 1000.0 < PRODUCT_BOUNDARY_SECONDS * 0.75
        ),
        "two_cycles_and_recheck_completed": (
            result["completed_cycles"] == 2
            and result["stop_reason"].startswith("provisional_stable")
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"GOB-5 acceptance failed: {failed!r}")
    receipt = {
        "schema_version": 1,
        "schema_kind": "gtt_optimizer_gob5_real_account_acceptance_receipt_v1",
        "status": "PASS",
        "checks": checks,
        "engine_executions": 0,
        "n1000_executions": 0,
        "request_sha256": compact["request_sha256"],
        "artifact_count": len(request["artifacts"]),
        "coordinate_count": len(coordinates),
        "initial_dps": str(result["initial"]["dps"]),
        "python_reference": {
            "historical_single_trace_damage": reference["formula_damage"],
            "historical_runtime_seconds": reference["runtime_seconds"],
            "same_go_panel_dps": str(python_leader_go_dps),
            "retained_finalist_rank": finalist_assignments.index(python_assignment) + 1,
            "assignments": reference["assignments"],
        },
        "go_leader": {
            "dps": str(result["leader"]["dps"]),
            "assignment": dict(zip(wearer_keys, result["leader"]["assignment"], strict=True)),
            "advantage_over_python_reference_dps": str(
                result["leader"]["dps"] - python_leader_go_dps
            ),
        },
        "runtime": {
            "compile_seconds": str(go["compile_elapsed_ms"] / 1000.0),
            "search_seconds": str(go["search_elapsed_ms"] / 1000.0),
            "total_seconds": str(go["total_elapsed_ms"] / 1000.0),
            "product_boundary_seconds": str(PRODUCT_BOUNDARY_SECONDS),
        },
        "search": {
            "completed_cycles": result["completed_cycles"],
            "accepted_steps": result["accepted_steps"],
            "stop_reason": result["stop_reason"],
            "finalist_count": len(result["finalists"]),
            "pair_actor_keys": result["pair_actor_keys"],
            "pair_generated": result["pair_generated"],
            "pair_evaluated": result["pair_evaluated"],
            "pair_invalid": result["pair_invalid"],
            "pair_duplicates": result["pair_duplicates"],
            "cross_actor_response_edges": [list(row) for row in cross_actor_edges],
            "opaque_reason_count": len(result["opaque_reasons"]),
            "saturation_frozen_wearers": result["saturation_frozen_wearers"],
            "steps": [
                {
                    "cycle": row["cycle"],
                    "wearer_key": row["wearer_key"],
                    "accepted": row["accepted"],
                    "raw_physical_builds": row["raw_physical_builds"],
                    "expanded": row["expanded"],
                    "guide_evaluations": row["guide_evaluations"],
                    "complete_evaluations": row["complete_evaluations"],
                    "frontier_discarded": row["frontier_discarded"],
                    "budget_unexpanded": row["budget_unexpanded"],
                    "frontier_width": row["frontier_width"],
                }
                for row in result["steps"]
            ],
        },
        "interpretation": (
            "GOB-5 searches the real Selected artifact domain entirely in Go, "
            "retains the migration leader, finds a higher same-panel formula "
            "score, and finishes with substantial room below 190 seconds. This "
            "is formula-search acceptance, not an n=1000 gameplay-quality claim."
        ),
        "next_stage": "GOB-6_mandatory_cleanup_after_user_authorization",
    }
    RECEIPT_PATH.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
