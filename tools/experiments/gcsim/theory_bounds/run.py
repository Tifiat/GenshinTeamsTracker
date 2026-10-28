"""Finite managed bounds experiments; no installation or saved-solution reuse."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
FEASIBLE = HERE.parent / "theory_feasible"
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from tools.experiments.gcsim.theory_feasible import run as prior


def identity():
    files = sorted(HERE.glob("*.go")) + sorted(HERE.glob("*.py"))
    own = {p.relative_to(ROOT).as_posix(): prior.sha(p) for p in files}
    combined = {"bounds": own, "feasible_dependency": prior.source_identity()}
    return {"sha256": hashlib.sha256(json.dumps(combined, sort_keys=True).encode()).hexdigest(),
            "files": own, "feasible_dependency_sha256": combined["feasible_dependency"]["sha256"]}


def patch_once(text, before, after):
    if text.count(before) != 1:
        raise RuntimeError("Scratch adapter source anchor changed: " + before[:60])
    return text.replace(before, after, 1)


def prepare_copy(native):
    shutil.copytree(ROOT / "native/gcsim_optimizer", native, ignore=shutil.ignore_patterns("*.exe"))
    shutil.copytree(FEASIBLE / "kernel", native / "internal/theoryprototype")
    bound = native / "internal/formula/artifact_bound.go"
    code = bound.read_text(encoding="utf-8")
    code = patch_once(code, "const boundDimensions = 32", "const boundDimensions = 128")
    code = patch_once(code, "type artifactBound struct {", "type artifactBound struct {\n research func(boundVector) (float64, float64)\n researchNode func(int, compiledNode, affineValue, []affineValue)")
    code = patch_once(code, "func (b *artifactBound) support(w boundVector) (float64, float64) {",
        "func (b *artifactBound) support(w boundVector) (float64, float64) {\n if b.research != nil { return b.research(w) }")
    code = patch_once(code, "\t\tvalues[i] = r", "\t\tvalues[i] = r\n\t\tif b.researchNode != nil { b.researchNode(i,n,r,values) }")
    bound.write_text(code, encoding="utf-8", newline="\n")
    for name in ("bounds_probe.go", "bounds_probe_test.go", "diagnostic_probe.go", "diagnostic_probe_test.go", "planes_probe.go", "planes_probe_test.go", "legal_probe_test.go", "targeted_probe.go", "targeted_probe_test.go"):
        shutil.copyfile(HERE/name, native/"internal/formula"/name)


def prepare_harness(native, case):
    for source_name,destination in (("family_probe.go","internal/setcontext/theory_research_family.go"),
        ("hunter_probe.go","internal/setcontext/theory_research_hunter.go"),
        ("round_two_test.go","cmd/gtt-optimizer/theory_round_two_test.go"),
        ("affine_probe.go","internal/formula/affine_probe.go")):
        shutil.copyfile(FEASIBLE/source_name,native/destination)
    harness=(FEASIBLE/"experiment_test.go").read_text(encoding="utf-8")
    if case != "chasca":
        harness=patch_once(harness,
            'req, sources, err := readSetSources(os.Getenv("GTT_FEASIBLE_REQUEST"), os.Getenv("GTT_FEASIBLE_SOURCES"))',
            '_, req, sources, err := readTheorySetSources(os.Getenv("GTT_FEASIBLE_REQUEST"), os.Getenv("GTT_FEASIBLE_SOURCES"))')
    marker='\tif strings.HasPrefix(os.Getenv("GTT_FEASIBLE_PHASE"), "r2_") {'
    harness=patch_once(harness,'\tif h == nil {\n\t\tw.work.Unavailable++',
        '\tif h == nil {\n\t\tw.metadata[theoryteams.Key(p)] = append([]string(nil), codes...)\n\t\tw.work.Unavailable++')
    for phase,call in (("bounds","runTheoryBounds"),("slack","runTheorySlack"),("progressive","runTheoryProgressive"),("hybrid","runTheoryHybrid")):
        harness=patch_once(harness,marker,f'\tif os.Getenv("GTT_FEASIBLE_PHASE") == "{phase}" {{\n {call}(t,factory,req,base,original,options,initial); return\n }}\n'+marker)
    (native/"cmd/gtt-optimizer/theory_feasible_experiment_test.go").write_text(harness,encoding="utf-8",newline="\n")
    for source,destination in (("experiment_test.go","theory_bounds_test.go"),("slack_test.go","theory_slack_test.go"),("deep_cache_test.go","theory_deep_cache_test.go"),("replay_test.go","theory_replay_test.go"),("progressive_test.go","theory_progressive_test.go")):
        shutil.copyfile(HERE/source,native/"cmd/gtt-optimizer"/destination)
    for source in ("hybrid_test.go", "hybrid_contract_test.go"):
        shutil.copyfile(HERE/source,native/"cmd/gtt-optimizer"/source)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--phase", choices=("unit", "bounds", "slack", "replay", "progressive", "hybrid"), default="unit")
    parser.add_argument("--replay-receipt", type=Path)
    parser.add_argument("--case", choices=("chasca", "chiori_lunar_crystallize", "bountiful_core"), default="chasca")
    args = parser.parse_args()
    if args.phase == "slack" and args.case != "chasca":
        raise ValueError("Slack stage is authorized only for Chasca")
    if args.phase == "progressive" and args.case not in ("chiori_lunar_crystallize", "bountiful_core"):
        raise ValueError("Progressive continuation has exactly two authorized contrasts")
    if (args.phase == "replay") != (args.replay_receipt is not None):
        raise ValueError("Replay requires exactly one explicit saved receipt")
    receipt = args.receipt.resolve()
    receipt.relative_to((ROOT/"docs/optimizer-evidence").resolve())
    prior.assert_unlinked(receipt)
    if receipt.exists():
        raise FileExistsError(receipt)
    source = prior.native_source_identity(ROOT)
    prototype = identity()
    consumer = prior.sha(prior.INSTALLED)
    if prior.sha(prior.GO) != prior.GO_SHA:
        raise RuntimeError("Toolchain identity differs")
    outcome = {"kind":"theory_hybrid_research_v1" if args.phase == "hybrid" else "theory_progressive_research_v1" if args.phase == "progressive" else "theory_slack_research_v1" if args.phase in ("slack","replay") else "theory_bounds_research_v1", "status":"failed", "phase":args.phase,
        "case":args.case, "native_source_sha256":source["sha256"], "prototype":prototype,
        "installed_consumer_sha256":consumer, "installed_changes":False, "records":[],
        "capture_call_limit":0 if args.phase in ("unit","replay") else 2, "finalist_engine_calls":0,
        "saved_solution_reuse":False, "scratch_adapter":"128 dimensions, exact support and diagnostic node callback; scratch-only enclosure alternatives"}
    started = time.perf_counter()
    try:
        with prior.managed_scratch() as job:
            outcome["managed_job"] = str(job)
            (job/"go-cache").mkdir()
            (job/"temp").mkdir()
            inherited = dict(os.environ, GOCACHE=str(job/"go-cache"), GTT_MANAGED_GO_CACHE=str(job/"go-cache"),
                GOTMPDIR=str(job/"temp"), GTT_SCRATCH_DIR=str(job), TMP=str(job/"temp"), TEMP=str(job/"temp"))
            env = prior.managed_go.go_environment(job, inherited)
            env.update(PYTHONDONTWRITEBYTECODE="1", GTT_RULE_CACHE_DIR=str(job/"rules"), GTT_RULE_BUNDLED_CACHE_DIR=str(job/"bundled-rules"))
            prior.managed_go.seed_module_downloads(Path(env["GOMODCACHE"]), prior.MODULES, prior.MODULE_SHA)
            native = job/"native"
            prepare_copy(native)
            prepare_harness(native,args.case)
            if args.phase == "unit":
                for key, command in (
                    ("kernel_unit",[str(prior.GO),"test","./internal/theoryprototype","-count=1","-v","-p","2"]),
                    ("envelope_unit",[str(prior.GO),"test","./internal/formula","-run","Research|Bound|RealJoint|ApproximateModel|Union","-count=1","-v","-p","2"]),
                    ("harness_unit",[str(prior.GO),"test","./cmd/gtt-optimizer","-run","TestR2CompleteKey|TestR2MemoizedResult|TestSlackMask","-count=1","-v","-p","2"])):
                    outcome[key] = prior.run_process(command,native,env,"FEASIBLE_RECEIPT ",outcome["records"])
                    if outcome[key]["returncode"]:
                        raise RuntimeError(key + " failed")
            elif args.phase == "replay":
                saved_path=args.replay_receipt.resolve()
                saved_path.relative_to((ROOT/"docs/optimizer-evidence").resolve())
                prior.assert_unlinked(saved_path)
                saved=json.loads(saved_path.read_text(encoding="utf-8"))
                if saved.get("status")!="pass" or saved.get("phase")!="slack" or saved.get("native_source_sha256")!=source["sha256"]:
                    raise ValueError("Replay needs a passed, source-compatible slack receipt")
                fixtures=[r for r in saved["records"] if r.get("kind")=="slack_replay_fixture"]
                if len(fixtures)!=1:
                    raise ValueError("Expected one reduced formula fixture")
                outcome["replay_provenance"]={"path":saved_path.relative_to(ROOT).as_posix(),"sha256":prior.sha(saved_path),
                    "request_sha256":saved["request_sha256"],"captured_engine":saved["engine"],"dag_sha256":fixtures[0]["dag"]["sha256"],
                    "saved_witness_only_for_validation":True,"fresh_engine_calls":0}
                prior.write_json(job/"replay.json",fixtures[0])
                env["GTT_SLACK_REPLAY"]=str(job/"replay.json")
                for key,command in (
                    ("targeted_unit",[str(prior.GO),"test","./internal/formula","-run","ResearchTargeted|ResearchDAG","-count=1","-v","-p","2"]),
                    ("replay",[str(prior.GO),"test","./cmd/gtt-optimizer","-run","^TestTheorySlackReplay$","-count=1","-v","-p","2","-timeout","2m"])):
                    outcome[key]=prior.run_process(command,native,env,"FEASIBLE_RECEIPT ",outcome["records"])
                    if outcome[key]["returncode"]:
                        raise RuntimeError(key+" failed")
                outcome["replay_input_stable"]=prior.sha(saved_path)==outcome["replay_provenance"]["sha256"]
                if not outcome["replay_input_stable"]:
                    raise RuntimeError("Replay source receipt changed")
            else:
                from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
                from run_workspace.gcsim.optimizer_go_all_sources import prepare_all_set_effect_sources
                engine = load_active_gcsim_optimizer_engine_context()
                if not engine.trusted or prior.sha(Path(engine.artifact_path)) != engine.artifact_sha256:
                    raise RuntimeError("Selected engine not trusted")
                outcome["engine"] = {k:getattr(engine,k) for k in ("engine_id","engine_root","artifact_path","artifact_sha256","binding_sha256")}
                input_started=time.perf_counter()
                if args.case == "chasca":
                    req = prior.rebind_request(json.loads(prior.SOURCE.read_bytes())["original_request"],Path(engine.engine_root))
                    outcome["source_fixture"] = {"path":prior.SOURCE.relative_to(ROOT).as_posix(),"sha256":prior.sha(prior.SOURCE)}
                else:
                    from tools.experiments.gcsim.theory_bounds.inputs import load_contrast
                    req,provenance=load_contrast(args.case,job,engine)
                    outcome["input_provenance"]=provenance
                    env["GTT_BOUNDS_CONTROL_PACKAGES"]=json.dumps(provenance["saved_package_control"]["packages_by_wearer"])
                outcome["input_preparation_seconds"]=time.perf_counter()-input_started
                if len(req["stochastic"]["seeds"]) != 2:
                    raise RuntimeError("Exactly two capture members required")
                outcome["request_sha256"] = hashlib.sha256(json.dumps(req,sort_keys=True).encode()).hexdigest()
                if args.phase in ("progressive", "hybrid"):
                    known_name={"chasca":"chasca-01.json","chiori_lunar_crystallize":"chiori-03.json","bountiful_core":"bountiful-01.json"}[args.case]
                    known_path=ROOT/"docs/optimizer-evidence/2026-10-09-theory-bounds"/known_name
                    known=json.loads(known_path.read_text(encoding="utf-8"))
                    if known["status"]!="pass" or known["native_source_sha256"]!=source["sha256"] or known["engine"]!=outcome["engine"]:
                        raise ValueError("Known-witness comparison provenance differs")
                    rows=[{"label":r.get("name",r["kind"]),"candidate":r["candidate"]} for r in known["records"] if "candidate" in r]
                    prior.write_json(job/"known.json",rows)
                    env["GTT_PROGRESSIVE_KNOWN"]=str(job/"known.json")
                    outcome["known_witness_provenance"]={"path":known_path.relative_to(ROOT).as_posix(),"sha256":prior.sha(known_path),
                        "role":"post-policy and post-audit point checks only; never starts or selection", "rows":len(rows)}
                    outcome["final_solution_cache_enabled"]=False
                    if args.phase == "hybrid":
                        env.pop("GTT_BOUNDS_CONTROL_PACKAGES", None)
                        outcome["control_packages_environment_removed"]=True
                prior.write_json(job/"request.json",req)
                prep=time.perf_counter()
                prior.write_json(job/"sources.json",prepare_all_set_effect_sources(Path(engine.engine_root),req["engine"],include_neutral_rules=True))
                prior.write_json(job/"rarities.json",{s.key:s.max_rarity for s in engine.catalog.sets})
                outcome["source_preparation_seconds"]=time.perf_counter()-prep
                env.update(GTT_FEASIBLE_REQUEST=str(job/"request.json"),GTT_FEASIBLE_SOURCES=str(job/"sources.json"),
                    GTT_FEASIBLE_RARITIES=str(job/"rarities.json"),GTT_FEASIBLE_ROOT=str(job/"experiment"),
                    GTT_FEASIBLE_PHASE=args.phase,GTT_BOUNDS_CASE=args.case)
                binary=job/"bounds-tests.exe"
                outcome["compile"]=prior.run_process([str(prior.GO),"test","-c","./cmd/gtt-optimizer","-o",str(binary),"-p","2"],native,env,"FEASIBLE_RECEIPT ",outcome["records"])
                if outcome["compile"]["returncode"]:
                    raise RuntimeError("Bounds harness compilation failed")
                if args.phase in ("progressive", "hybrid"):
                    pattern="^TestHybrid" if args.phase == "hybrid" else "^TestProgressive"
                    outcome["policy_unit"]=prior.run_process([str(binary),"-test.run="+pattern,"-test.v","-test.timeout=1m"],native,env,"FEASIBLE_RECEIPT ",outcome["records"])
                    if outcome["policy_unit"]["returncode"]:
                        raise RuntimeError("Progressive gate failed before capture")
                timeout="13m" if args.phase == "hybrid" else "10m"
                outcome["search"]=prior.run_process([str(binary),"-test.run=^TestTheoryFeasibleExperiment$","-test.v","-test.timeout="+timeout],native,env,"FEASIBLE_RECEIPT ",outcome["records"])
                if outcome["search"]["returncode"]:
                    raise RuntimeError("Bounds measurement failed")
                current=load_active_gcsim_optimizer_engine_context()
                outcome["engine_stable"]=current.binding_sha256==engine.binding_sha256 and prior.sha(Path(engine.artifact_path))==engine.artifact_sha256
            outcome["scratch_bytes_before_cleanup"]=sum(p.stat().st_size for p in job.rglob("*") if p.is_file())
        outcome["inputs_stable"]=prior.native_source_identity(ROOT)["sha256"]==source["sha256"] and identity()==prototype and prior.sha(prior.INSTALLED)==consumer
        outcome["status"]="pass" if outcome["inputs_stable"] and outcome.get("engine_stable",True) else "failed_identity"
    except BaseException as exc:
        outcome["error"]=str(exc)
        raise
    finally:
        if "managed_job" in outcome:
            owned=Path(outcome["managed_job"])
            outcome["cleanup"]={"job_absent":not owned.exists(),"remaining_jobs":[p.name for p in owned.parent.glob("job-*")]}
        outcome["wall_seconds"]=time.perf_counter()-started
        receipt.parent.mkdir(parents=True,exist_ok=True)
        with receipt.open("x",encoding="utf-8") as stream:
            json.dump(outcome,stream,ensure_ascii=False,indent=2)
            stream.write("\n")
        print(json.dumps({"status":outcome["status"],"receipt":str(receipt)}),flush=True)


if __name__ == "__main__":
    main()
