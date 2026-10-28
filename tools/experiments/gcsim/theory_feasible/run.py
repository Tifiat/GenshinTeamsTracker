"""Managed, isolated Chasca feasibility/search experiment; never installs a build."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from tools.managed_optimizer_experiment import managed_scratch, assert_unlinked
from tools.experiments.gcsim.theory_source_repair import run_sourcegen_gate as managed_go
from tools.experiments.gcsim.theory_audit.run_gaming_neutral import native_source_identity
from tools.experiments.gcsim.theory_strategies.run_comparison import GO, GO_SHA, MODULES, MODULE_SHA, SOURCE, INSTALLED, sha
from tools.experiments.gcsim.parametric_effects.repair_health_identity import rebind_request, write_json


def source_identity():
    files = sorted(HERE.rglob("*.go")) + [Path(__file__).resolve()]
    files += [ROOT/p for p in (
        "tools/managed_optimizer_experiment.py",
        "tools/experiments/gcsim/theory_source_repair/run_sourcegen_gate.py",
        "tools/experiments/gcsim/theory_audit/run_gaming_neutral.py",
        "tools/experiments/gcsim/theory_strategies/run_comparison.py",
        "tools/experiments/gcsim/parametric_effects/repair_health_identity.py",
        "tools/experiments/gcsim/theory_verification/render.py",
        "tools/experiments/gcsim/theory_verification/run_case.py",
        "run_workspace/gcsim/optimizer_engine_context.py",
        "run_workspace/gcsim/optimizer_go_all_sources.py",
        "run_workspace/gcsim/artifact_investment_rules.py")]
    rows = {p.relative_to(ROOT).as_posix(): sha(p) for p in files}
    return {"files": rows, "sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()}


def run_process(command, cwd, env, prefix, records):
    started = time.perf_counter()
    tail = []
    with subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace") as p:
        try:
            for raw in p.stdout:
                line = raw.rstrip()
                if line.startswith(prefix):
                    records.append(json.loads(line[len(prefix):]))
                    print("Recorded " + str(records[-1].get("name", records[-1].get("kind", "measurement"))), flush=True)
                else:
                    print(line, flush=True)
                    tail = (tail + [line])[-20:]
            code = p.wait()
        finally:
            if p.poll() is None:
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, check=False)
                p.wait(timeout=15)
    return {"returncode": code, "seconds": time.perf_counter()-started, "tail": tail}


def verify(job, req, engine, candidates, env, limit=3):
    from tools.experiments.gcsim.theory_verification.render import render_candidate_config
    from tools.experiments.gcsim.theory_verification.run_case import summarize_member
    from run_workspace.gcsim.artifact_set_catalog import load_gcsim_artifact_set_catalog
    sets = [s.key for s in load_gcsim_artifact_set_catalog(Path(engine.engine_root)).sets]
    out = []
    # The concrete leader, strongest distinct runner-up, and independently solved
    # none control: at most three builds, two identical seeds per build.
    for index, candidate in enumerate(candidates[:limit]):
        folder = job / f"verification-{index}"
        folder.mkdir()
        text = render_candidate_config(req["context"]["prepared_config"]["text"], candidate, known_sets=sets)
        config = folder / "config.txt"
        config.write_text(text, encoding="utf-8", newline="\n")
        points = []
        start = time.perf_counter()
        for seed in req["stochastic"]["seeds"]:
            trace, member = folder / f"trace-{seed}.json", folder / f"member-{seed}.json"
            write_json(trace, {"schema_version": 1, "context_sha256": sha(config), "seed": str(seed),
                "iterations": 1, "workers": 1, "ignore_burst_energy": True, "output_mode": "compact_ir_v1"})
            result = subprocess.run([engine.artifact_path, "-c", str(config), "-out", str(member),
                "-gtt-trace-equation", str(trace)], cwd=folder, env=env, capture_output=True, text=True, timeout=120)
            if result.returncode:
                raise RuntimeError(result.stderr[-2000:])
            doc = json.loads(member.read_bytes())
            point = summarize_member(doc, seed)
            points.append(point)
        mean = sum(p["expected_dps"] for p in points)/len(points)
        out.append({"candidate": candidate, "config": text, "points": points,
                    "formula_dps": candidate["formula_dps"], "engine_expected_dps": mean,
                    "seconds": time.perf_counter()-start,
                    "scope": "paired compact expected-DPS samples; no statistical acceptance threshold"})
    return out


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--mode", choices=("unit", "search"), default="unit")
    parser.add_argument("--phase", choices=("all", "combined", "r2_bench", "r2_fast", "r2_search", "r2_pairs"), default="all")
    parser.add_argument("--reuse-numeric", action="store_true")
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--verify-limit", type=int, default=3)
    args = parser.parse_args()
    if not 0 <= args.verify_limit <= 6:
        raise ValueError("Verification limit must be in [0,6]")
    if args.phase.startswith("r2_") and args.reference:
        raise ValueError("Round two independent experiments cannot reuse completed results")
    receipt = args.receipt.resolve()
    receipt.relative_to((ROOT / "docs/optimizer-evidence").resolve())
    assert_unlinked(receipt)
    if receipt.exists():
        raise FileExistsError(receipt)
    before = native_source_identity(ROOT)
    prototype = source_identity()
    if sha(GO) != GO_SHA:
        raise RuntimeError("Go binary differs from recorded toolchain")
    consumer = sha(INSTALLED)
    outcome = {"kind": "theory_feasible_research_v1", "mode": args.mode, "status": "failed",
        "native_source": before, "prototype": prototype, "installed_consumer_sha256": consumer,
        "installed_changes": False, "records": [], "source_fixture_sha256": sha(SOURCE)}
    reference = None
    if args.reference:
        reference_path = args.reference.resolve(strict=True)
        reference_path.relative_to((ROOT/"docs/optimizer-evidence").resolve())
        reference = json.loads(reference_path.read_bytes())
        if reference.get("status") != "pass" or reference["native_source"]["sha256"] != before["sha256"] or reference["source_fixture_sha256"] != sha(SOURCE):
            raise RuntimeError("Reference source/input binding differs")
        outcome["reference"] = {"path": reference_path.relative_to(ROOT).as_posix(), "sha256": sha(reference_path)}
    outcome["numeric_reuse"] = args.reuse_numeric
    started = time.perf_counter()
    try:
        with managed_scratch() as job:
            outcome["managed_job"] = str(job)
            (job/"go-cache").mkdir()
            (job/"temp").mkdir()
            inherited = dict(os.environ, GOCACHE=str(job/"go-cache"),
                             GTT_MANAGED_GO_CACHE=str(job/"go-cache"),
                             GOTMPDIR=str(job/"temp"), GTT_SCRATCH_DIR=str(job),
                             TMP=str(job/"temp"), TEMP=str(job/"temp"))
            env = managed_go.go_environment(job, inherited)
            env.update(PYTHONDONTWRITEBYTECODE="1", GTT_RULE_CACHE_DIR=str(job/"rules"),
                       GTT_RULE_BUNDLED_CACHE_DIR=str(job/"bundled-rules"))
            managed_go.seed_module_downloads(Path(env["GOMODCACHE"]), MODULES, MODULE_SHA)
            native = job/"native"
            shutil.copytree(ROOT/"native/gcsim_optimizer", native, ignore=shutil.ignore_patterns("*.exe"))
            shutil.copytree(HERE/"kernel", native/"internal/theoryprototype")
            for name in ("affine_probe.go", "affine_probe_test.go"):
                if (HERE/name).exists():
                    shutil.copyfile(HERE/name, native/"internal/formula"/name)
            command = [str(GO), "test", "./internal/theoryprototype", "-count=1", "-v", "-p", "2"]
            outcome["unit"] = run_process(command, native, env, "FEASIBLE_RECEIPT ", outcome["records"])
            if outcome["unit"]["returncode"]:
                raise RuntimeError("Feasibility kernel tests failed")
            if (HERE/"affine_probe_test.go").exists():
                command = [str(GO), "test", "./internal/formula", "-run", "PositiveAffine", "-count=1", "-v", "-p", "2"]
                outcome["affine_unit"] = run_process(command, native, env, "FEASIBLE_RECEIPT ", outcome["records"])
                if outcome["affine_unit"]["returncode"]:
                    raise RuntimeError("Affine certificate tests failed")
            if args.mode == "search":
                from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
                from run_workspace.gcsim.optimizer_go_all_sources import prepare_all_set_effect_sources
                engine = load_active_gcsim_optimizer_engine_context()
                if not engine.trusted or sha(Path(engine.artifact_path)) != engine.artifact_sha256:
                    raise RuntimeError("Selected engine identity is not trusted")
                outcome["engine"] = {k: getattr(engine,k) for k in ("engine_id", "engine_root", "artifact_path", "artifact_sha256", "binding_sha256")}
                req = rebind_request(json.loads(SOURCE.read_bytes())["original_request"], Path(engine.engine_root))
                if [w["wearer_key"] for w in req["wearers"]] != ["bennett", "chasca", "furina", "ororon"]:
                    raise RuntimeError("Unexpected saved team")
                write_json(job/"request.json", req)
                prep = time.perf_counter()
                write_json(job/"sources.json", prepare_all_set_effect_sources(Path(engine.engine_root),req["engine"],include_neutral_rules=True))
                write_json(job/"rarities.json", {s.key: s.max_rarity for s in engine.catalog.sets})
                outcome["source_preparation_seconds"] = time.perf_counter()-prep
                shutil.copyfile(HERE/"family_probe.go", native/"internal/setcontext/theory_research_family.go")
                shutil.copyfile(HERE/"hunter_probe.go", native/"internal/setcontext/theory_research_hunter.go")
                shutil.copyfile(HERE/"experiment_test.go", native/"cmd/gtt-optimizer/theory_feasible_experiment_test.go")
                if (HERE/"round_two_test.go").exists():
                    shutil.copyfile(HERE/"round_two_test.go", native/"cmd/gtt-optimizer/theory_round_two_test.go")
                for name in ("affine_probe.go", "affine_probe_test.go"):
                    if (HERE/name).exists():
                        shutil.copyfile(HERE/name, native/"internal/formula"/name)
                env.update(GTT_FEASIBLE_REQUEST=str(job/"request.json"), GTT_FEASIBLE_SOURCES=str(job/"sources.json"), GTT_FEASIBLE_RARITIES=str(job/"rarities.json"), GTT_FEASIBLE_ROOT=str(job/"experiment"))
                binary = job/"feasible-tests.exe"
                command = [str(GO),"test","-c","./cmd/gtt-optimizer","-o",str(binary),"-p","2"]
                outcome["compile"] = run_process(command,native,env,"FEASIBLE_RECEIPT ",outcome["records"])
                if outcome["compile"]["returncode"]:
                    raise RuntimeError("Chasca harness compilation failed")
                for phase in (("ablations", "combined") if args.phase == "all" else (args.phase,)):
                    phase_env = dict(env,GTT_FEASIBLE_PHASE=phase,GTT_FEASIBLE_ROOT=str(job/phase),
                                     GTT_FEASIBLE_NUMERIC_REUSE="1" if args.reuse_numeric else "0")
                    command = [str(binary),"-test.run=^TestTheoryFeasibleExperiment$","-test.v","-test.timeout=20m"]
                    outcome[phase] = run_process(command,native,phase_env,"FEASIBLE_RECEIPT ",outcome["records"])
                    if outcome[phase]["returncode"]:
                        raise RuntimeError("Chasca " + phase + " failed")
                finalists = next((r["candidates"] for r in reversed(outcome["records"]) if r.get("kind") == "finalists"), [])
                if reference:
                    if reference["engine"]["binding_sha256"] != engine.binding_sha256:
                        raise RuntimeError("Reference engine binding differs")
                    prior = next(r["candidates"] for r in reversed(reference["records"]) if r.get("kind") == "finalists")
                    matches = len(prior) == len(finalists) and all(
                        all(a[k] == b[k] for k in ("packages", "allocations", "feasibility_witness"))
                        and math.isclose(a["formula_dps"], b["formula_dps"], rel_tol=1e-12, abs_tol=1e-8)
                        for a,b in zip(prior,finalists))
                    outcome["reference_candidates_equal"] = matches
                    if not matches:
                        raise RuntimeError("Exact numeric-cache experiment changed a reference candidate")
                    outcome["verification"] = reference["verification"]
                    outcome["verification_reused_from"] = outcome["reference"]
                    outcome["fresh_finalist_engine_calls"] = 0
                else:
                    outcome["verification"] = verify(job,req,engine,finalists,env,args.verify_limit)
                    outcome["fresh_finalist_engine_calls"] = min(args.verify_limit,len(finalists))*len(req["stochastic"]["seeds"])
                current = load_active_gcsim_optimizer_engine_context()
                outcome["engine_stable"] = current.binding_sha256 == engine.binding_sha256 and sha(Path(engine.artifact_path)) == engine.artifact_sha256
            outcome["scratch_bytes_before_cleanup"] = sum(p.stat().st_size for p in job.rglob("*") if p.is_file())
        outcome["cleanup"] = {"job_absent": not job.exists(), "remaining_jobs": [p.name for p in job.parent.glob("job-*")]}
        outcome["inputs_stable"] = native_source_identity(ROOT)["sha256"] == before["sha256"] and source_identity() == prototype and sha(INSTALLED) == consumer
        outcome["status"] = "pass" if outcome["inputs_stable"] and outcome.get("engine_stable", True) else "failed_identity"
    except BaseException as exc:
        outcome["error"] = str(exc)
        raise
    finally:
        if "managed_job" in outcome:
            owned = Path(outcome["managed_job"])
            outcome["cleanup"] = {"job_absent": not owned.exists(),
                "remaining_jobs": [p.name for p in owned.parent.glob("job-*")]}
        outcome["wall_seconds"] = time.perf_counter()-started
        receipt.parent.mkdir(parents=True, exist_ok=True)
        with receipt.open("x", encoding="utf-8") as stream:
            json.dump(outcome, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps({"status":outcome["status"],"receipt":str(receipt)}), flush=True)


if __name__ == "__main__":
    main()
