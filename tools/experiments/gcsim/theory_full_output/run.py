"""One leased Stage15 target study; capture waits for frozen preparation evidence."""
from __future__ import annotations

import argparse
import gzip
import hashlib
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

EVIDENCE = ROOT / "docs/optimizer-evidence/2026-10-11-theory-real-output"
TARGET = ROOT / "docs/optimizer-evidence/2026-10-11-theory-target"
PYTHON = Path("C:/Users/user/Desktop/GenshinTeamsTracker/.venv/Scripts/python.exe")
GO = Path("C:/Program Files/Go/bin/go.exe")
MAIN = Path("C:/Users/user/Desktop/GenshinTeamsTracker")
TABLE_TEST = "tests/tools/test_theory_full_output_table.py"
STORAGE_TEST = "tests/tools/test_theory_full_output_storage.py"


def object_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def identity() -> dict:
    paths = sorted(p for p in HERE.iterdir() if p.suffix in (".go", ".py"))
    paths += [ROOT / TABLE_TEST, ROOT / STORAGE_TEST, EVIDENCE / "PROTOCOL.md"]
    return {p.relative_to(ROOT).as_posix(): io.sha_bytes(p.read_bytes()) for p in paths}


def pins(initial: dict) -> None:
    if source.git(ROOT, "rev-parse", "HEAD").decode().strip() != initial["worker_head"]:
        raise ValueError("Stage15 source HEAD changed")
    if source.git(MAIN, "rev-parse", "HEAD").decode().strip() != initial["target_head"]:
        raise ValueError("Stage15 target HEAD changed")
    for path, row in initial["target_source_snapshot"].items():
        target = MAIN / path
        body = target.read_bytes() if target.is_file() else b""
        if target.is_file() != row["exists"] or io.sha_bytes(body) != row["raw_sha256"]:
            raise ValueError("target source changed: " + path)
    for field in ("worker_runtime_account_raw_sha256", "worker_prior147_raw_sha256"):
        for path, digest in initial[field].items():
            if io.sha_bytes((ROOT / path).read_bytes()) != digest:
                raise ValueError("preserved Worker2 input changed: " + path)


def write_evidence(name: str, body: bytes) -> dict:
    if Path(name).name != name or not name.endswith((".json", ".json.gz", ".csv", ".tsv", ".md")):
        raise ValueError("invalid public evidence filename")
    target = EVIDENCE / name
    for path in (*reversed(target.parents), target):
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("linked public evidence path")
    with target.open("xb") as stream:
        stream.write(body)
    if target.read_bytes() != body:
        raise ValueError("public export changed while writing")
    return {"path": name, "bytes": len(body), "sha256": io.sha_bytes(body)}


