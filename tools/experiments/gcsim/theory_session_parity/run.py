"""One authorized Stage12 parity packet; managed current-source assembly only."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from tools.experiments.gcsim.theory_light import adapter as light_adapter
from tools.experiments.gcsim.theory_hybrid import run as common
prior, bounds = common.prior, common.bounds
PROTOCOL = ROOT / "docs/optimizer-evidence/2026-10-10-theory-parity/PROTOCOL.md"
SOURCE_RECEIPT = ROOT / "docs/optimizer-evidence/2026-10-10-theory-session/validation.json"
BASELINE = ROOT / "docs/optimizer-evidence/2026-10-10-theory-session/preservation.json"
CASE = "chiori_lunar_crystallize"
COMMON_SHA = "f8740ff8ab9d0ea8c928138e9cfb995c027cbe56495209fea9f6a87c09820eb0"
CORE_COMMIT = "ba880bd5b87752b7a53c889eb1288ec2a01a8dd2"

def identity():
    paths = [p for p in sorted(HERE.iterdir()) if p.suffix in (".py", ".go")]
    rows = {p.relative_to(ROOT).as_posix(): prior.sha(p) for p in paths}
    rows.update({str(PROTOCOL.relative_to(ROOT)): prior.sha(PROTOCOL)})
    return {"files": rows, "sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()}

def _patch(path, before, after):
    text = path.read_text(encoding="utf-8")
    changed = common.adapter.once(text, before, after)
    if common.adapter.once(changed, after, before) != text:
        raise RuntimeError("Parity observer inverse transform changed source")
    path.write_text(changed, encoding="utf-8", newline="\n")

def assemble(job):
    native = job / "native"
    evidence = light_adapter.prepare(native, bounds, CASE)
    _patch(native / "cmd/gtt-optimizer/light_policy_test.go",
           'func lightPassRefinement(h *hybridRun, prefix string) error {',
           'func lightPassRefinement(h *hybridRun, prefix string) error {\n stage12ObserveReference(h, prefix)')
    _patch(native / "internal/theorysearch/search.go",
           '\t\t\tfor _, option := range cfg.Domains[a] {',
           '\t\t\tParityRecordAnchor(b, pass, a, anchor.packages)\n\t\t\tfor _, option := range cfg.Domains[a] {')
    for name in ("product_probe.go", "product_probe_test.go"):
        shutil.copyfile(HERE / name, native / "internal/theorysearch" / name)
    for name in ("compare_test.go", "packet_test.go"):
        shutil.copyfile(HERE / name, native / "cmd/gtt-optimizer" / ("stage12_" + name))
    fixtures = job / "tests/fixtures/gcsim_optimizer_go_v1"
    shutil.copytree(ROOT / "tests/fixtures/gcsim_optimizer_go_v1", fixtures)
    return native, evidence

def _run(command, cwd, env, records, timeout):
    started = time.perf_counter()
    tail, killed = [], threading.Event()
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL)
    def terminate():
        if process.poll() is None:
            killed.set()
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, check=False)
    timer = threading.Timer(timeout, terminate)
    timer.start()
    try:
        for raw in process.stdout:
            line = raw.rstrip()
            if line.startswith("STAGE12_RECEIPT "):
                row = json.loads(line[len("STAGE12_RECEIPT "):])
                records.append(row)
                print("Recorded " + str(row.get("name", row.get("kind", "record"))), flush=True)
            elif not line.startswith("FEASIBLE_RECEIPT "):
                tail = (tail + [line[:6000]])[-30:]
                print(line[:6000], flush=True)
        code = process.wait()
    finally:
        timer.cancel()
        terminate()
        if process.poll() is None:
            process.wait(timeout=15)
    return {"returncode": code, "seconds": time.perf_counter()-started,
            "hard_watchdog_fired": killed.is_set(), "tail": tail}

def verify_preservation():
    expected = json.loads(BASELINE.read_text())["baseline_raw_sha256"]
    owners = {"docs/handoff/GCSIM_GOB11_GP3_CHECKPOINT.md",
              "docs/handoff/GCSIM_OPTIMIZER_GO_BACKEND_DESIGN.md",
              "docs/handoff/GCSIM_OPTIMIZER_TRACE_EQUATION_HANDOFF.md"}
    bad = [p for p, h in expected.items() if p not in owners and prior.sha(ROOT / p) != h]
    core = json.loads(SOURCE_RECEIPT.read_text())["source_provenance"]["raw_sha256"]
    bad += [p for p, h in core.items() if prior.sha(ROOT / p) != h]
    if bad:
        raise RuntimeError("Pinned source/draft changed: " + ", ".join(bad[:5]))
    return {"old_drafts": len(expected), "unaltered_nonhandoff": len(expected)-len(owners),
            "product_core_paths": len(core)}

def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--phase", choices=("preflight", "study"), required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt = args.receipt.resolve()
    receipt.relative_to((ROOT / "docs/optimizer-evidence").resolve())
    prior.assert_unlinked(receipt)
    if receipt.exists():
        raise FileExistsError(receipt)
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()!=CORE_COMMIT:
        raise RuntimeError("Product HEAD changed")
    source = prior.native_source_identity(ROOT)
    prototype = identity()
    if common.identity()["sha256"] != COMMON_SHA or prior.sha(prior.GO) != prior.GO_SHA:
        raise RuntimeError("Reference/toolchain pins changed")
    preserved = verify_preservation()
    consumer = prior.sha(prior.INSTALLED)
    result = {"kind": "theory_stage12_parity_v1", "phase": args.phase, "status": "failed",
        "core_commit": CORE_COMMIT, "native_source": source, "harness": prototype,
        "preservation": preserved, "records": [], "capture_reservation_spent": 0,
        "capture_members_actual": 0, "ordinary_finalists": 0, "study_invocations": 0,
        "offline_guard_seconds": 480, "outer_guard_seconds": 600,
        "installed_consumer_sha256": consumer, "installed_changes": False}
    started = time.perf_counter()
    job = None
    try:
        with prior.managed_scratch() as job:
            result["managed_job"] = str(job)
            (job / "go-cache").mkdir()
            (job / "temp").mkdir()
            inherited = dict(os.environ, GOCACHE=str(job/"go-cache"),
                GTT_MANAGED_GO_CACHE=str(job/"go-cache"), GOTMPDIR=str(job/"temp"),
                GTT_SCRATCH_DIR=str(job), TMP=str(job/"temp"), TEMP=str(job/"temp"))
            env = prior.managed_go.go_environment(job, inherited)
            env.update(PYTHONDONTWRITEBYTECODE="1", GTT_RULE_CACHE_DIR=str(job/"rules"),
                GTT_RULE_BUNDLED_CACHE_DIR=str(job/"bundled-rules"),
                GOPROXY="off", GOTOOLCHAIN="local")
            for key in ("GTT_PROGRESSIVE_KNOWN","GTT_BOUNDS_CONTROL_PACKAGES",
                        "GTT_FEASIBLE_NUMERIC_REUSE", "GTT_FEASIBLE_REQUEST"):
                env.pop(key, None)
            prior.managed_go.seed_module_downloads(Path(env["GOMODCACHE"]), prior.MODULES, prior.MODULE_SHA)
            native, proof = assemble(job)
            result["observer_equivalence"] = proof
            binary = job/"stage12-tests.exe"
            result["compile"] = _run([str(prior.GO),"test","-c","./cmd/gtt-optimizer",
                "-o",str(binary),"-p","2"],native,env,result["records"],180)
            if result["compile"]["returncode"]:
                raise RuntimeError("Managed pinned assembly/harness compilation failed before capture")
            result["probe_contracts"] = _run([str(prior.GO),"test","-count=1","-p","2",
                "-run","^TestParity","-v","./internal/theorysearch"],native,env,result["records"],90)
            if result["probe_contracts"]["returncode"]:
                raise RuntimeError("Product probe contracts failed before capture")
            result["reference_contracts"] = _run([str(binary),
                "-test.run=^TestHybrid|^TestCommonH|^TestLight|^TestStage12(Reference|Comparison|Family|Point)",
                "-test.v","-test.timeout=60s"],native,env,result["records"],70)
            if result["reference_contracts"]["returncode"]:
                raise RuntimeError("Reference/comparison contracts failed before capture")
            if args.phase=="study":
                from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
                from run_workspace.gcsim.optimizer_go_all_sources import prepare_all_set_effect_sources
                from tools.experiments.gcsim.theory_bounds.inputs import load_contrast
                engine=load_active_gcsim_optimizer_engine_context()
                if not engine.trusted or engine.engine_id!="gcsim-v2.45.0-20260927011932" or engine.artifact_sha256!="7df37b5224f655d271d9389686bf22445717e02e896df5e3aa22d1d698042f8c" or prior.sha(Path(engine.artifact_path))!=engine.artifact_sha256:
                    raise RuntimeError("Active trusted engine differs")
                result["engine"]={k:getattr(engine,k) for k in ("engine_id","artifact_path","artifact_sha256","binding_sha256")}
                at=time.perf_counter()
                req, provenance=load_contrast(CASE,job,engine)
                result["input_preparation_seconds"]=time.perf_counter()-at
                result["input_provenance"]=provenance
                if req["stochastic"]["seeds"]!=[742031889,742031890]:
                    raise RuntimeError("Two saved seeds differ")
                prior.write_json(job/"request.json",req)
                sources=prepare_all_set_effect_sources(Path(engine.engine_root),req["engine"],include_neutral_rules=True)
                prior.write_json(job/"sources.json",sources)
                prior.write_json(job/"rarities.json",{s.key:s.max_rarity for s in engine.catalog.sets})
                result["request_file_sha256"]=prior.sha(job/"request.json")
                result["sources_file_sha256"]=prior.sha(job/"sources.json")
                if identity()!=prototype or prior.native_source_identity(ROOT)!=source:
                    raise RuntimeError("Frozen sources changed before capture")
                env.update(GTT_FEASIBLE_REQUEST=str(job/"request.json"),
                    GTT_FEASIBLE_SOURCES=str(job/"sources.json"),GTT_FEASIBLE_RARITIES=str(job/"rarities.json"),
                    GTT_FEASIBLE_ROOT=str(job/"packet"),GTT_BOUNDS_CASE=CASE)
                result["capture_reservation_spent"]=2
                result["study_invocations"]=1
                result["capture_members_actual"]=None  # Unknown until the owner emits its ledger.
                result["study"]=_run([str(binary),"-test.run=^TestStage12NumericalParity$",
                    "-test.v","-test.timeout=610s"],native,env,result["records"],600)
                caps=[r for r in result["records"] if r.get("kind")=="capture_budget"]
                if caps:
                    result["capture_members_actual"]=caps[-1]["attempted"]
                if result["study"]["returncode"]:
                    raise RuntimeError("Single parity study failed; no retry or recapture")
                summaries=[r for r in result["records"] if r.get("kind")=="parity_summary"]
                if len(summaries)!=1 or result["capture_members_actual"]!=2:
                    raise RuntimeError("Missing final parity or exact2 capture evidence")
                if summaries[0]["offline_seconds"]>480 or result["study"]["seconds"]>600:
                    raise RuntimeError("Hard numerical/outer guard exceeded")
                if prior.sha(job/"request.json")!=result["request_file_sha256"] or prior.sha(job/"sources.json")!=result["sources_file_sha256"]:
                    raise RuntimeError("Study inputs changed")
            result["scratch_bytes_before_cleanup"]=sum(p.stat().st_size for p in job.rglob("*") if p.is_file())
            result["status"]="pass"
    except Exception as exc:
        result["error"]=str(exc)
    finally:
        result["wall_seconds"]=time.perf_counter()-started
        result["cleanup"]={"job_removed":job is not None and not job.exists(),
            "surviving_jobs":len(list((ROOT/".codex_tmp/managed-optimizer").glob("job-*")))}
        result["source_stable"]=prior.native_source_identity(ROOT)==source and identity()==prototype
        result["consumer_stable"]=prior.sha(prior.INSTALLED)==consumer
        result["preservation_after"]=verify_preservation()
        if not result["source_stable"] or not result["consumer_stable"] or not result["cleanup"]["job_removed"] or result["cleanup"]["surviving_jobs"]:
            result["status"]="failed"
        prior.write_json(receipt,result)
    print(json.dumps({"status":result["status"],"captures":result["capture_members_actual"],
        "reservation":result["capture_reservation_spent"],"cleanup":result["cleanup"],"error":result.get("error")}),flush=True)
    return 0 if result["status"]=="pass" else 1

if __name__=="__main__":
    raise SystemExit(main())
