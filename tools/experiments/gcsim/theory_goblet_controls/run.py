"""One leased Stage16 six-case study; immutable preparation precedes one run."""
from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from tools.experiments.gcsim.theory_release import package_io as io, release as source
from tools.experiments.gcsim.theory_full_output.run import pins
from tools.experiments.gcsim.theory_goblet_controls.projection import project_trace

EVIDENCE = ROOT / "docs/optimizer-evidence/2026-10-11-theory-goblet-controls"
TARGET = ROOT / "docs/optimizer-evidence/2026-10-11-theory-target"
PRIOR = ROOT / "docs/optimizer-evidence/2026-10-11-theory-real-output"
OLD = ROOT / "tools/experiments/gcsim/theory_full_output"
PYTHON = Path("C:/Users/user/Desktop/GenshinTeamsTracker/.venv/Scripts/python.exe")
GO = Path("C:/Program Files/Go/bin/go.exe")
MAIN = Path("C:/Users/user/Desktop/GenshinTeamsTracker")
TEST = "tests/tools/test_theory_goblet_controls_public.py"

def object_file(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def canonical(value) -> bytes:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def identity() -> dict:
    paths = sorted(p for p in HERE.iterdir() if p.suffix in (".go",".py"))
    paths += [ROOT/TEST, OLD/"prepare.py", OLD/"guard.go", EVIDENCE/"PROTOCOL.md",
              EVIDENCE/"initial.json", EVIDENCE/"archive-comparison.json", EVIDENCE/"source-proc-audit.json"]
    return {p.relative_to(ROOT).as_posix():io.sha_bytes(p.read_bytes()) for p in paths}

def write_evidence(name: str,body: bytes) -> dict:
    if Path(name).name != name or not name.endswith(".json"):
        raise ValueError("invalid Stage16 evidence filename")
    target = EVIDENCE/name
    for path in (*reversed(target.parents),target):
        if path.exists() or path.is_symlink():
            row=path.lstat()
            if stat.S_ISLNK(row.st_mode) or getattr(row,"st_file_attributes",0)&0x400:
                raise ValueError("linked evidence path")
    with target.open("xb") as stream: stream.write(body)
    if target.read_bytes()!=body: raise ValueError("public evidence changed during export")
    return {"path":name,"bytes":len(body),"sha256":io.sha_bytes(body)}

def process(argv,cwd,env,timeout):
    return source.run([str(x) for x in argv],cwd,env,timeout)

def freeze_public(job,result):
    public=job/"packet/public"
    result.setdefault("retained_public_files",[])
    result.setdefault("documentary_public_files",[])
    if not public.exists(): return
    for path in sorted(public.iterdir()):
        if path.suffix!=".json" or not path.is_file() or path.is_symlink():
            raise ValueError("unexpected Stage16 public output")
        record=write_evidence(path.name,path.read_bytes())
        result["retained_public_files" if path.name=="comparison.json" else "documentary_public_files"].append(record)
    diagnostic=public/"diagnostic-results.json"
    if diagnostic.exists():
        projections=[]
        for row in object_file(diagnostic):
            measured=row["result"]
            if row["status"]!="PASS": continue
            raw_path=Path(measured["ResultPath"]).resolve()
            if not raw_path.is_relative_to(job.resolve()) or not raw_path.is_file():
                raise ValueError("raw diagnostic path escapes owned job")
            raw_bytes=raw_path.read_bytes()
            if io.sha_bytes(raw_bytes)!=measured["ResultSHA256"]:
                raise ValueError("raw trace changed before projection")
            projected=project_trace(json.loads(raw_bytes))
            projected.update(case=row["case"],seed=row["seed"],raw_result_sha256=measured["ResultSHA256"],raw_result_bytes=len(raw_bytes))
            if abs(projected["damage"]["actual_dps"]-measured["DPS"])>1e-7*(1+abs(measured["DPS"])):
                raise ValueError("trace projection/Go ordinary scalar mismatch")
            projections.append(projected)
        # Source-defined gameplay invariants outside the artifact delta.
        if projections:
            orders={tuple(row["character_key"] for row in p["identity"]["actor_order"]) for p in projections}
            targets={p["identity"]["target_sha256"] for p in projections}
            actions={p["identity"]["compiled_action_sha256"] for p in projections}
            if orders!={("furina","xilonen","chiori","columbina")} or len(targets)!=1 or len(actions)!=1:
                raise ValueError("paired diagnostics changed declaration/actions/target")
        record=write_evidence("proc-evidence.json",canonical({"schema_kind":"gtt_theory_stage16_runtime_proc_v1","members":projections})+b"\n")
        result["retained_public_files"].append(record)
        result["diagnostic_projection_members"]=len(projections)

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt",required=True)
    args=parser.parse_args()
    if Path(args.receipt).name!=args.receipt or not args.receipt.endswith(".json"):parser.error("new evidence filename required")
    if (EVIDENCE/args.receipt).exists():raise FileExistsError(args.receipt)
    initial=object_file(EVIDENCE/"initial.json")
    if (EVIDENCE/"capture-entry.json").exists():raise ValueError("Stage16 budget closed; no repeat study or engine call")
    pins(initial)
    harness=identity()
    manifest=object_file(TARGET/"package/manifest.json")
    if io.sha_bytes((TARGET/"package/manifest.json").read_bytes())!=initial["target_manifest_sha256"]:raise ValueError("target manifest changed")
    if initial["dependency_runtime"]!={"python_sha256":io.sha_bytes(PYTHON.read_bytes()),"go_sha256":io.sha_bytes(GO.read_bytes())}:raise ValueError("runtimes changed")
    result={"schema_kind":"gtt_theory_goblet_controls_validation_v1","date":"2026-10-11","status":"FAIL","worker_head":initial["worker_head"],
            "harness":harness,"checks":[],"capture_reserved":0,"capture_attempts":0,"ordinary_diagnostic_attempts":0,"study_invocations":0,
            "installed":False,"transfer":False,"merge":False}
    lifecycle=None;job=None;exported=False;prep_started=time.monotonic()
    try:
        with source.optimizer_slot(ROOT/".codex_tmp/managed-optimizer"), io.managed_job(ROOT/".codex_tmp/theory-full-output") as lifecycle:
            job=lifecycle["path"];assembly=job/"assembly"
            records=io.materialize_from_manifest(MAIN,manifest,TARGET/"package/combined",assembly)
            digest=io.sha_bytes(canonical(records))
            if len(records)!=initial["expected_core_assembly_files"] or digest!=initial["expected_core_assembly_sha256"]:raise ValueError("original Stage14 target changed")
            result.update(core_assembly_files=len(records),core_assembly_sha256=digest)
            original={path:row["after_sha256"] for path,row in records.items()}
            for name in ("temp","go-cache","go-mod","rule-cache","bundled-cache"):(job/name).mkdir()
            env=dict(os.environ)
            for key in list(env):
                if key.startswith("GTT_STAGE15") or key.startswith("GTT_STAGE16") or key in ("PYTHONPATH","PYTHONHOME","GTT_RULE_SOURCE_BUNDLE","GTT_ENGINE_ROOT","GTT_RUN_ROOT"):env.pop(key,None)
            env.update(manifest["go_build_environment"],GOROOT=str(GO.parent.parent),GOPROXY="off",GOSUMDB="off",GOTOOLCHAIN="local",GOWORK="off",
                       TEMP=str(job/"temp"),TMP=str(job/"temp"),GOTMPDIR=str(job/"temp"),GOCACHE=str(job/"go-cache"),GOMODCACHE=str(job/"go-mod"),
                       GTT_RULE_CACHE_DIR=str(job/"rule-cache"),GTT_BUNDLED_CACHE_DIR=str(job/"bundled-cache"),
                       PYTHONDONTWRITEBYTECODE="1",PYTHONIOENCODING="utf-8",QT_QPA_PLATFORM="offscreen")
            native=assembly/"native/gcsim_optimizer";binary=job/"standard.exe"
            check=process([GO,"build","-trimpath","-p=2","-o",binary,"./cmd/gtt-optimizer"],native,env,180);result["checks"].append(check)
            if check["exit_code"] or io.sha_bytes(binary.read_bytes())!=initial["expected_standard_binary_sha256"]:raise ValueError("standard frozen target binary differs")
            result["standard_binary_sha256"]=io.sha_bytes(binary.read_bytes())
            mapping={"constrained.go":"internal/theoryalloc/stage16_constrained.go","constrained_test.go":"internal/theoryalloc/stage16_constrained_test.go",
                     "diagnostic.go":"internal/engineclient/stage16_diagnostic.go","diagnostic_test.go":"internal/engineclient/stage16_diagnostic_test.go",
                     "render.go":"internal/finalists/stage16_render.go","input.go":"cmd/gtt-optimizer/stage16_input.go","study_test.go":"cmd/gtt-optimizer/stage16_study_test.go"}
            for name,target in mapping.items():
                p=native/target
                if p.exists():raise ValueError("diagnostic collision:"+target)
                p.write_bytes((HERE/name).read_bytes())
            (native/"internal/theorysearch/stage16_guard.go").write_bytes((OLD/"guard.go").read_bytes())
            prep=process([PYTHON,"-I","-B",OLD/"prepare.py","--assembly",assembly,"--repo",ROOT,"--job",job],assembly,env,180);result["checks"].append(prep)
            if prep["exit_code"]:raise ValueError("capture-free frozen preparation failed")
            baseline_family=object_file(EVIDENCE/"archive-comparison.json")["cases"][0]["archived_row_family"]
            archived=json.loads(gzip.decompress((PRIOR/"terminal-archive.json.gz").read_bytes()))
            baseline=next(row["witness45"] for row in archived["families"] if row["family"]==baseline_family)
            (job/"baseline-state.json").write_bytes(canonical(baseline)+b"\n")
            env.update(GTT_STAGE16_REQUEST=str(job/"request.json"),GTT_STAGE16_SOURCES=str(job/"sources.json"),GTT_STAGE16_BASELINE=str(job/"baseline-state.json"),GTT_STAGE16_ROOT=str(job/"packet"))
            raw=process([GO,"test","-json","-count=1","-p=2","-run","^(TestRunConstrained|TestConstrained|TestStage16|TestParseStage16Trace)","./internal/theoryalloc","./internal/engineclient"],native,env,120)
            check=source.go_receipt(raw)
            if raw["exit_code"]:check["failed_process_stdout"]=raw["stdout"]
            result["checks"].append(check)
            if check["exit_code"] or check["skips"]:raise ValueError("new allocation/diagnostic fixture controls failed")
            pycode="import sys,unittest;sys.path.insert(0,sys.argv[1]);s=unittest.defaultTestLoader.loadTestsFromName('tests.tools.test_theory_goblet_controls_public');r=unittest.TextTestRunner(verbosity=2).run(s);sys.exit(not r.wasSuccessful())"
            check=process([PYTHON,"-I","-B","-c",pycode,ROOT],ROOT,env,120);result["checks"].append(check)
            if check["exit_code"]:raise ValueError("public projection/retention fixture controls failed")
            packet=job/"packet.exe"
            check=process([GO,"test","-c","-trimpath","-p=2","-o",packet,"./cmd/gtt-optimizer"],native,env,180);result["checks"].append(check)
            if check["exit_code"]:raise ValueError("Stage16 diagnostic test binary compile failed")
            check=process([packet,"-test.run=^TestStage16PreparedInputs$","-test.v","-test.timeout=60s"],native,env,70);result["checks"].append(check)
            if check["exit_code"]:raise ValueError("native six-case input preflight failed")
            native_rows=[json.loads(line.split(" ",1)[1]) for line in check["stdout"].splitlines() if line.startswith("STAGE16_RECEIPT ")]
            if len(native_rows)!=1:raise ValueError("native preflight receipt missing")
            for path,sha in original.items():
                if io.sha_bytes((assembly/path).read_bytes())!=sha:raise ValueError("diagnostic changed original target:"+path)
            pins(initial)
            if identity()!=harness:raise ValueError("harness changed during preparation")
            prepared={"schema_kind":"gtt_theory_goblet_controls_prepared_v1","core_assembly_sha256":digest,"standard_binary_sha256":result["standard_binary_sha256"],
                      "instrumented_test_binary_sha256":io.sha_bytes(packet.read_bytes()),"harness":harness,"native_preflight":native_rows[0],
                      "python_preparation":object_file(job/"prep-provenance.json"),"request_file_sha256":io.sha_bytes((job/"request.json").read_bytes()),
                      "source_file_sha256":io.sha_bytes((job/"sources.json").read_bytes()),"capture_spent":0,"ordinary_spent":0,"capture_maximum":2,"ordinary_maximum":12,"universes":1,"job":str(job)}
            prepared_sha=io.sha_bytes(canonical(prepared))
            result["preparation"]=prepared;result["compile_prep_validation_seconds"]=time.monotonic()-prep_started
            (job/"prepared-pins.json").write_bytes(canonical(prepared)+b"\n")
            print("STAGE16_PREPARED "+json.dumps({"sha256":prepared_sha,"pins_file":str(job/"prepared-pins.json"),"job":str(job)},sort_keys=True),flush=True)
            line=sys.stdin.readline().strip()
            if line!="STAGE16_GO "+prepared_sha or object_file(EVIDENCE/"preparation-pins.json")!=prepared:raise ValueError("exact frozen preparation/run signal missing")
            pins(initial)
            if identity()!=harness:raise ValueError("prepared harness changed")
            if (EVIDENCE/"capture-entry.json").exists():raise ValueError("prior Stage16 invocation blocks every retry")
            write_evidence("capture-entry.json",canonical({"prepared_sha256":prepared_sha,"capture_reserved":2,"ordinary_reserved":12,"universes":1,"seeds":[742031889,742031890],"attempts_include_failures":True})+b"\n")
            result.update(capture_reserved=2,study_invocations=1,capture_attempts=None,ordinary_diagnostic_attempts=None)
            env["GTT_STAGE16_RUN"]="authorized-one-universe-six-controls";study_started=time.monotonic()
            try:
                check=process([packet,"-test.run=^TestStage16SixControls$","-test.v","-test.timeout=910s"],native,env,900)
                result["checks"].append(check)
            finally:
                ledger=job/"packet/public/study-ledger.json"
                if ledger.exists():
                    result["native_ledger"]=object_file(ledger)
                    result["capture_attempts"]=result["native_ledger"]["capture_attempts"]
                    result["ordinary_diagnostic_attempts"]=result["native_ledger"]["ordinary_diagnostic_attempts"]
                output_started=time.monotonic()
                freeze_public(job,result);exported=True
                result["python_output_seconds"]=time.monotonic()-output_started
                result["outer_including_python_output_seconds"]=time.monotonic()-study_started
            ledger=result.get("native_ledger",{})
            if check["exit_code"] or ledger.get("status")!="PASS_SIX_CONTROLS_ONE_UNIVERSE" or result["capture_attempts"]!=2 or result["ordinary_diagnostic_attempts"]!=12:raise ValueError("sole six-control study incomplete; no retry")
            if result["outer_including_python_output_seconds"]>900 or ledger["clocks_seconds"]["offline_native"]+result["python_output_seconds"]>480:raise ValueError("hard clock exceeded during compact output")
            for path,sha in original.items():
                if io.sha_bytes((assembly/path).read_bytes())!=sha:raise ValueError("study changed original target:"+path)
            result["status"]="PASS_SIX_CONTROLS_ONE_UNIVERSE"
    except Exception as exc:
        result["error"]=f"{type(exc).__name__}: {exc}";result["traceback"]=traceback.format_exc()
    finally:
        result["cleanup"]={key:str(value) if isinstance(value,Path) else value for key,value in (lifecycle or {}).items()}
        try:pins(initial);result["all_preservation_pins_unchanged"]=True
        except Exception as exc:result["pin_error"]=str(exc);result["status"]="FAIL"
        if not result["cleanup"].get("cleaned"):result["status"]="FAIL"
        result["public_export_completed"]=exported
        write_evidence(args.receipt,json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False).encode()+b"\n")
    print("STAGE16_FINAL "+json.dumps({"status":result["status"],"capture_attempts":result["capture_attempts"],"ordinary_diagnostic_attempts":result["ordinary_diagnostic_attempts"],"error":result.get("error"),"cleanup":result["cleanup"]}),flush=True)
    return 0 if result["status"].startswith("PASS_") else 1

if __name__=="__main__":raise SystemExit(main())

