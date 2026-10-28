"""Bounded preparation profiling in a managed copy; never installs native code."""
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
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from tools.experiments.gcsim.theory_bounds import run as bounds
from tools.experiments.gcsim.theory_prepare.overlay import instrument

prior = bounds.prior


def identity():
    files = {p.name: prior.sha(p) for p in sorted(HERE.iterdir()) if p.suffix in (".go", ".py")}
    material = {"files": files, "hybrid_dependency": bounds.identity()["sha256"]}
    return {**material, "sha256": hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--phase", choices=("micro",), required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
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
    result = {"kind": "theory_preparation_research_v1", "phase": args.phase, "status": "failed",
              "native_source_sha256": source["sha256"], "prototype": prototype,
              "installed_consumer_sha256": consumer, "installed_changes": False,
              "capture_calls": 0, "finalist_calls": 0, "records": [],
              "micro_guard_seconds": 90, "source_model_changed": False}
    started = time.perf_counter()
    try:
        with prior.managed_scratch() as job:
            result["managed_job"] = str(job)
            (job / "go-cache").mkdir()
            (job / "temp").mkdir()
            inherited = dict(os.environ, GOCACHE=str(job / "go-cache"), GTT_MANAGED_GO_CACHE=str(job / "go-cache"),
                             GOTMPDIR=str(job / "temp"), GTT_SCRATCH_DIR=str(job),
                             TMP=str(job / "temp"), TEMP=str(job / "temp"), PYTHONDONTWRITEBYTECODE="1")
            env = prior.managed_go.go_environment(job, inherited)
            prior.managed_go.seed_module_downloads(Path(env["GOMODCACHE"]), prior.MODULES, prior.MODULE_SHA)
            native = job / "native"
            shutil.copytree(ROOT / "native/gcsim_optimizer", native, ignore=shutil.ignore_patterns("*.exe"))
            instrument(native)
            shutil.copyfile(HERE / "profile_test.go", native / "internal/setcontext/research_prepare_test.go")
            binary = job / "prepare-tests.exe"
            result["compile"] = prior.run_process(
                [str(prior.GO), "test", "-c", "./internal/setcontext", "-o", str(binary), "-p", "2"],
                native, env, "PREP_RECEIPT ", result["records"])
            if result["compile"]["returncode"]:
                raise RuntimeError("Preparation profile compilation failed")
            result["micro"] = prior.run_process(
                [str(binary), "-test.run=^TestPrepare|^TestNeutral",
                 "-test.v", "-test.timeout=90s"], native, env, "PREP_RECEIPT ", result["records"])
            if result["micro"]["returncode"]:
                raise RuntimeError("Preparation profile/gates failed")
            result["scratch_bytes_before_cleanup"] = sum(p.stat().st_size for p in job.rglob("*") if p.is_file())
        result["inputs_stable"] = (prior.native_source_identity(ROOT)["sha256"] == source["sha256"]
                                   and identity() == prototype and prior.sha(prior.INSTALLED) == consumer)
        result["status"] = "pass" if result["inputs_stable"] else "failed_identity"
    except BaseException as exc:
        result["error"] = str(exc)
        raise
    finally:
        if "managed_job" in result:
            owned = Path(result["managed_job"])
            result["cleanup"] = {"job_absent": not owned.exists(),
                                 "remaining_jobs": [p.name for p in owned.parent.glob("job-*")]}
        result["wall_seconds"] = time.perf_counter() - started
        receipt.parent.mkdir(parents=True, exist_ok=True)
        with receipt.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps({"status": result["status"], "receipt": str(receipt)}), flush=True)


if __name__ == "__main__":
    main()