def freeze_public(job: Path, result: dict, assembly: Path) -> None:
    public = job / "packet/public"
    records = result.setdefault("retained_public_files", [])
    if not public.exists():
        return
    for path in sorted(public.iterdir()):
        if path.suffix != ".json" or not path.is_file() or path.is_symlink():
            raise ValueError("unexpected public study output")
        body = path.read_bytes()
        packed = gzip.compress(body, compresslevel=6, mtime=0)
        if gzip.decompress(packed) != body:
            raise ValueError("lossless public compression roundtrip failed")
        row = write_evidence(path.name + ".gz", packed)
        row.update(raw_bytes=len(body), raw_sha256=io.sha_bytes(body), gzip_roundtrip=True)
        records.append(row)
    terminal = public / "terminal-snapshot.json"
    candidates = [public / (name + "-snapshot.json") for name in ("deep", "breadth", "first")]
    selected = terminal if terminal.exists() else next((p for p in candidates if p.exists()), None)
    if selected is None:
        result["table_available"] = False
        return
    # Import the already tested pure seam with production transport from target.
    sys.path.insert(0, str(assembly))
    spec = importlib.util.spec_from_file_location("stage15_table_export", HERE / "table.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    snapshot = object_file(selected)
    report = module.build_theory_full_output(snapshot, team_key="chiori_lunar_crystallize_theory",
        wearer_names={"furina": "Фурина", "xilonen": "Шилонен", "chiori": "Тиори", "columbina": "Колумбина"},
        set_names=object_file(job / "set-labels.json"),
        public_context={"energy_mode": "infinite", "prediction_status": "formula_model_only_no_ordinary_finalists",
                        "stage15_status": result.get("native_ledger", {}).get("status", "FAIL"),
                        "proc_facts": [], "execution": "diagnostic_target_product_session;not_installed_cli_or_physical_ui"})
    rendered = module.render_theory_full_output(report)
    for key, name in (("json", "full-table.json.gz"), ("csv", "full-table.csv"), ("grouped_options_tsv", "grouped-options.tsv"), ("summary_ru", "TABLE_SUMMARY_RU.md")):
        raw = rendered[key].encode("utf-8")
        if name.endswith(".gz"):
            packed = gzip.compress(raw, compresslevel=6, mtime=0)
            if gzip.decompress(packed) != raw or json.loads(raw) != report:
                raise ValueError("table lossless roundtrip failed")
            row = write_evidence(name, packed)
            row.update(raw_bytes=len(raw), raw_sha256=io.sha_bytes(raw), gzip_roundtrip=True)
        else:
            row = write_evidence(name, raw)
        records.append(row)
    result["table_available"] = True
    result["table_counts"] = report["roundtrip_counts"]
    result["table_snapshot"] = selected.name


def process(argv: list[str], cwd: Path, env: dict, timeout: int) -> dict:
    return source.run(argv, cwd, env, timeout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()
    if Path(args.receipt).name != args.receipt or not args.receipt.endswith(".json"):
        parser.error("receipt must be a new evidence filename")
    if (EVIDENCE / args.receipt).exists():
        raise FileExistsError(args.receipt)
    initial = object_file(EVIDENCE / "initial.json")
    pins(initial)
    harness = identity()
    manifest_raw = (TARGET / "package/manifest.json").read_bytes()
    if io.sha_bytes(manifest_raw) != initial["target_manifest_sha256"]:
        raise ValueError("target manifest changed")
    manifest = json.loads(manifest_raw)
    if initial["dependency_runtime"] != {"python_sha256": io.sha_bytes(PYTHON.read_bytes()), "go_sha256": io.sha_bytes(GO.read_bytes())}:
        raise ValueError("dependency runtimes changed")
    result = {"schema_kind": "gtt_theory_real_full_output_validation_v1", "date": "2026-10-11", "status": "FAIL",
              "worker_head": initial["worker_head"], "target_manifest_sha256": io.sha_bytes(manifest_raw), "harness": harness,
              "checks": [], "capture_reserved": 0, "capture_attempts": 0, "ordinary_finalists": 0, "study_invocations": 0,
              "installed": False, "transfer": False, "merge": False}
    lifecycle = None
    job = None
    assembly = None
    exported = False
    try:
        with source.optimizer_slot(ROOT / ".codex_tmp/managed-optimizer"), io.managed_job(ROOT / ".codex_tmp/theory-full-output") as lifecycle:
            job = lifecycle["path"]
            assembly = job / "assembly"
            records = io.materialize_from_manifest(MAIN, manifest, TARGET / "package/combined", assembly)
            digest = io.sha_bytes(json.dumps(records, sort_keys=True, separators=(",", ":")).encode())
            if len(records) != initial["expected_core_assembly_files"] or digest != initial["expected_core_assembly_sha256"]:
                raise ValueError("Stage15 original target assembly changed")
            result["core_assembly_sha256"] = digest
            result["core_assembly_files"] = len(records)
            original_files = {path: row["after_sha256"] for path, row in records.items()}
            for name in ("temp", "go-cache", "go-mod", "rule-cache", "bundled-cache"):
                (job / name).mkdir()
            env = dict(os.environ)
            for key in ("PYTHONPATH", "PYTHONHOME", "GTT_RULE_SOURCE_BUNDLE", "GTT_THEORY_OUTPUT_EXPORT", "GTT_ENGINE_ROOT", "GTT_RUN_ROOT", "GTT_STAGE15_RUN"):
                env.pop(key, None)
            env.update(manifest["go_build_environment"], GOROOT=str(GO.parent.parent), GOPROXY="off", GOSUMDB="off", GOTOOLCHAIN="local", GOWORK="off",
                       TEMP=str(job / "temp"), TMP=str(job / "temp"), GOTMPDIR=str(job / "temp"), GOCACHE=str(job / "go-cache"), GOMODCACHE=str(job / "go-mod"),
                       GTT_RULE_CACHE_DIR=str(job / "rule-cache"), GTT_BUNDLED_CACHE_DIR=str(job / "bundled-cache"),
                       PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", QT_QPA_PLATFORM="offscreen")
            native = assembly / "native/gcsim_optimizer"
            binary = job / "standard.exe"
            check = process([str(GO), "build", "-trimpath", "-p=2", "-o", str(binary), "./cmd/gtt-optimizer"], native, env, 180)
            result["checks"].append(check)
            if check["exit_code"] or io.sha_bytes(binary.read_bytes()) != initial["expected_standard_binary_sha256"]:
                raise ValueError("standard target build differs from accepted Stage14 binary")
            result["standard_binary_sha256"] = io.sha_bytes(binary.read_bytes())
            mapping = {"observer.go": "internal/theorysearch/stage15_observer.go", "observer_test.go": "internal/theorysearch/stage15_observer_test.go",
                       "guard.go": "internal/theorysearch/stage15_guard.go", "guard_test.go": "internal/theorysearch/stage15_guard_test.go",
                       "study_test.go": "cmd/gtt-optimizer/stage15_study_test.go"}
            for name, target in mapping.items():
                path = native / target
                if path.exists():
                    raise ValueError("diagnostic file collides with target")
                path.write_bytes((HERE / name).read_bytes())
            python_folder = assembly / "tools/experiments/gcsim/theory_full_output"
            python_folder.mkdir(parents=True)
            for name in ("table.py", "prepare.py", "storage.py"):
                (python_folder / name).write_bytes((HERE / name).read_bytes())
            (assembly / TABLE_TEST).write_bytes((ROOT / TABLE_TEST).read_bytes())
            (assembly / STORAGE_TEST).write_bytes((ROOT / STORAGE_TEST).read_bytes())
            prep = process([str(PYTHON), "-I", "-B", str(HERE / "prepare.py"), "--assembly", str(assembly), "--repo", str(ROOT), "--job", str(job)], assembly, env, 180)
            result["checks"].append(prep)
            if prep["exit_code"]:
                raise ValueError("capture-free frozen-target preparation failed")
            prep_provenance = object_file(job / "prep-provenance.json")
            env.update(GTT_STAGE15_REQUEST=str(job / "request.json"), GTT_STAGE15_SOURCES=str(job / "sources.json"), GTT_STAGE15_ROOT=str(job / "packet"))
            probe_raw = process([str(GO), "test", "-json", "-count=1", "-p=2", "-run", "^TestStage15", "./internal/theorysearch"], native, env, 120)
            probe = source.go_receipt(probe_raw)
            # Go 1.26 build errors use build-output events without Test names.
            # Retain diagnostics even when no test could start.
            if probe_raw["exit_code"]:
                probe["failed_process_stdout"] = probe_raw["stdout"]
            result["checks"].append(probe)
            if probe["exit_code"] or probe["skips"]:
                raise ValueError("new capture-free observer/guard controls failed")
            py_code = "import sys,unittest;sys.path.insert(0,sys.argv[1]);s=unittest.defaultTestLoader.loadTestsFromNames(['tests.tools.test_theory_full_output_table','tests.tools.test_theory_full_output_storage']);r=unittest.TextTestRunner(verbosity=2).run(s);sys.exit(not r.wasSuccessful())"
            check = process([str(PYTHON), "-I", "-B", "-c", py_code, str(assembly)], assembly, env, 120)
            result["checks"].append(check)
            if check["exit_code"]:
                raise ValueError("new lossless table seam failed")
            packet = job / "packet.exe"
            check = process([str(GO), "test", "-c", "-trimpath", "-p=2", "-o", str(packet), "./cmd/gtt-optimizer"], native, env, 180)
            result["checks"].append(check)
            if check["exit_code"]:
                raise ValueError("diagnostic test binary compilation failed")
            preflight = process([str(packet), "-test.run=^TestStage15PreparedTargetInputs$", "-test.v", "-test.timeout=60s"], native, env, 70)
            result["checks"].append(preflight)
            if preflight["exit_code"]:
                raise ValueError("native raw/expanded request/default domain preflight failed")
            native_rows = [json.loads(line.split(" ", 1)[1]) for line in preflight["stdout"].splitlines() if line.startswith("STAGE15_RECEIPT ")]
            if len(native_rows) != 1:
                raise ValueError("exact native preflight record missing")
            for path, sha in original_files.items():
                if io.sha_bytes((assembly / path).read_bytes()) != sha:
                    raise ValueError("diagnostic altered original target file: " + path)
            pins(initial)
            if identity() != harness:
                raise ValueError("harness changed during preparation")
            prepared = {"schema_kind": "gtt_theory_real_output_prepared_v1", "core_assembly_sha256": digest,
                        "standard_binary_sha256": result["standard_binary_sha256"], "instrumented_test_binary_sha256": io.sha_bytes(packet.read_bytes()),
                        "harness": harness, "native_preflight": native_rows[0], "python_preparation": prep_provenance,
                        "request_file_sha256": io.sha_bytes((job / "request.json").read_bytes()), "source_file_sha256": io.sha_bytes((job / "sources.json").read_bytes()),
                        "capture_spent": 0, "expected_seed_members": 2, "model_universes": 1, "ordinary_finalists": 0, "job": str(job)}
            prepared_sha = io.sha_bytes(canonical(prepared))
            result["preparation"] = prepared
            prepared_file = job / "prepared-pins.json"
            prepared_file.write_bytes(canonical(prepared) + b"\n")
            print("STAGE15_PREPARED " + json.dumps({"sha256": prepared_sha, "pins_file": str(prepared_file), "job": str(job)}, sort_keys=True), flush=True)
            # Parent saves exact pins with apply_patch; this is an internal gate,
            # not a request for a second human authorization.
            line = sys.stdin.readline().strip()
            frozen = object_file(EVIDENCE / "preparation-pins.json")
            if line != "STAGE15_GO " + prepared_sha or frozen != prepared:
                raise ValueError("exact preparation evidence/one-run signal missing")
            pins(initial)
            if identity() != harness:
                raise ValueError("prepared harness changed before capture")
            if (EVIDENCE / "capture-entry.json").exists():
                raise ValueError("a prior Stage15 invocation blocks any recapture")
            write_evidence("capture-entry.json", canonical({"prepared_sha256": prepared_sha, "reserved_maximum": 2,
                "attempts_include_failures": True, "universes": 1, "ordinary_finalists": 0}) + b"\n")
            result.update(capture_reserved=2, capture_attempts=None, study_invocations=1)
            env["GTT_STAGE15_RUN"] = "authorized-one-universe"
            study_started = time.monotonic()
            try:
                study = process([str(packet), "-test.run=^TestStage15RealFullOutput$", "-test.v", "-test.timeout=610s"], native, env, 600)
            except BaseException as exc:
                result["study_process_error"] = f"{type(exc).__name__}: {exc}"
                # Export completed actual publications before managed cleanup,
                # including a deadline/child failure with no terminal receipt.
                freeze_public(job, result, assembly)
                exported = True
                raise
            result["checks"].append(study)
            try:
                ledger_path = job / "packet/public/study-ledger.json"
                if ledger_path.exists():
                    ledger = object_file(ledger_path)
                    result["native_ledger"] = ledger
                    result["capture_attempts"] = ledger["capture_attempts"]
            finally:
                # Retain all actual publication bytes even if the ledger is
                # absent, malformed, or missing accounting fields.
                output_started = time.monotonic()
                freeze_public(job, result, assembly)
                exported = True
                result["python_output_seconds"] = time.monotonic() - output_started
            result["outer_including_python_output_seconds"] = time.monotonic() - study_started
            ledger = result.get("native_ledger", {})
            if study["exit_code"] or ledger.get("status") != "PASS_REAL_PRODUCT_SESSION_FULL_OUTPUT" or result["capture_attempts"] != 2:
                raise ValueError("sole real study failed or capture accounting incomplete; no retry")
            if result["outer_including_python_output_seconds"] > 600 or ledger["clocks_seconds"]["offline"] + result["python_output_seconds"] > 480:
                raise ValueError("hard output clock exceeded")
            if not result.get("table_available") or result["table_snapshot"] != "terminal-snapshot.json":
                raise ValueError("complete terminal table missing")
            for path, sha in original_files.items():
                if io.sha_bytes((assembly / path).read_bytes()) != sha:
                    raise ValueError("study altered original target source")
            result["status"] = "PASS_REAL_TARGET_FULL_OUTPUT_ONE_TEAM"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()
    finally:
        result["cleanup"] = {key: str(value) if isinstance(value, Path) else value for key, value in (lifecycle or {}).items()}
        try:
            pins(initial)
            result["all_preservation_pins_unchanged"] = True
        except Exception as exc:
            result["pin_error"] = str(exc)
            result["status"] = "FAIL"
        if not result["cleanup"].get("cleaned"):
            result["status"] = "FAIL"
        result["public_export_completed"] = exported
        write_evidence(args.receipt, json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False).encode() + b"\n")
    print("STAGE15_FINAL " + json.dumps({"status": result["status"], "capture_attempts": result["capture_attempts"], "error": result.get("error"), "cleanup": result["cleanup"]}), flush=True)
    return 0 if result["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
