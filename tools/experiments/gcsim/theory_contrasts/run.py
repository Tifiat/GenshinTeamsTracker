"""Managed Stage11 same-universe Chasca/Bountiful contrast entry point."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from tools.experiments.gcsim.theory_light import run as light

bounds = light.bounds
prior = light.prior
LIGHT_SHA256 = "fd9a6a3367694a978cd77b8ed61111d1ab51d296467ad95ff8e4bed2c675eb2d"
STAGE10_COMMIT = "47e13fa8c2bc79284b177978605a38570c841ac7"
PROTOCOL = ROOT / "docs/optimizer-evidence/2026-10-09-theory-contrasts/PROTOCOL.md"
CONTINUATION = ROOT / "docs/optimizer-evidence/2026-10-09-theory-contrasts/CONTINUATION.md"
FROZEN_CHASCA_COMMIT = "ef9077bf50b96bc06cabff94e870fbe8e8f70c1f"
FROZEN_CHASCA_IDENTITY = "fcd10ac3779bbaf7fd2c20e9043c295c60590a686069ded65d8f37f8c6e1bf90"
OFFLINE_GUARD_SECONDS = 240
OUTER_TEST_GUARD_SECONDS = 450
CONTRACT_TEST_GUARD_SECONDS = 60
GO_TEST_PATTERN = r"^TestHybrid|^TestCommonH|^TestLight|^TestContrast"
EXPECTED_GO_TESTS = 20
EXPECTED_PYTHON_TESTS = 26
PREFIX_ACK = "CONTINUE_BASELINE\n"
PREFIX_SCOPE = (
    "parent-clock interval from immediately after compile and contract gates, before engine imports/loading/input/source, "
    "through trusted engine/input/source preparation, two-member capture/model/catalog, H-light completion and its "
    "receipt line arrival; stops before baseline, audit and postchecks"
)


def identity():
    files = {path.name: prior.sha(path) for path in sorted(HERE.iterdir()) if path.suffix in (".py", ".go")}
    light_identity = light.identity()
    material = {"files": files, "light_identity_sha256": light_identity["sha256"],
                "frozen_chasca_commit": FROZEN_CHASCA_COMMIT,
                "frozen_chasca_identity_sha256": FROZEN_CHASCA_IDENTITY}
    return {
        **material,
        "sha256": hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest(),
    }


def _record(records, kind):
    return next((row for row in records if row.get("kind") == kind), None)


def _offline_seconds(receipt):
    timing = receipt.get("timing", {})
    for key in ("offline_study_seconds", "offline_seconds", "study_offline_seconds"):
        value = timing.get(key, receipt.get(key))
        if isinstance(value, (int, float)):
            return float(value)
    for row in receipt.get("records", []):
        if row.get("kind") in ("light_study_summary", "contrast_study_summary", "contrast_summary"):
            value = row.get("seconds")
            if isinstance(value, (int, float)):
                return float(value)
    return None


def _load_chasca_prerequisite(path, prototype_sha256, protocol_sha256, output_receipt, acceptance, admission=None):
    saved_path = path.resolve(strict=True)
    saved_path.relative_to((ROOT / "docs/optimizer-evidence").resolve())
    if saved_path == output_receipt:
        raise ValueError("Chasca prerequisite and Bountiful output receipt must be different files")
    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    digest = prior.sha(saved_path)
    if admission is None:
        validated_seconds = acceptance.validate_prerequisite(saved, prototype_sha256, protocol_sha256)
        decision = {"kind": "original_quality_gate"}
    else:
        validated_seconds = admission.validate_prerequisite(saved, digest, prototype_sha256, protocol_sha256)
        decision = admission.decision_info()
    return saved, {
        "path": saved_path.relative_to(ROOT).as_posix(),
        "sha256": digest,
        "offline_seconds": validated_seconds,
        "validation": "passed",
        "validated": True,
        "admission": decision,
        "original_quality_pass": saved["quality_gate"]["pass"],
        "original_next_case_allowed": saved["next_case_allowed"],
        "role": "prior Chasca acceptance and pair-budget input only; no candidate or allocation reuse",
    }


def _passed_name(line):
    prefix = "--- PASS: "
    if not line.startswith(prefix):
        return None
    return line[len(prefix):].split(None, 1)[0]


def run_process(command, cwd, env, records, *, collect_go_tests=False,
                barrier_prefix=False, prefix_started=None, direct_prefix=None,
                collect_python_tests=False):
    """Read line records and service the one declared pre-baseline ACK barrier."""
    started = time.perf_counter()
    tail = []
    passed_tests = []
    p = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE if barrier_prefix else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    try:
        for raw in p.stdout:
            line = raw.rstrip()
            line_arrival = time.perf_counter()
            if line.startswith("FEASIBLE_RECEIPT "):
                row = json.loads(line[len("FEASIBLE_RECEIPT "):])
                records.append(row)
                if row.get("kind") == "contrast_light_ready":
                    if not barrier_prefix or p.stdin is None or prefix_started is None or direct_prefix is None:
                        raise RuntimeError("Unexpected contrast prefix barrier record")
                    direct_prefix["ready_count"] += 1
                    if direct_prefix["ready_count"] == 1:
                        direct_prefix["seconds"] = line_arrival - prefix_started
                    p.stdin.write(PREFIX_ACK)
                    p.stdin.flush()
                    direct_prefix["ack_sent_count"] += 1
                print("Recorded " + str(row.get("name", row.get("kind", "measurement"))), flush=True)
                continue

            name = _passed_name(line)
            if collect_go_tests and name:
                passed_tests.append(name)
            if collect_python_tests:
                match = re.match(r"^(\w+)\s+\(([^)]+)\)\s+\.\.\.\s+ok$", line)
                if match:
                    passed_tests.append(match.group(1) + " (" + match.group(2) + ")")
            print(line, flush=True)
            tail = (tail + [line])[-30:]

        code = p.wait()
    finally:
        if p.poll() is None:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, check=False)
            p.wait(timeout=15)
        if p.stdin is not None and not p.stdin.closed:
            p.stdin.close()
        if p.stdout is not None:
            p.stdout.close()
    result = {"returncode": code, "seconds": time.perf_counter() - started, "tail": tail}
    if collect_go_tests:
        result["passed_tests"] = passed_tests
    if collect_python_tests:
        result["passed_tests"] = passed_tests
    return result


def timing_summary(result):
    prep = _record(result["records"], "preparation")
    study = result.get("study", {})
    summary = next((row for row in result["records"]
                    if row.get("kind") in ("light_study_summary", "contrast_study_summary", "contrast_summary")), None)
    native_prep = None
    if prep is not None:
        native_prep = sum(float(prep.get(key, 0.0)) for key in (
            "native_input_seconds", "capture_seconds", "model_seconds", "catalog_setup_seconds"))
    shared_named_prep = (native_prep or 0.0) + sum(result.get(key, 0.0) for key in (
        "engine_context_load_seconds", "input_preparation_seconds", "source_preparation_seconds"))
    offline = float(summary["seconds"]) if summary else None
    native_residual = study.get("seconds", 0.0) - (native_prep or 0.0) - offline if offline is not None else None
    policies = []
    for row in result["records"]:
        if row.get("kind") != "light_policy_result":
            continue
        snapshot = next(r for r in result["records"] if r.get("kind") == "hybrid_policy" and r["variant"] == row["variant"])
        policies.append({
            "variant": row["variant"], "cold_policy_seconds": row["seconds"],
            "search_seconds": row["search_seconds"], "observation_seconds": row["observation_seconds"],
            "cold_model_seconds": snapshot["model_seconds"], "stages_seconds": snapshot["stages_seconds"],
            "policy_unassigned_seconds": row["seconds"] - snapshot["model_seconds"] - sum(snapshot["stages_seconds"].values()) - row["observation_seconds"],
            "reconstructed_cold_subtotal_seconds": shared_named_prep + row["seconds"],
            "reconstruction_scope": "named shared preparation plus this cold policy; not another standalone run",
        })
    named_managed = sum(result.get(key, {}).get("seconds", 0.0) for key in ("compile", "contracts", "python_contracts", "study"))
    named_managed += sum(result.get(key, 0.0) for key in (
        "engine_context_load_seconds", "input_preparation_seconds", "source_preparation_seconds", "acceptance_seconds"))
    return {
        "compilation_seconds": result.get("compile", {}).get("seconds"),
        "go_contract_seconds": result.get("contracts", {}).get("seconds"),
        "python_contract_seconds": result.get("python_contracts", {}).get("seconds"),
        "study_process_seconds": study.get("seconds"),
        "offline_study_seconds": float(summary["seconds"]) if summary and isinstance(summary.get("seconds"), (int, float)) else None,
        "offline_guard_seconds": OFFLINE_GUARD_SECONDS,
        "offline_guard_met": (
            float(summary["seconds"]) <= OFFLINE_GUARD_SECONDS
            if summary and isinstance(summary.get("seconds"), (int, float)) else None
        ),
        "direct_prefix": result.get("direct_prefix"),
        "engine_context_load_seconds": result.get("engine_context_load_seconds"),
        "input_preparation_seconds": result.get("input_preparation_seconds"),
        "source_preparation_seconds": result.get("source_preparation_seconds"),
        "native_preparation_seconds": native_prep,
        "shared_named_preparation_seconds": shared_named_prep,
        "native_process_residual_seconds": native_residual,
        "native_residual_scope": "study process startup, serialization, teardown and unassigned overhead; not pure preparation",
        "policy_results": policies,
        "prefix_ack_wait_seconds": (_record(result["records"], "contrast_prefix_ack") or {}).get("wait_seconds"),
        "acceptance_seconds": result.get("acceptance_seconds"),
        "actual_managed_wall_seconds": result.get("wall_seconds"),
        "managed_setup_cleanup_and_unassigned_seconds": result.get("wall_seconds", 0.0) - named_managed,
        "actual_managed_without_compile_seconds": (
            result.get("wall_seconds", 0.0) - result.get("compile", {}).get("seconds", 0.0)
            if result.get("wall_seconds") is not None else None
        ),
        "scope_note": "Actual managed wall spans setup, gates, study, cleanup and receipt acceptance; excludes final durable receipt serialization. Direct prefix is parent-clock measured. Named subtotals are explicitly reconstructed, with no historical-time subtraction.",
    }


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--phase", choices=("unit", "study"), required=True)
    parser.add_argument("--case", choices=("chasca", "bountiful_core"), required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--chasca-receipt", type=Path)
    parser.add_argument("--authorized-nilou-continuation", action="store_true",
                        help="Use the exact prospective admission in CONTINUATION.md; preserve the original Chasca FAIL")
    args = parser.parse_args()
    protocol = CONTINUATION if args.authorized_nilou_continuation else PROTOCOL

    receipt = args.receipt.resolve()
    receipt.relative_to((ROOT / "docs/optimizer-evidence").resolve())
    prior.assert_unlinked(receipt)
    if receipt.exists():
        raise FileExistsError(receipt)

    result = {
        "kind": "theory_contrasts_research_v1",
        "status": "failed",
        "process_status": "not_started",
        "phase": args.phase,
        "case": args.case,
        "stage10_commit": STAGE10_COMMIT,
        "native_source_sha256": None,
        "prototype": None,
        "light_identity_sha256": None,
        "protocol_path": protocol.relative_to(ROOT).as_posix(),
        "protocol_sha256": None,
        "protocol_stable": False,
        "installed_changes": False,
        "records": [],
        "capture_member_limit": 2 if args.phase == "study" else 0,
        "capture_reservation_spent": 0,
        "capture_members_actual": 0,
        "ordinary_finalists": 0,
        "study_invocations": 0,
        "offline_guard_seconds": OFFLINE_GUARD_SECONDS,
        "outer_test_guard_seconds": OUTER_TEST_GUARD_SECONDS,
        "contract_test_guard_seconds": CONTRACT_TEST_GUARD_SECONDS,
        "compilation_separate": True,
        "full_solution_cache_enabled": False,
        "historical_controls_removed": True,
        "direct_prefix": {
            "seconds": None,
            "ready_count": 0,
            "ack_sent_count": 0,
            "baseline_excluded_by_ack": True,
            "scope": PREFIX_SCOPE,
        },
    }
    started = time.perf_counter()
    acceptance_module = None
    failure = None
    try:
        if args.authorized_nilou_continuation and (args.phase != "study" or args.case != "bountiful_core" or args.chasca_receipt is None):
            raise ValueError("Specific post-result admission permits only the saved Bountiful study with its Chasca receipt")
        if args.phase == "study" and args.case == "bountiful_core" and args.chasca_receipt is None:
            raise ValueError("Bountiful study requires a validated Chasca prerequisite receipt")
        if args.chasca_receipt is not None and not (args.phase == "study" and args.case == "bountiful_core"):
            raise ValueError("--chasca-receipt is only valid for a Bountiful study")
        from tools.experiments.gcsim.theory_contrasts import acceptance as acceptance_module

        source = prior.native_source_identity(ROOT)
        prototype = identity()
        light_identity = light.identity()
        if light_identity["sha256"] != LIGHT_SHA256:
            raise RuntimeError("Pinned Stage10 identity differs")
        if prototype["light_identity_sha256"] != LIGHT_SHA256:
            raise RuntimeError("Stage11 prototype does not include the pinned Stage10 identity")
        protocol_sha = prior.sha(protocol)
        consumer = prior.sha(prior.INSTALLED)
        result.update(
            native_source_sha256=source["sha256"],
            prototype=prototype,
            light_identity_sha256=light_identity["sha256"],
            protocol_sha256=protocol_sha,
            installed_consumer_sha256=consumer,
        )
        if prior.sha(prior.GO) != prior.GO_SHA:
            raise RuntimeError("Toolchain identity differs")

        if args.phase == "study" and args.case == "bountiful_core":
            admission = None
            if args.authorized_nilou_continuation:
                from tools.experiments.gcsim.theory_contrasts import admission
            saved, provenance = _load_chasca_prerequisite(
                args.chasca_receipt, prototype["sha256"], protocol_sha, receipt, acceptance_module, admission
            )
            result["chasca_prerequisite"] = provenance
            result["chasca_offline_seconds"] = provenance["offline_seconds"]
            # Keep the saved receipt out of the output: only its identity and elapsed evidence are inputs.
            del saved

        python_env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        for key in ("GTT_PROGRESSIVE_KNOWN", "GTT_BOUNDS_CONTROL_PACKAGES", "GTT_FEASIBLE_NUMERIC_REUSE"):
            python_env.pop(key, None)
        result["python_contracts"] = run_process(
            [sys.executable, "-B", "-m", "unittest", "-v",
             "tools.experiments.gcsim.theory_contrasts.test_acceptance",
             "tools.experiments.gcsim.theory_contrasts.test_witness_audit",
             "tools.experiments.gcsim.theory_contrasts.test_admission"],
            ROOT, python_env, result["records"], collect_python_tests=True,
        )
        if result["python_contracts"]["returncode"]:
            result["process_status"] = "failed_python_contracts"
            raise RuntimeError("Pure Python acceptance tests failed before capture")
        if len(result["python_contracts"].get("passed_tests", [])) != EXPECTED_PYTHON_TESTS:
            result["process_status"] = "failed_python_contract_count"
            raise RuntimeError("Expected exactly 26 passing acceptance, witness and prospective-admission tests")

        with prior.managed_scratch() as job:
            result["managed_job"] = str(job)
            (job / "go-cache").mkdir()
            (job / "temp").mkdir()
            inherited = dict(
                os.environ,
                GOCACHE=str(job / "go-cache"),
                GTT_MANAGED_GO_CACHE=str(job / "go-cache"),
                GOTMPDIR=str(job / "temp"),
                GTT_SCRATCH_DIR=str(job),
                TMP=str(job / "temp"),
                TEMP=str(job / "temp"),
            )
            env = prior.managed_go.go_environment(job, inherited)
            env.update(
                PYTHONDONTWRITEBYTECODE="1",
                GTT_RULE_CACHE_DIR=str(job / "rules"),
                GTT_RULE_BUNDLED_CACHE_DIR=str(job / "bundled-rules"),
            )
            for key in ("GTT_PROGRESSIVE_KNOWN", "GTT_BOUNDS_CONTROL_PACKAGES", "GTT_FEASIBLE_NUMERIC_REUSE"):
                env.pop(key, None)
            prior.managed_go.seed_module_downloads(Path(env["GOMODCACHE"]), prior.MODULES, prior.MODULE_SHA)

            native = job / "native"
            result["adapter_equivalence"] = __import__(
                "tools.experiments.gcsim.theory_contrasts.adapter", fromlist=["adapter"]
            ).prepare(native, bounds, args.case)

            binary = job / "contrast-tests.exe"
            result["compile"] = run_process(
                [str(prior.GO), "test", "-c", "./cmd/gtt-optimizer", "-o", str(binary), "-p", "2"],
                native, env, result["records"],
            )
            if result["compile"]["returncode"]:
                result["process_status"] = "failed_compile"
                raise RuntimeError("Stage11 managed-copy compilation failed before capture")

            result["contracts"] = run_process(
                [str(binary), "-test.run=" + GO_TEST_PATTERN, "-test.v",
                 f"-test.timeout={CONTRACT_TEST_GUARD_SECONDS}s"],
                native, env, result["records"], collect_go_tests=True,
            )
            if result["contracts"]["returncode"]:
                result["process_status"] = "failed_go_contracts"
                raise RuntimeError("Stage11 Go gates failed before capture")
            if len(result["contracts"]["passed_tests"]) != EXPECTED_GO_TESTS:
                result["process_status"] = "failed_go_contract_count"
                raise RuntimeError("Expected exactly 20 passing Hybrid/Common-H/Light/Contrast gates")

            result["process_status"] = "gates_passed"
            if args.phase == "study":
                if prior.sha(protocol) != protocol_sha:
                    raise RuntimeError("Contrast protocol changed before study entry")

                # The direct-prefix clock starts before any engine or case-input imports.
                prefix_started = time.perf_counter()
                from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
                from run_workspace.gcsim.optimizer_go_all_sources import prepare_all_set_effect_sources

                engine_started = time.perf_counter()
                engine = load_active_gcsim_optimizer_engine_context()
                result["engine_context_load_seconds"] = time.perf_counter() - engine_started
                if not engine.trusted or prior.sha(Path(engine.artifact_path)) != engine.artifact_sha256:
                    raise RuntimeError("Selected engine not trusted")
                result["engine"] = {
                    key: getattr(engine, key)
                    for key in ("engine_id", "engine_root", "artifact_path", "artifact_sha256", "binding_sha256")
                }

                input_started = time.perf_counter()
                if args.case == "chasca":
                    fixture = prior.SOURCE
                    saved_input = json.loads(fixture.read_bytes())
                    req = prior.rebind_request(saved_input["original_request"], Path(engine.engine_root))
                    result["source_fixture"] = {
                        "path": fixture.relative_to(ROOT).as_posix(),
                        "sha256": prior.sha(fixture),
                        "role": "request fixture only; no saved candidate/result reuse",
                    }
                else:
                    from tools.experiments.gcsim.theory_bounds.inputs import load_contrast
                    req, provenance = load_contrast(args.case, job, engine)
                    result["input_provenance"] = provenance
                result["input_preparation_seconds"] = time.perf_counter() - input_started
                if len(req["stochastic"]["seeds"]) != 2:
                    raise RuntimeError("Each contrast case requires exactly two capture members")
                result["request_sha256"] = hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()
                prior.write_json(job / "request.json", req)

                source_started = time.perf_counter()
                prior.write_json(
                    job / "sources.json",
                    prepare_all_set_effect_sources(Path(engine.engine_root), req["engine"], include_neutral_rules=True),
                )
                prior.write_json(job / "rarities.json", {item.key: item.max_rarity for item in engine.catalog.sets})
                result["source_preparation_seconds"] = time.perf_counter() - source_started

                env.update(
                    GTT_FEASIBLE_REQUEST=str(job / "request.json"),
                    GTT_FEASIBLE_SOURCES=str(job / "sources.json"),
                    GTT_FEASIBLE_RARITIES=str(job / "rarities.json"),
                    GTT_FEASIBLE_ROOT=str(job / "experiment"),
                    GTT_FEASIBLE_PHASE="light_study",
                    GTT_BOUNDS_CASE=args.case,
                )
                result["capture_reservation_spent"] = 2
                result["study_invocations"] = 1
                result["study"] = run_process(
                    [str(binary), "-test.run=^TestTheoryFeasibleExperiment$", "-test.v",
                     f"-test.timeout={OUTER_TEST_GUARD_SECONDS}s"],
                    native, env, result["records"], barrier_prefix=True,
                    prefix_started=prefix_started, direct_prefix=result["direct_prefix"],
                )
                if result["study"]["returncode"]:
                    result["process_status"] = "failed_study"
                    raise RuntimeError("Stage11 contrast study failed; no automatic retry or recapture")
                result["process_status"] = "pass"
                prep = _record(result["records"], "preparation")
                if prep is not None and isinstance(prep.get("engine_calls"), int):
                    result["capture_members_actual"] = prep["engine_calls"]
                finalists = []
                for row in result["records"]:
                    if "ordinary_finalists" in row:
                        finalists.append(int(row["ordinary_finalists"]))
                    if "finalist_calls" in row:
                        finalists.append(int(row["finalist_calls"]))
                result["ordinary_finalists"] = sum(finalists)
                if result["direct_prefix"]["ready_count"] != 1 or result["direct_prefix"]["ack_sent_count"] != 1:
                    raise RuntimeError("Expected exactly one acknowledged H-light prefix boundary")
                if result["study_invocations"] != 1:
                    raise RuntimeError("Unexpected study invocation count")

                if result["capture_members_actual"] != 2:
                    raise RuntimeError("Unexpected Stage11 capture count")
                if result["ordinary_finalists"] != 0:
                    raise RuntimeError("Unexpected ordinary finalist calls")

                current = load_active_gcsim_optimizer_engine_context()
                result["engine_stable"] = (
                    current.binding_sha256 == engine.binding_sha256
                    and prior.sha(Path(engine.artifact_path)) == engine.artifact_sha256
                )
                if not result["engine_stable"]:
                    raise RuntimeError("Selected engine changed during contrast study")
                result["protocol_stable"] = prior.sha(protocol) == protocol_sha
                if not result["protocol_stable"]:
                    raise RuntimeError("Contrast protocol changed during study")

            result["scratch_bytes_before_cleanup"] = sum(
                path.stat().st_size for path in job.rglob("*") if path.is_file()
            )

        result["identity_checks"] = {
            "native_source_stable": prior.native_source_identity(ROOT)["sha256"] == source["sha256"],
            "prototype_stable": identity() == prototype,
            "light_identity_stable": light.identity()["sha256"] == LIGHT_SHA256,
            "consumer_stable": prior.sha(prior.INSTALLED) == consumer,
            "go_toolchain_stable": prior.sha(prior.GO) == prior.GO_SHA,
            "protocol_stable": prior.sha(protocol) == protocol_sha,
            "engine_stable": result.get("engine_stable", True),
        }
        result["protocol_stable"] = result["identity_checks"]["protocol_stable"]
        result["inputs_stable"] = all(result["identity_checks"].values())
        if not result["inputs_stable"]:
            raise RuntimeError("A pinned source, protocol, consumer, toolchain, or engine identity changed")
        if result["process_status"] == "gates_passed" and args.phase == "unit":
            result["process_status"] = "pass"
        result["status"] = "pass"
    except BaseException as exc:
        failure = exc
        result["error"] = str(exc)
        if result["process_status"] in ("not_started", "gates_passed"):
            result["process_status"] = "failed"
        result["status"] = "failed"
    finally:
        prep = _record(result["records"], "preparation")
        if prep is not None and isinstance(prep.get("engine_calls"), int):
            result["capture_members_actual"] = prep["engine_calls"]
        elif result["capture_reservation_spent"] == 2:
            result["capture_members_actual"] = None
        finalists = []
        for row in result["records"]:
            if "ordinary_finalists" in row:
                finalists.append(int(row["ordinary_finalists"]))
            if "finalist_calls" in row:
                finalists.append(int(row["finalist_calls"]))
        result["ordinary_finalists"] = sum(finalists)
        if "managed_job" in result:
            owned = Path(result["managed_job"])
            result["cleanup"] = {
                "job_absent": not owned.exists(),
                "remaining_jobs": [path.name for path in owned.parent.glob("job-*")],
            }
            if not result["cleanup"]["job_absent"] and result["process_status"] == "pass":
                result["process_status"] = "failed_cleanup"
                result["status"] = "failed"
                result["error"] = "Managed scratch job remained after context cleanup"
        else:
            result["cleanup"] = {"job_absent": True, "managed_job_allocated": False}
        result["wall_seconds"] = time.perf_counter() - started
        result["timing"] = timing_summary(result)
        current_offline = _offline_seconds(result)
        result["offline_study_seconds"] = current_offline
        prior_offline = result.get("chasca_prerequisite", {}).get("offline_seconds")
        if args.phase == "study" and args.case == "bountiful_core":
            result["paired_offline_seconds"] = (
                float(prior_offline) + float(current_offline)
                if isinstance(prior_offline, (int, float)) and isinstance(current_offline, (int, float))
                else None
            )
        elif args.phase == "study":
            result["paired_offline_seconds"] = current_offline
        if result.get("protocol_sha256"):
            try:
                result["protocol_stable"] = prior.sha(protocol) == result["protocol_sha256"]
            except Exception as exc:
                result["protocol_stable"] = False
                result["protocol_check_error"] = str(exc)
        if acceptance_module is None:
            try:
                from tools.experiments.gcsim.theory_contrasts import acceptance as acceptance_module
            except Exception as exc:
                result["acceptance_error"] = str(exc)
        acceptance_started = time.perf_counter()
        if acceptance_module is not None:
            try:
                result.update(acceptance_module.evaluate(result))
            except BaseException as exc:
                result["acceptance_error"] = str(exc)
                result["acceptance_complete"] = False
                result["acceptance_failures"] = ["Acceptance evaluation raised: " + str(exc)]
                result["next_case_allowed"] = False
        else:
            result["acceptance_complete"] = False
            result["acceptance_failures"] = [
                "Acceptance module unavailable: " + result.get("acceptance_error", "unknown error")
            ]
            result["next_case_allowed"] = False
        if args.phase == "study" and not result.get("next_case_allowed", False):
            result["exit_required"] = "acceptance did not allow the next case"
        result["acceptance_seconds"] = time.perf_counter() - acceptance_started
        result["wall_seconds"] = time.perf_counter() - started
        result["timing"] = timing_summary(result)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        with receipt.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps({
            "process_status": result["process_status"],
            "next_case_allowed": result.get("next_case_allowed", False),
            "receipt": str(receipt),
        }), flush=True)

    if failure is not None:
        raise failure
    if args.phase == "study" and not result.get("next_case_allowed", False):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
