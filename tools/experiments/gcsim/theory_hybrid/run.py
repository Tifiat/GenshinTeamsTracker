"""Common H research entry point; stage8 permits only one Bountiful capture pair."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from tools.experiments.gcsim.theory_bounds import run as bounds
from tools.experiments.gcsim.theory_hybrid import adapter

prior = bounds.prior
PRIOR_RECEIPTS = {
    "chasca": "442b4385e298eb78a8bc19f062ab8d72c94ec58196e6db5c8214aedf5874838a",
    "chiori": "8a8116c036a2ff84893087aa548873e663b3a86ee096c1a13232ecfae8de7d02",
    "bountiful": "228e36daf090fdb89a0ceebc5b99daf42f419f8a9d837bfe3678c3bdaa141b65",
}


def identity():
    files = {p.name: prior.sha(p) for p in sorted(HERE.iterdir()) if p.suffix in (".py", ".go")}
    material = {"files": files, "v2_dependency": bounds.identity()["sha256"]}
    return {**material, "sha256": hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()}


def verify_prior_receipts(native_sha):
    rows = []
    for case, digest in PRIOR_RECEIPTS.items():
        path = ROOT / "docs/optimizer-evidence/2026-10-09-theory-hybrid" / (case + "-01.json")
        if prior.sha(path) != digest:
            raise RuntimeError("Prior receipt changed: " + case)
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["status"] != "pass" or data["native_source_sha256"] != native_sha or not data["inputs_stable"] or not data["engine_stable"]:
            raise RuntimeError("Prior identity/status differs: " + case)
        policies = {r["variant"]: r for r in data["records"] if r.get("kind") == "hybrid_policy"}
        prep = next(r for r in data["records"] if r.get("kind") == "preparation")
        same_core = case != "bountiful"
        if same_core:
            if data["prototype"]["sha256"] != adapter.LEGACY_DEPENDENCY_SHA:
                raise RuntimeError("Prior v2 dependency differs: " + case)
            for label, passes in (("H_transfer_first_pass", 1), ("H_transfer", 2)):
                row = policies[label]
                if row["completed_refined_passes"] != passes or row["full_sweeps"] != 8*passes:
                    raise RuntimeError("Prior refined checkpoint incomplete: " + case)
                work = row["work"]
                if work["Formula"] >= 400000 or work["Gradient"] >= 100000 or row["reuse"]["Requests"] >= 9+16*prep["packages_per_wearer"]+64 or row["seconds"] >= 180:
                    raise RuntimeError("New watchdog would censor prior numerical route: " + case)
        shared = data["input_preparation_seconds"] + data["source_preparation_seconds"] + prep["capture_seconds"] + prep["model_seconds"]
        summary = next(r for r in data["records"] if r.get("kind") == "hybrid_summary")
        process_residual = data["search"]["seconds"] - prep["capture_seconds"] - prep["model_seconds"] - summary["seconds"]
        selected = []
        for label in ("H_transfer_first_pass", "H_transfer"):
            if label not in policies:
                continue
            p = policies[label]
            selected.append({"label": label, "formula_dps": p["best"]["formula_dps"], "policy_seconds": p["seconds"],
                             "reconstructed_cold_subtotal_seconds": shared+p["seconds"],
                             "reconstructed_with_process_residual_seconds": shared+process_residual+p["seconds"], "work": p["work"],
                             "family_count": len(p["ranking"]), "full_sweeps": p["full_sweeps"]})
        rows.append({"case": case, "path": path.relative_to(ROOT).as_posix(), "sha256": digest,
                     "prototype_sha256": data["prototype"]["sha256"], "same_v2_numerical_core": same_core,
                     "scope": "measured v2 first/full checkpoints; watchdogs nonbinding" if same_core else "v1 historical context; refined first-pass unmeasured",
                     "shared_named_preparation_seconds": shared, "policies": selected,
                     "native_process_residual_seconds": process_residual,
                     "residual_scope": "native input/catalog, test startup/output/teardown and unassigned overhead; not a pure input timer",
                     "managed_matrix_wall_seconds": data["wall_seconds"],
                     "compilation_seconds": data["compile"]["seconds"],
                     "managed_matrix_without_compile_seconds": data["wall_seconds"]-data["compile"]["seconds"],
                     "timing_is_new_standalone_run": False})
    return rows


def pipeline_timing(result):
    prep = next((r for r in result["records"] if r.get("kind") == "preparation"), None)
    summary = next((r for r in result["records"] if r.get("kind") == "common_h_study_summary"), None)
    if prep is None or summary is None:
        return {"complete_study_timing_available": False}
    native_preparation = sum(prep[k] for k in ("native_input_seconds", "capture_seconds", "model_seconds", "catalog_setup_seconds"))
    shared = result["input_preparation_seconds"] + result["source_preparation_seconds"] + native_preparation
    process_residual = result["study"]["seconds"] - native_preparation - summary["seconds"]
    compile_seconds = result["compile"]["seconds"]
    contract_seconds = result["contracts"]["seconds"]
    measured = compile_seconds + contract_seconds + result["input_preparation_seconds"] + result["source_preparation_seconds"] + result["study"]["seconds"]
    checkpoints = []
    for row in result["records"]:
        if row.get("kind") == "hybrid_policy":
            checkpoints.append({"label": row["variant"], "policy_seconds": row["seconds"],
                                "reconstructed_cold_subtotal_seconds": shared+row["seconds"],
                                "reconstructed_with_process_residual_seconds": shared+process_residual+row["seconds"]})
    return {"complete_study_timing_available": True, "native_preparation_seconds": native_preparation,
            "shared_named_preparation_seconds": shared, "native_process_residual_seconds": process_residual,
            "native_process_residual_scope": "test-process startup/output/teardown and unassigned time; not pure preparation",
            "checkpoints": checkpoints, "standalone_first_or_full_run_measured": False,
            "actual_managed_wall_seconds": result["wall_seconds"], "compilation_seconds": compile_seconds,
            "contracts_seconds": contract_seconds, "actual_managed_without_compile_seconds": result["wall_seconds"]-compile_seconds,
            "managed_setup_cleanup_and_unassigned_seconds": result["wall_seconds"]-measured,
            "offline_study_seconds": summary["seconds"], "offline_target_seconds": 360,
            "offline_target_met": summary["seconds"] <= 360,
            "actual_scope": "managed setup, compilation/contracts, preparation/capture, full H with first checkpoint, audit/postchecks, cleanup"}


def known_rows():
    path = ROOT / "docs/optimizer-evidence/2026-10-09-theory-hybrid/bountiful-01.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for r in data["records"]:
        if r.get("kind") == "hybrid_policy" and r.get("variant") in ("R_fresh", "H_transfer", "P_pairs"):
            rows.append({"label": "historical_" + r["variant"], "candidate": r["best"]})
        elif r.get("kind") in ("progressive_known_control", "progressive_known_on_leader") and r.get("candidate"):
            rows.append({"label": "historical_" + r.get("label", r.get("known_label", r["kind"])), "candidate": r["candidate"]})
    return rows, {"path": path.relative_to(ROOT).as_posix(), "sha256": prior.sha(path),
                  "rows": len(rows), "role": "read by Go only after policy and independent audit; never starts or queue"}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--phase", choices=("unit", "study"), required=True)
    parser.add_argument("--case", choices=("bountiful_core",), default="bountiful_core")
    parser.add_argument("--depth", choices=("first", "full"), default="full")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.phase == "study" and args.depth != "full":
        raise ValueError("Stage8's sole capture must include first and full H; use full depth")
    receipt = args.receipt.resolve()
    receipt.relative_to((ROOT / "docs/optimizer-evidence").resolve())
    prior.assert_unlinked(receipt)
    if receipt.exists():
        raise FileExistsError(receipt)
    source = prior.native_source_identity(ROOT)
    prototype = identity()
    consumer = prior.sha(prior.INSTALLED)
    if prior.sha(prior.GO) != prior.GO_SHA:
        raise RuntimeError("Toolchain identity differs")
    prior_evidence = verify_prior_receipts(source["sha256"])
    result = {"kind": "theory_common_h_research_v1", "status": "failed", "phase": args.phase,
              "case": args.case, "depth": args.depth, "native_source_sha256": source["sha256"],
              "prototype": prototype, "installed_consumer_sha256": consumer, "installed_changes": False,
              "prior_evidence": prior_evidence, "records": [], "capture_member_limit": 2 if args.phase == "study" else 0,
              "capture_reservation_spent": 0, "ordinary_finalists": 0, "full_solution_cache_enabled": False,
              "offline_guard_seconds": 300, "test_process_guard_seconds": 420, "compilation_separate": True}
    started = time.perf_counter()
    try:
        with prior.managed_scratch() as job:
            result["managed_job"] = str(job)
            (job / "go-cache").mkdir()
            (job / "temp").mkdir()
            inherited = dict(os.environ, GOCACHE=str(job / "go-cache"), GTT_MANAGED_GO_CACHE=str(job / "go-cache"),
                             GOTMPDIR=str(job / "temp"), GTT_SCRATCH_DIR=str(job), TMP=str(job / "temp"), TEMP=str(job / "temp"))
            env = prior.managed_go.go_environment(job, inherited)
            env.update(PYTHONDONTWRITEBYTECODE="1", GTT_RULE_CACHE_DIR=str(job / "rules"), GTT_RULE_BUNDLED_CACHE_DIR=str(job / "bundled-rules"))
            env.pop("GTT_BOUNDS_CONTROL_PACKAGES", None)
            env.pop("GTT_FEASIBLE_NUMERIC_REUSE", None)
            prior.managed_go.seed_module_downloads(Path(env["GOMODCACHE"]), prior.MODULES, prior.MODULE_SHA)
            native = job / "native"
            result["core_equivalence"] = adapter.prepare(native, bounds, args.case)
            binary = job / "common-h-tests.exe"
            result["compile"] = prior.run_process([str(prior.GO), "test", "-c", "./cmd/gtt-optimizer", "-o", str(binary), "-p", "2"],
                                                  native, env, "FEASIBLE_RECEIPT ", result["records"])
            if result["compile"]["returncode"]:
                raise RuntimeError("Common H compilation failed before capture")
            result["contracts"] = prior.run_process([str(binary), "-test.run=^TestHybrid|^TestCommonH", "-test.v", "-test.timeout=60s"],
                                                    native, env, "FEASIBLE_RECEIPT ", result["records"])
            if result["contracts"]["returncode"]:
                raise RuntimeError("Common H contracts failed before capture")
            if args.phase == "study":
                from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
                from run_workspace.gcsim.optimizer_go_all_sources import prepare_all_set_effect_sources
                from tools.experiments.gcsim.theory_bounds.inputs import load_contrast
                engine = load_active_gcsim_optimizer_engine_context()
                if not engine.trusted or prior.sha(Path(engine.artifact_path)) != engine.artifact_sha256:
                    raise RuntimeError("Selected engine not trusted")
                result["engine"] = {k: getattr(engine, k) for k in ("engine_id", "engine_root", "artifact_path", "artifact_sha256", "binding_sha256")}
                at = time.perf_counter()
                req, provenance = load_contrast(args.case, job, engine)
                result["input_preparation_seconds"] = time.perf_counter() - at
                result["input_provenance"] = provenance
                if len(req["stochastic"]["seeds"]) != 2:
                    raise RuntimeError("Stage8 requires exactly two capture members")
                result["request_sha256"] = hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()
                prior.write_json(job / "request.json", req)
                at = time.perf_counter()
                prior.write_json(job / "sources.json", prepare_all_set_effect_sources(Path(engine.engine_root), req["engine"], include_neutral_rules=True))
                prior.write_json(job / "rarities.json", {s.key: s.max_rarity for s in engine.catalog.sets})
                result["source_preparation_seconds"] = time.perf_counter() - at
                known, result["known_witness_provenance"] = known_rows()
                prior.write_json(job / "known.json", known)
                env.update(GTT_FEASIBLE_REQUEST=str(job / "request.json"), GTT_FEASIBLE_SOURCES=str(job / "sources.json"),
                           GTT_FEASIBLE_RARITIES=str(job / "rarities.json"), GTT_FEASIBLE_ROOT=str(job / "experiment"),
                           GTT_FEASIBLE_PHASE="common_h", GTT_COMMON_H_DEPTH=args.depth, GTT_BOUNDS_CASE=args.case,
                           GTT_PROGRESSIVE_KNOWN=str(job / "known.json"))
                result["capture_reservation_spent"] = 2
                result["study"] = prior.run_process([str(binary), "-test.run=^TestTheoryFeasibleExperiment$", "-test.v", "-test.timeout=420s"],
                                                    native, env, "FEASIBLE_RECEIPT ", result["records"])
                if result["study"]["returncode"]:
                    raise RuntimeError("Common H study failed; no automatic recapture")
                prep = next(r for r in result["records"] if r.get("kind") == "preparation")
                result["capture_members_actual"] = prep["engine_calls"]
                if prep["engine_calls"] != 2:
                    raise RuntimeError("Unexpected capture count")
                current = load_active_gcsim_optimizer_engine_context()
                result["engine_stable"] = current.binding_sha256 == engine.binding_sha256 and prior.sha(Path(engine.artifact_path)) == engine.artifact_sha256
            result["scratch_bytes_before_cleanup"] = sum(p.stat().st_size for p in job.rglob("*") if p.is_file())
        result["inputs_stable"] = prior.native_source_identity(ROOT)["sha256"] == source["sha256"] and identity() == prototype and prior.sha(prior.INSTALLED) == consumer
        result["status"] = "pass" if result["inputs_stable"] and result.get("engine_stable", True) else "failed_identity"
    except BaseException as exc:
        result["error"] = str(exc)
        raise
    finally:
        if "managed_job" in result:
            owned = Path(result["managed_job"])
            result["cleanup"] = {"job_absent": not owned.exists(), "remaining_jobs": [p.name for p in owned.parent.glob("job-*")]}
        result["wall_seconds"] = time.perf_counter() - started
        result["timing"] = pipeline_timing(result)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        with receipt.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps({"status": result["status"], "receipt": str(receipt)}), flush=True)


if __name__ == "__main__":
    main()
