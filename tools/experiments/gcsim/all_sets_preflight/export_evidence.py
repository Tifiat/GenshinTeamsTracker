"""Export bounded All Sets preflight evidence without running an engine.

Only selects existing real-capture witnesses; expected damage is never computed
by this exporter. The portable samples pin static-effect arithmetic and rejected
shortcut controls, not universal set replacement or an All Sets implementation.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import combinations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.experiments.gcsim.gob11_dependency_audit.export_samples import slice_member
from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
from tools.experiments.gcsim.all_sets_preflight.probe import validate_wire_binding


def inventory_summary(request: dict, catalog: dict) -> dict:
    slots = defaultdict(set)
    for item in request["artifacts"]:
        if item["rarity"] == 5:
            slots[item["set_uid"]].add(item["slot"])
    known = {d["set_key"] for d in catalog["descriptors"]}
    four_known = set(catalog["modeled_5star_4p_keys"])
    four = sorted(k for k, positions in slots.items() if len(positions) >= 4 and k in four_known)
    pairs = [(a, b) for a, b in combinations(sorted(known & slots.keys()), 2)
             if len(slots[a]) >= 2 and len(slots[b]) >= 2 and len(slots[a] | slots[b]) >= 4]
    return {"scope": "saved fixture inventory, optimistic single-wearer slot feasibility only; no team ID/conflict proof",
            "five_star_sets_present": len(slots), "slot_feasible_4p_count": len(four),
            "slot_feasible_2plus2_count": len(pairs), "slot_feasible_4p_keys": four}


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, required=True)
    args = parser.parse_args()
    folder = args.matrix.resolve()
    load = lambda name: json.loads((folder / name).read_text(encoding="utf-8"))
    jobs = {j["case"]: j for j in load("jobs.json")}
    responses = {r["case"]: r for r in load("response.json")}
    samples = []
    definitions = [("remove_static", False), ("remove_static", True),
                   ("replace_static", False), ("restore_static_offline", False)]
    for case, foreign in definitions:
        row, job = responses[case], jobs[case]
        assert row["aligned"] and row["mismatched_hits"] == 0 and row["dense_interpreter_error"] == 0
        base, fresh = load(job["base"]), load(job["output"])
        eligible = [i for i, c in enumerate(base["channels"])
                    if (c["actor_key"] != "lauma") == foreign]
        difference = lambda i: abs(float(base["channels"][i]["baseline_damage"]) - float(fresh["channels"][i]["baseline_damage"]))
        index = max(eligible, key=difference)
        assert difference(index) > 1e-6
        samples.append({"case": case + ("_cross_owner" if foreign else "_personal"),
                        "original_channel": base["channels"][index]["channel_id"],
                        "member": slice_member(base, index),
                        "checks": [{"deltas": job["deltas"], "engine_expected_damage": fresh["channels"][index]["baseline_damage"]}]})
    negatives = []
    for case in ("negative_control_ghost_old_bonus", "negative_control_double_new_bonus", "remove_resistance"):
        row, job = responses[case], jobs[case]
        assert row["aligned"] and row["mismatched_hits"] > 0
        base, fresh = load(job["base"]), load(job["output"])
        index = row["first_mismatches"][0]["index"]
        negatives.append({"case": case, "member": slice_member(base, index), "wrong_deltas": job["deltas"],
                          "fresh_engine_damage": fresh["channels"][index]["baseline_damage"],
                          "same_topology_hash": base["topology_sha256"] == fresh["topology_sha256"]})
    fixtures = ROOT / "tests/fixtures/gcsim_optimizer_go_v1"
    sample_file = fixtures / "all_sets_preflight_samples_v1.json"
    sample_file.write_text(json.dumps({"schema_version": 1, "scope": __doc__, "samples": samples,
                                       "negative_controls": negatives}, indent=2), encoding="utf-8")

    catalog, timings, captures = load("catalog.json"), load("timings.json"), load("captures.json")
    request = json.loads((args.source_run / "request.json").read_text(encoding="utf-8"))
    context = load_active_gcsim_optimizer_engine_context()
    wire_binding = validate_wire_binding(context, request)
    assert context.catalog.source_fingerprint == catalog["catalog_fingerprint"]
    assert context.binding_sha256 == catalog["binding_sha256"]
    catalog["modeled_5star_4p_keys"] = list(context.catalog.modeled_five_star_four_piece_keys)
    receipt = {
        "schema_version": 1, "date": "2026-09-16",
        "authority": "docs/handoff/GCSIM_GOB11_GP3_CHECKPOINT.md",
        "status": "bounded_static_reuse_demonstrated_conditional_reuse_not_implemented",
        "engine_id": catalog["engine_id"], "engine_sha256": catalog["engine_sha256"],
        "catalog_engine_binding_sha256": catalog["binding_sha256"],
        "standalone_wire_binding_sha256": wire_binding, "source_and_wire_identity_revalidated": True,
        "catalog_fingerprint": catalog["catalog_fingerprint"],
        "catalog_modeled_five_star_4p": catalog["modeled_5star_4p_count"],
        "two_piece_proof_counts": catalog["two_piece_proof_counts"],
        "proof_limit": "Existing classifier recognizes constructor stat assignments, not a whole-lifecycle replacement certificate. Init/helpers/key collisions/order/stat-read coverage require a gate.",
        "inventory": inventory_summary(request, catalog),
        "gate": load("gate.json"), "timings": timings,
        "baseline": load("base-summary.json"),
        "capture_timings": [{k: r[k] for k in ("case", "capture_seconds", "bytes", "sha256", "config_sha256", "hits", "nodes", "duration_ms", "topology_sha256")} for r in captures],
        "responses": [{k: row[k] for k in ("case", "aligned", "base_hits", "fresh_hits", "mismatched_hits", "relative_error", "dense_interpreter_error", "same_topology_hash") if k in row} for row in responses.values()],
        "notes": [
            "Seven new n1 same-seed captures, baseline reused. No full search or n500/n1000 runs.",
            "Static removed/restored/equivalent/replaced effects match all543 hits in this fixture.",
            "Conditional/team/resistance shortcut mismatches are expected negative evidence, not an accepted All Sets result or regression in fixed-set Selected.",
            "Same topology hash is not sufficient for set-effect reuse: removed resistance changes damage with unchanged hits.",
            "New-damage package changes total hits543 to561; old graph lacks those outputs.",
            "No engine patch, installed binary, UI, energy behavior, DB, gear or saved rotation was changed.",
            "No universal4p source analyzer is present. Unknown effects are not zero; fresh per-context captures are the current safe route.",
            "Repeated full Selected pipelines are not the proposed All Sets design; next pilot needs shared preparation and a bounded context budget."
        ],
        "portable_samples": sample_file.name,
        "reproduction": {"probe": "tools/experiments/gcsim/all_sets_preflight/probe.py",
                         "raw_output": str(folder.relative_to(ROOT)).replace("\\", "/"),
                         "source_run": str(args.source_run).replace("\\", "/")},
    }
    (fixtures / "all_sets_preflight_receipt_v1.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({"samples": len(samples), "negative_controls": len(negatives),
                      "sample_bytes": sample_file.stat().st_size, "inventory": receipt["inventory"]}))


if __name__ == "__main__":
    main()
