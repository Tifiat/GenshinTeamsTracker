"""Capture-free completion of the two Stage16 trace-parser fixtures."""
from __future__ import annotations
import argparse,json,os,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
from tools.experiments.gcsim.theory_release import package_io as io,release as source
from tools.experiments.gcsim.theory_full_output.run import pins
EVIDENCE=ROOT/"docs/optimizer-evidence/2026-10-11-theory-goblet-controls"
TARGET=ROOT/"docs/optimizer-evidence/2026-10-11-theory-target"
MAIN=Path("C:/Users/user/Desktop/GenshinTeamsTracker")
GO=Path("C:/Program Files/Go/bin/go.exe")
def canonical(v):return json.dumps(v,sort_keys=True,separators=(",",":")).encode()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument("--receipt",required=True);args=p.parse_args()
 if Path(args.receipt).name!=args.receipt or not args.receipt.endswith(".json"):p.error("new evidence filename")
 target=EVIDENCE/args.receipt
 if target.exists():raise FileExistsError(target)
 initial=json.loads((EVIDENCE/"initial.json").read_bytes());prepared=json.loads((EVIDENCE/"preparation-pins.json").read_bytes())
 pins(initial);manifest=json.loads((TARGET/"package/manifest.json").read_bytes())
 result={"schema_kind":"gtt_theory_goblet_controls_fixture_verification_v1","status":"FAIL","engine_calls":0,
         "reason":"study fixture selector matched six allocation tests but excluded TestParseStage16Trace names",
         "study_unchanged":True,"checks":[]};lifecycle=None;started=time.monotonic()
 try:
  with source.optimizer_slot(ROOT/".codex_tmp/managed-optimizer"),io.managed_job(ROOT/".codex_tmp/theory-full-output") as lifecycle:
   job=lifecycle["path"];assembly=job/"assembly"
   records=io.materialize_from_manifest(MAIN,manifest,TARGET/"package/combined",assembly)
   digest=io.sha_bytes(canonical(records))
   if len(records)!=initial["expected_core_assembly_files"] or digest!=initial["expected_core_assembly_sha256"]:raise ValueError("frozen target differs")
   for name in ("temp","go-cache","go-mod"):(job/name).mkdir()
   env=dict(os.environ)
   for key in list(env):
    if key.startswith("GTT_STAGE"):env.pop(key,None)
   env.update(manifest["go_build_environment"],GOROOT=str(GO.parent.parent),GOPROXY="off",GOSUMDB="off",GOTOOLCHAIN="local",GOWORK="off",
              TEMP=str(job/"temp"),TMP=str(job/"temp"),GOTMPDIR=str(job/"temp"),GOCACHE=str(job/"go-cache"),GOMODCACHE=str(job/"go-mod"))
   native=assembly/"native/gcsim_optimizer";identities={}
   for name in ("diagnostic.go","diagnostic_test.go"):
    body=(HERE/name).read_bytes();sha=io.sha_bytes(body)
    rel=(HERE/name).relative_to(ROOT).as_posix()
    if sha!=prepared["harness"][rel]:raise ValueError("actual study parser source changed")
    (native/"internal/engineclient"/("stage16_"+name)).write_bytes(body);identities[rel]=sha
   raw=source.run([str(GO),"test","-json","-count=1","-p=2","-run","^TestParseStage16Trace","./internal/engineclient"],native,env,120)
   check=source.go_receipt(raw)
   if raw["exit_code"]:check["failed_process_stdout"]=raw["stdout"]
   result["checks"].append(check);result["parser_files"]=identities;result["core_assembly_sha256"]=digest
   if check["exit_code"] or check["skips"] or check["top_level_passes"]!=2:raise ValueError("exact two trace parser fixtures did not pass")
   for path,row in records.items():
    if io.sha_bytes((assembly/path).read_bytes())!=row["after_sha256"]:raise ValueError("fixture changed frozen target")
   result["status"]="PASS_TWO_TRACE_PARSER_FIXTURES_NO_ENGINE"
 except Exception as exc:result["error"]=f"{type(exc).__name__}: {exc}";result["traceback"]=traceback.format_exc()
 finally:
  result["seconds_including_compile"]=time.monotonic()-started
  result["cleanup"]={k:str(v) if isinstance(v,Path) else v for k,v in (lifecycle or {}).items()}
  try:pins(initial);result["all_preservation_pins_unchanged"]=True
  except Exception as exc:result["pin_error"]=str(exc);result["status"]="FAIL"
  if not result["cleanup"].get("cleaned"):result["status"]="FAIL"
  target.write_bytes(json.dumps(result,sort_keys=True,indent=2).encode()+b"\n")
 print(json.dumps({"status":result["status"],"engine_calls":0,"error":result.get("error"),"cleanup":result["cleanup"]}),flush=True)
 return 0 if result["status"].startswith("PASS_") else 1
if __name__=="__main__":raise SystemExit(main())

