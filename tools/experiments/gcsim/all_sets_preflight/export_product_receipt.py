"""Sanitize preserved All Sets integration evidence; no simulations/account reads.

Keeps aggregate timings, source/binary identities and limits, not private item
inventories, equipment IDs or machine paths. GP-3 owns current acceptance.
"""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[4]
tmp = root / ".codex_tmp"
read = lambda path: json.loads(path.read_bytes())
cli = read(tmp / "all-sets-cli-20260917-run2/output.json")
gate = read(tmp / "all-sets-cli-20260917-run2/cli-receipt.json")
pilot = read(tmp / "all-sets-coordinator-20260917/coordinator-receipt.json")
ordinary = read(tmp / "all-sets-coordinator-ordinary-20260917/ordinary-receipt.json")
installed = read(tmp / "all-sets-install-20260917/installation-receipt.json")
engine = read(tmp / "all-sets-transfer-guide-20260917/engine.json")
pick = lambda obj, keys: {k: obj[k] for k in keys}
selected_formula = cli["search_work"][0]["formula_dps"]
selected = next(c for c in cli["verification"]["candidates"] if c["formula_dps"] == selected_formula)
receipt = {
    "schema_version": 1, "date": "2026-09-17",
    "owner": "docs/handoff/GCSIM_GOB11_GP3_CHECKPOINT.md",
    "status": "all_sets_installed_backend_pass_ui_pending",
    "fixture": "copied_bloom_account_original_Lauma_2plus2_infinite_energy_two_fixed_seeds",
    "cold_test_engine_sha256": engine["artifact_sha256"],
    "cold_test_source_manifest_sha256": engine["source_manifest_sha256"],
    "coordinator_pilot": pick(pilot, ("selected_formula_dps", "best_formula_dps", "new_n1_calls", "reused_members", "capture_members", "total_seconds", "search_expansions", "guides", "stop_reason")),
    "pilot_ordinary": {"replay_seconds": ordinary["replay_seconds"],
        "screen_seconds": ordinary["screen"]["total_elapsed_ms"] / 1000,
        "verify_seconds": ordinary["verification"]["total_elapsed_ms"] / 1000,
        "winner_measured_dps": ordinary["verification"]["winner"]["measured_dps"],
        "calls": {"n128": 7, "n500": 7, "n1000": 3}},
    "cold_cli": {**gate, "includes_python_source_preparation": False,
        "search_seconds": cli["search_seconds"], "guide_seconds_within_search": cli["guide_seconds"],
        "proposal_seconds_within_search": cli["proposal_seconds"],
        "capture_seconds_within_search": sum(w["CaptureSeconds"] for w in cli["search_work"]),
        "artifact_search_seconds_within_search": sum(w["SearchSeconds"] for w in cli["search_work"]),
        "screen_seconds": cli["screening"]["total_elapsed_ms"] / 1000,
        "verify_seconds": cli["verification"]["total_elapsed_ms"] / 1000,
        "search_work": cli["search_work"], "search_expansions": cli["search_expansions"],
        "guides": cli["guides"], "queued": cli["queued"], "pending": cli["pending"],
        "adaptive_status": cli["verification"]["adaptive"]["status"],
        "selected_formula_dps": selected_formula, "selected_measured_dps": selected["measured_dps"],
        "winner_standard_error": cli["product_result"]["measured"]["standard_error"],
        "ordinary_calls": {"n128": 7, "n500": 7, "n1000": 0}},
    "installation": installed,
    "combined_stage_compact_n1_calls": 54,
    "call_accounting": "31 before coordinator +4 coordinator +16 cold CLI +1 bundle compact +2 installed winner; ordinary panels counted separately; earlier preflight pilot8 separate",
    "automated_checks": {"go_test_all": "pass", "go_vet_all": "pass", "python_focused_tests": 34},
    "limits": ["one copied account fixture, not all-team quality or a global optimum",
        "eight contexts selected by bounded source-aware hints, not all492 feasible wearer packages captured",
        "cold CLI6:36 excludes Python request/source preparation, not a visible UI timing",
        "installer rejected byte identity first;155 CRLF-only files explained source/binary hash change, generated semantic manifest equal excluding tree hash; new installed controls passed",
        "no real native AppShell click; Windows computer-use tools unavailable",
        "finite energy unchanged and ER-aware search deferred",
        "Selected2plus2 actual UI and All Sets navigation/save/preservation still require acceptance"],
}
target = root / "tests/fixtures/gcsim_optimizer_go_v1/all_sets_product_receipt_v1.json"
target.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"receipt": str(target.relative_to(root)), "selected_measured_dps": selected["measured_dps"],
                  "capture_seconds": receipt["cold_cli"]["capture_seconds_within_search"],
                  "artifact_search_seconds": receipt["cold_cli"]["artifact_search_seconds_within_search"]}))
