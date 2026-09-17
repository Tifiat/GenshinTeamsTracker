"""Bounded All Sets set-replacement experiment, not a production search path.

Uses the saved Selected2+2 bloom fixture and the installed engine. Names below
are fixture choices only: no character/set rule is added to the optimizer.
The existing two-piece source classifier is evidence to audit, not a universal
equivalence certificate. See the All Sets plan in the Go backend handoff.
Writes isolated generated evidence; never opens the account DB or changes gear.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
from run_workspace.gcsim.engine_store import load_engine_manifest
from run_workspace.gcsim.optimizer_go_contracts import canonical_sha256
from run_workspace.gcsim.optimizer_two_piece_signatures import (
    build_gcsim_optimizer_two_piece_effect_descriptors,
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def validate_wire_binding(context, request: dict) -> str:
    """Catalog-context and standalone-wire bindings are different protocols."""
    root = Path(context.engine_root)
    manifest = load_engine_manifest(root)
    payload = {
        "kind": "gtt.standalone_engine_binding.v1",
        "artifact_sha256": context.artifact_sha256,
        "source_manifest_sha256": digest(root / "build/gtt-source-manifest-body.json"),
        "patch_manifest_sha256": str(manifest.patch_metadata["patch_stack_sha256"]).casefold(),
    }
    for key in ("artifact_sha256", "source_manifest_sha256", "patch_manifest_sha256"):
        assert payload[key] == request["engine"][key], key
    binding = canonical_sha256(payload)
    assert binding == request["engine"]["binding_sha256"]
    return binding


def set_row(text: str, actor: str, old: str, new: str, count: int) -> str:
    """Replace exactly one row in place; never reorder character declarations."""
    pattern = rf'(?m)^{re.escape(actor)} add set="{re.escape(old)}" count=\d+;$'
    value, found = re.subn(pattern, f'{actor} add set="{new}" count={count};', text)
    if found != 1:
        raise ValueError(f"expected one set row: {actor}/{old}, found {found}")
    return value


def member_summary(member: dict) -> dict:
    groups = Counter()
    for channel in member["channels"]:
        groups[f'{channel["actor_key"]}/{channel["attack_tag"]}/{channel["kind"]}/{channel["damage_type"]}'] += 1
    return {
        "hits": len(member["channels"]), "nodes": len(member["nodes"]),
        "duration_ms": member["duration_ms"], "topology_sha256": member["topology_sha256"],
        "expected_damage": sum(float(c["baseline_damage"]) for c in member["channels"]),
        "groups": dict(sorted(groups.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, output = args.source_run.resolve(), args.output.resolve()
    output.relative_to(ROOT / ".codex_tmp")
    output.mkdir(exist_ok=False)
    request = json.loads((source / "request.json").read_text(encoding="utf-8"))
    started = time.perf_counter()
    context = load_active_gcsim_optimizer_engine_context()
    assert context.artifact_sha256 == request["engine"]["artifact_sha256"]
    wire_binding = validate_wire_binding(context, request)
    descriptors = build_gcsim_optimizer_two_piece_effect_descriptors(context)
    by_key = {d.set_key: d for d in descriptors}
    em = Decimal(dict(by_key["wandererstroupe"].semantic_terms)["EM"])
    dendro = Decimal(dict(by_key["deepwoodmemories"].semantic_terms)["DendroP"])
    equivalent = next(d.set_key for d in descriptors if d.set_key not in {"wandererstroupe", "gildeddreams"}
                      and d.semantic_terms == by_key["wandererstroupe"].semantic_terms
                      and d.modifier_key != by_key["wandererstroupe"].modifier_key)
    catalog_seconds = time.perf_counter() - started
    catalog = {
        "engine_id": context.engine_id, "binding_sha256": context.binding_sha256,
        "standalone_wire_binding_sha256": wire_binding,
        "engine_sha256": context.artifact_sha256,
        "catalog_fingerprint": context.catalog.source_fingerprint,
        "catalog_and_binding_seconds": catalog_seconds,
        "modeled_5star_4p_count": len(context.catalog.modeled_five_star_four_piece_keys),
        "modeled_5star_4p_keys": list(context.catalog.modeled_five_star_four_piece_keys),
        "two_piece_proof_counts": dict(Counter(d.proof_kind.value for d in descriptors)),
        "descriptors": [d.to_dict() for d in descriptors],
        "static_terms_are_not_whole_lifecycle_equivalence_proof": True,
    }
    write(output / "catalog.json", catalog)

    baseline_text = (source / "prepared-config.txt").read_text(encoding="utf-8")
    seed = request["stochastic"]["seeds"][0]
    capture_request = json.loads((source / f"compact-request-{seed}.json").read_text())
    base_path = source / f"compact-member-{seed}.json"
    base = json.loads(base_path.read_text())
    shutil.copy2(base_path, output / "base.json")
    write(output / "base-summary.json", member_summary(base))

    without_wt = set_row(baseline_text, "lauma", "wandererstroupe", "wandererstroupe", 1)
    cases = [
        ("remove_static", without_wt, {"lauma.em": float(-em)}),
        ("replace_static", set_row(baseline_text, "lauma", "wandererstroupe", "deepwoodmemories", 2),
         {"lauma.em": float(-em), "lauma.dendro_damage_bonus": float(dendro)}),
        ("equivalent_static", set_row(baseline_text, "lauma", "wandererstroupe", equivalent, 2), {}),
        ("activate_conditional", set_row(without_wt, "lauma", "gildeddreams", "gildeddreams", 4),
         {"lauma.em": float(-em)}),
        ("remove_resistance", set_row(baseline_text, "nahida", "deepwoodmemories", "deepwoodmemories", 2), {}),
        ("add_team_buff", set_row(without_wt, "lauma", "gildeddreams", "noblesseoblige", 4),
         {"lauma.em": float(-2 * em)}),
        ("new_damage", set_row(baseline_text, "kukishinobu", "silkenmoonsserenade", "oceanhuedclam", 4), {}),
    ]
    assert len(cases) == 7  # Frozen engine-call budget; no retries/parameter sweep.
    rows, jobs = [], []
    for name, config, deltas in cases:
        cfg, out = output / f"{name}.txt", output / f"{name}.json"
        cfg.write_text(config, encoding="utf-8")
        bound = dict(capture_request, context_sha256=digest(cfg))
        bound_path = output / f"{name}-request.json"
        write(bound_path, bound)
        tick = time.perf_counter()
        run = subprocess.run([context.artifact_path, "-c", str(cfg), "-out", str(out),
                              "-gtt-trace-equation", str(bound_path)],
                             capture_output=True, text=True, timeout=45)
        elapsed = time.perf_counter() - tick
        if run.returncode:
            write(output / "capture-failure.json", {"case": name, "seconds": elapsed,
                                                    "stderr": run.stderr[-4000:]})
            raise RuntimeError(f"capture failed: {name}")
        fresh = json.loads(out.read_text())
        row = {"case": name, "capture_seconds": elapsed, "bytes": out.stat().st_size,
               "sha256": digest(out), "config_sha256": digest(cfg), **member_summary(fresh)}
        rows.append(row)
        jobs.append({"case": name, "base": "base.json", "output": out.name, "deltas": deltas})
        print(json.dumps({k: row[k] for k in ("case", "capture_seconds", "hits", "nodes")}), flush=True)
        write(output / "captures.json", rows)
    # Reverse removal verifies restoration without a further engine call.
    jobs.append({"case": "restore_static_offline", "base": "remove_static.json", "output": "base.json",
                 "deltas": {"lauma.em": float(em)}})
    # Deliberately wrong controls expose forgotten subtraction/double counting.
    jobs.append({"case": "negative_control_ghost_old_bonus", "base": "base.json", "output": "remove_static.json", "deltas": {}})
    jobs.append({"case": "negative_control_double_new_bonus", "base": "base.json", "output": "replace_static.json",
                 "deltas": {"lauma.em": float(-em), "lauma.dendro_damage_bonus": float(2 * dendro)}})
    write(output / "jobs.json", jobs)
    tick = time.perf_counter()
    subprocess.run([sys.executable, str(ROOT / "tools/experiments/gcsim/gob11_dependency_audit/run_matrix.py"),
                    "--matrix", str(output)], check=True, timeout=90)
    write(output / "timings.json", {"catalog_seconds": catalog_seconds,
                                    "matrix_process_seconds": time.perf_counter() - tick,
                                    "total_seconds": time.perf_counter() - started,
                                    "new_engine_calls": len(cases), "equivalent_set_key": equivalent,
                                    "source_base_sha256": digest(base_path)})
    responses = json.loads((output / "response.json").read_text())
    by_case = {row["case"]: row for row in responses}
    static_cases = ("remove_static", "replace_static", "equivalent_static", "restore_static_offline")
    accepted = all(by_case[name].get("aligned") and by_case[name].get("mismatched_hits") == 0
                   and by_case[name].get("dense_interpreter_error") == 0 for name in static_cases)
    negatives = all(by_case[name].get("mismatched_hits", 0) > 0 for name in
                    ("negative_control_ghost_old_bonus", "negative_control_double_new_bonus"))
    write(output / "gate.json", {"static_fixture_gate_passed": accepted, "negative_controls_detected": negatives,
                                 "scope": "bounded fixture responses only, not production reuse authorization"})
    print(json.dumps({"static_fixture_gate_passed": accepted, "negative_controls_detected": negatives}), flush=True)


if __name__ == "__main__":
    main()
