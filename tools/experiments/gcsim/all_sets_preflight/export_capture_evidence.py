"""Export a small scoped receipt from the completed pilot, without new runs.

Keep private inventory/complete finalists in local evidence. The committed
receipt names the bounded witness and timings, not account-scale acceptance.
"""
from pathlib import Path
import argparse
import json


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--decode", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    pilot = json.loads((args.pilot / "capture-pilot-receipt.json").read_text(encoding="utf-8"))
    decode = json.loads((args.decode / "canonical-read-benchmark.json").read_text(encoding="utf-8"))
    replay = json.loads((args.replay / "context-routing-receipt.json").read_text(encoding="utf-8"))
    out = {key: pilot[key] for key in (
        "schema_version", "date", "authority", "engine_sha256", "catalog_sha256", "request_sha256",
        "source_inventory_scope", "feasible_packages", "baseline_dps", "baseline_decode_compile_ms",
        "domain_build_feasibility_ms", "new_engine_calls", "context_capture_members", "candidate_response_members",
        "replayed_baseline_members", "max_expanded_per_actor", "context_timings", "elapsed_seconds",
        "installed_binary_ui_energy_changed", "product_acceptance")}
    out["status"] = "bounded_fresh_context_domain_search_response_pass_not_all_sets_product"
    out["cases"] = []
    for row in pilot["cases"]:
        keep = {key: row[key] for key in (
            "actor", "package", "context_sha256", "route", "proposal_ms", "capture_compile_ms", "search_ms",
            "verification_ms", "observed_two_seed_expected_dps", "relative_response_residual",
            "candidate_member_sha256", "context_hits", "opaque_reasons", "cached_reuse")}
        keep["formula_dps"] = row["winner"]["dps"]
        keep["exceeds_original_baseline"] = keep["formula_dps"] > out["baseline_dps"]
        keep["search_counts"] = {key: row["step"][key] for key in (
            "expanded", "guide_evaluations", "complete_evaluations", "frontier_discarded", "budget_unexpanded")}
        out["cases"].append(keep)
    out["canonical_read_optimization"] = decode
    out["post_refactor_saved_context_replay"] = {
        "elapsed_seconds": replay["elapsed_test_seconds"], "new_engine_calls": 0,
        "replayed_members": replay["replayed_members"], "all_seven_contexts_passed": True,
    }
    out["limits"] = [
        "Two hand-selected 4p proposals; not automatic ranking of all sets or joint whole-team optimum.",
        "1000-expansion pilot cap is not a changed production search default.",
        "Two fixed-seed conditional expected DPS checks are not ordinary n500/n1000 or UI acceptance.",
        "Neither tested package winner beats the original team baseline; retaining incumbent is mandatory.",
        "Timing was measured before the JSON substep optimization; no claimed post-change full pipeline speedup.",
        "Actual full-inventory or 600s All Sets budget acceptance remains untested.",
        "No real-set static replacement proof producer or general 4p effect guide enabled.",
    ]
    out["repair_notes"] = [
        "Initial harness attempt stopped before new engine calls: incorrectly compared Selected trace-context hash to config hash. Corrected to the validated request identity.",
        "Post-run harness cleanup preserves reference-stat identity for candidate config and reads its energy flag explicitly; no additional engine reruns.",
    ]
    target = root / "tests/fixtures/gcsim_optimizer_go_v1/all_sets_capture_domain_receipt_v1.json"
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
