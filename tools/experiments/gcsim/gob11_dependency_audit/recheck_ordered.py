"""Repeat stat probes without changing character first-declaration order.

Requires baseline captures from the SAME isolated engine. Existing output is
never overwritten. A prepended add-stats line can create a character early
in GCSIM and change party initialization/RNG; it is not a valid stat-only probe.
"""
from pathlib import Path
import argparse
import json
import re
import shutil
import subprocess
import time

p = argparse.ArgumentParser(__doc__)
p.add_argument("--matrix", type=Path, required=True)
p.add_argument("--engine", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
args = p.parse_args()
args.out.mkdir(exist_ok=False)
jobs = json.loads((args.matrix / "jobs.json").read_text())
for job in jobs:
    job.pop("error", None)
    job.pop("capture_seconds", None)
    for name in (job["config"], job["request"]):
        shutil.copy2(args.matrix / name, args.out / name)
    if job["baseline"]:
        shutil.copy2(args.matrix / job["output"], args.out / job["output"])
        job["reused_same_engine_baseline"] = True
        continue
    changed = (args.matrix / job["config"]).read_text(encoding="utf-8")
    line, remainder = changed.split("\n", 1)
    assert re.fullmatch(r"\w+ add stats [\w%]+=[-\d.]+;", line), line
    baseline = (args.matrix / (job["case"] + ".txt")).read_text(encoding="utf-8")
    assert remainder == baseline, "Unexpected prior mutation shape"
    (args.out / job["config"]).write_text(baseline + "\n" + line + "\n", encoding="utf-8")
    started = time.monotonic()
    proc = subprocess.run([str(args.engine), "-c", str(args.out / job["config"]), "-out", str(args.out / job["output"]), "-gtt-trace-equation", str(args.out / job["request"])], capture_output=True, text=True, timeout=120)
    job["capture_seconds"] = time.monotonic() - started
    if proc.returncode:
        job["error"] = (proc.stdout + proc.stderr)[-2000:]
    print(job["config"], job.get("error", "captured"), flush=True)
    (args.out / "jobs.json").write_text(json.dumps(jobs, indent=2), encoding="utf-8")
