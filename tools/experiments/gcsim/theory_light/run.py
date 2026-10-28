"""Managed light-study entry point for the fixed Chiori saved case."""
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
from tools.experiments.gcsim.theory_hybrid import run as common
from tools.experiments.gcsim.theory_light import adapter

bounds = common.bounds
prior = common.prior
CASE = "chiori_lunar_crystallize"
COMMON_SHA256 = "f8740ff8ab9d0ea8c928138e9cfb995c027cbe56495209fea9f6a87c09820eb0"
PROTOCOL = ROOT / "docs/optimizer-evidence/2026-10-09-theory-light/PROTOCOL.md"
OFFLINE_GUARD_SECONDS = 360
OUTER_TEST_GUARD_SECONDS = 450


def identity():
    files = {p.name: prior.sha(p) for p in sorted(HERE.iterdir()) if p.suffix in (".py", ".go")}
    common_identity = common.identity()
    material = {"files": files, "common_identity_sha256": common_identity["sha256"]}
    return {**material, "sha256": hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()}


def _record(records, kind):
    return next((row for row in records if row.get("kind") == kind), None)


def pipeline_timing(result):
    prep = _record(result["records"], "preparation")
    summary = _record(result["records"], "light_study_summary")
    if prep is None or summary is None or "study" not in result:
        return {"complete_study_timing_available": False,
                "offline_guard_seconds": OFFLINE_GUARD_SECONDS}

    native_preparation = sum(float(prep.get(key, 0.0)) for key in (
        "native_input_seconds", "capture_seconds", "model_seconds", "catalog_setup_seconds"))
    shared_named_preparation = (
        result.get("input_preparation_seconds", 0.0)
        + result.get("source_preparation_seconds", 0.0)
        + native_preparation
    )
    native_process_residual = (
        result["study"].get("seconds", 0.0)
        - native_preparation
        - float(summary.get("seconds", 0.0))
    )
    policies = []
    for row in result["records"]:
        if row.get("kind") != "light_policy_result":
            continue
        policy_seconds = row.get("seconds")
        policies.append({
            "variant": row.get("variant"),
            "seconds": policy_seconds,
            "search_seconds": row.get("search_seconds"),
            "observation_seconds": row.get("observation_seconds"),
            "policy_guard_seconds": row.get("policy_guard_seconds"),
            "reconstructed_cold_subtotal_seconds": (
                shared_named_preparation + float(policy_seconds)
                if policy_seconds is not None else None
            ),
            "reconstructed_with_native_residual_seconds": (
                shared_named_preparation + native_process_residual + float(policy_seconds)
                if policy_seconds is not None else None
            ),
        })

    compile_seconds = result.get("compile", {}).get("seconds", 0.0)
    contracts_seconds = result.get("contracts", {}).get("seconds", 0.0)
    measured_managed = (
        compile_seconds + contracts_seconds
        + result.get("input_preparation_seconds", 0.0)
        + result.get("source_preparation_seconds", 0.0)
        + result["study"].get("seconds", 0.0)
    )
    study_seconds = float(summary.get("seconds", 0.0))
    return {
        "complete_study_timing_available": True,
        "native_preparation_seconds": native_preparation,
        "shared_named_preparation_seconds": shared_named_preparation,
        "native_process_residual_seconds": native_process_residual,
        "native_process_residual_scope": "study-process startup, serialization, teardown and unassigned overhead; not pure preparation",
        "policy_results": policies,
        "actual_managed_wall_seconds": result.get("wall_seconds"),
        "compilation_seconds": compile_seconds,
        "contracts_seconds": contracts_seconds,
        "actual_managed_without_compile_seconds": result.get("wall_seconds", 0.0) - compile_seconds,
        "managed_setup_cleanup_and_unassigned_seconds": result.get("wall_seconds", 0.0) - measured_managed,
        "offline_study_seconds": study_seconds,
        "offline_guard_seconds": OFFLINE_GUARD_SECONDS,
        "offline_guard_met": study_seconds <= OFFLINE_GUARD_SECONDS,
        "outer_test_guard_seconds": OUTER_TEST_GUARD_SECONDS,
        "actual_scope": "managed setup, separate compilation, contract gates, two-member capture, light study and cleanup",
    }


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--phase", choices=("unit", "study"), required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    receipt = args.receipt.resolve()
    receipt.relative_to((ROOT / "docs/optimizer-evidence").resolve())
    prior.assert_unlinked(receipt)
    if receipt.exists():
        raise FileExistsError(receipt)

    result = {
        "kind": "theory_light_research_v1",
        "status": "failed",
        "phase": args.phase,
        "case": CASE,
        "native_source_sha256": None,
        "prototype": None,
        "common_identity": None,
        "protocol_path": PROTOCOL.relative_to(ROOT).as_posix(),
        "protocol_sha256": None,
        "protocol_stable": False,
        "installed_changes": False,
        "records": [],
        "capture_member_limit": 2 if args.phase == "study" else 0,
        "capture_reservation_spent": 0,
        "capture_members_actual": None,
        "ordinary_finalists": 0,
        "study_invocations": 0,
        "full_solution_cache_enabled": False,
        "offline_guard_seconds": OFFLINE_GUARD_SECONDS,
        "outer_test_guard_seconds": OUTER_TEST_GUARD_SECONDS,
        "compilation_separate": True,
    }
    started = time.perf_counter()
    try:
        source = prior.native_source_identity(ROOT)
        prototype = identity()
        common_identity = common.identity()
        if common_identity["sha256"] != COMMON_SHA256:
            raise RuntimeError("Pinned common-H identity differs")
        if prototype["common_identity_sha256"] != COMMON_SHA256:
            raise RuntimeError("Light prototype does not include the pinned common-H identity")
        protocol_sha = prior.sha(PROTOCOL)
        consumer = prior.sha(prior.INSTALLED)
        result.update(
            native_source_sha256=source["sha256"],
            prototype=prototype,
            common_identity=common_identity,
            protocol_sha256=protocol_sha,
            installed_consumer_sha256=consumer,
        )
        if prior.sha(prior.GO) != prior.GO_SHA:
            raise RuntimeError("Toolchain identity differs")

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
            for key in (
                "GTT_PROGRESSIVE_KNOWN",
                "GTT_BOUNDS_CONTROL_PACKAGES",
                "GTT_FEASIBLE_NUMERIC_REUSE",
            ):
                env.pop(key, None)
            result["historical_controls_removed"] = True

            prior.managed_go.seed_module_downloads(Path(env["GOMODCACHE"]), prior.MODULES, prior.MODULE_SHA)
            native = job / "native"
            result["adapter_equivalence"] = adapter.prepare(native, bounds, CASE)

            binary = job / "light-tests.exe"
            result["compile"] = prior.run_process(
                [str(prior.GO), "test", "-c", "./cmd/gtt-optimizer", "-o", str(binary), "-p", "2"],
                native, env, "FEASIBLE_RECEIPT ", result["records"],
            )
            if result["compile"]["returncode"]:
                raise RuntimeError("Light-study managed compilation failed before capture")

            result["contracts"] = prior.run_process(
                [str(binary), "-test.run=^TestHybrid|^TestCommonH|^TestLight", "-test.v",
                 "-test.timeout=60s"],
                native, env, "FEASIBLE_RECEIPT ", result["records"],
            )
            if result["contracts"]["returncode"]:
                raise RuntimeError("Light-study contracts failed before capture")

            if args.phase == "study":
                if prior.sha(PROTOCOL) != protocol_sha:
                    raise RuntimeError("Light protocol changed before study entry")
                from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
                from run_workspace.gcsim.optimizer_go_all_sources import prepare_all_set_effect_sources
                from tools.experiments.gcsim.theory_bounds.inputs import load_contrast

                engine = load_active_gcsim_optimizer_engine_context()
                if not engine.trusted or prior.sha(Path(engine.artifact_path)) != engine.artifact_sha256:
                    raise RuntimeError("Selected engine not trusted")
                result["engine"] = {
                    key: getattr(engine, key)
                    for key in ("engine_id", "engine_root", "artifact_path", "artifact_sha256", "binding_sha256")
                }
                at = time.perf_counter()
                req, provenance = load_contrast(CASE, job, engine)
                result["input_preparation_seconds"] = time.perf_counter() - at
                result["input_provenance"] = provenance
                if len(req["stochastic"]["seeds"]) != 2:
                    raise RuntimeError("Light study requires exactly two capture members")
                result["request_sha256"] = hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()
                prior.write_json(job / "request.json", req)

                at = time.perf_counter()
                prior.write_json(
                    job / "sources.json",
                    prepare_all_set_effect_sources(Path(engine.engine_root), req["engine"], include_neutral_rules=True),
                )
                prior.write_json(job / "rarities.json", {item.key: item.max_rarity for item in engine.catalog.sets})
                result["source_preparation_seconds"] = time.perf_counter() - at

                env.update(
                    GTT_FEASIBLE_REQUEST=str(job / "request.json"),
                    GTT_FEASIBLE_SOURCES=str(job / "sources.json"),
                    GTT_FEASIBLE_RARITIES=str(job / "rarities.json"),
                    GTT_FEASIBLE_ROOT=str(job / "experiment"),
                    GTT_FEASIBLE_PHASE="light_study",
                    GTT_BOUNDS_CASE=CASE,
                )
                result["capture_reservation_spent"] = 2
                result["study_invocations"] = 1
                result["study"] = prior.run_process(
                    [str(binary), "-test.run=^TestTheoryFeasibleExperiment$", "-test.v",
                     f"-test.timeout={OUTER_TEST_GUARD_SECONDS}s"],
                    native, env, "FEASIBLE_RECEIPT ", result["records"],
                )
                if result["study"]["returncode"]:
                    raise RuntimeError("Light study failed; no automatic recapture")

                prep = _record(result["records"], "preparation")
                summary = _record(result["records"], "light_study_summary")
                if prep is None or summary is None:
                    raise RuntimeError("Light study omitted preparation or summary record")
                result["capture_members_actual"] = int(prep.get("engine_calls", 0))
                if result["capture_members_actual"] != 2:
                    raise RuntimeError("Unexpected capture count")
                if result["study_invocations"] != 1:
                    raise RuntimeError("Unexpected study invocation count")
                reported_finalists = summary.get("ordinary_finalists", 0)
                result["ordinary_finalists"] = int(reported_finalists)
                if result["ordinary_finalists"] != 0:
                    raise RuntimeError("Unexpected ordinary finalist calls")
                result["light_policy_result_count"] = sum(
                    1 for row in result["records"] if row.get("kind") == "light_policy_result"
                )
                result["hybrid_policy_snapshot_count"] = sum(
                    1 for row in result["records"] if row.get("kind") == "hybrid_policy"
                )
                if result["light_policy_result_count"] != 2 or result["hybrid_policy_snapshot_count"] < 2:
                    raise RuntimeError("Light study omitted one or both frozen policy results/snapshots")
                if int(summary.get("offline_guard_seconds", 0)) != OFFLINE_GUARD_SECONDS:
                    raise RuntimeError("Light study offline guard differs from the declared 360 seconds")
                if float(summary["seconds"]) > OFFLINE_GUARD_SECONDS:
                    raise RuntimeError("Measured offline time exceeded the hard guard")
                for row in result["records"]:
                    if row.get("kind") == "light_policy_result":
                        if row.get("complete") and (row.get("stop_reason") or row.get("wall_guard_hit") or row["seconds"] > row["policy_guard_seconds"]):
                            raise RuntimeError("A guarded policy was mislabeled complete")
                    elif row.get("kind") == "light_audit_summary":
                        if row.get("complete") and (row.get("wall_guard_hit") or row.get("target_wall_guard_hits") or row["seconds"] > 29):
                            raise RuntimeError("A guarded audit was mislabeled complete")

                current = load_active_gcsim_optimizer_engine_context()
                result["engine_stable"] = (
                    current.binding_sha256 == engine.binding_sha256
                    and prior.sha(Path(engine.artifact_path)) == engine.artifact_sha256
                )
                if not result["engine_stable"]:
                    raise RuntimeError("Selected engine changed during light study")
                result["protocol_stable"] = prior.sha(PROTOCOL) == protocol_sha
                if not result["protocol_stable"]:
                    raise RuntimeError("Light protocol changed during study")

            result["scratch_bytes_before_cleanup"] = sum(
                item.stat().st_size for item in job.rglob("*") if item.is_file()
            )

        result["inputs_stable"] = (
            prior.native_source_identity(ROOT)["sha256"] == source["sha256"]
            and identity() == prototype
            and common.identity()["sha256"] == COMMON_SHA256
            and prior.sha(prior.INSTALLED) == consumer
        )
        result["protocol_stable"] = prior.sha(PROTOCOL) == protocol_sha
        if not result["protocol_stable"]:
            raise RuntimeError("Light protocol changed during managed run")
        if not result["inputs_stable"]:
            raise RuntimeError("Source, prototype, common-H, or installed consumer identity changed")
        result["status"] = "pass"
    except BaseException as exc:
        result["error"] = str(exc)
        raise
    finally:
        prep = _record(result["records"], "preparation")
        if prep is not None:
            result["capture_members_actual"] = int(prep["engine_calls"])
        elif not result["capture_reservation_spent"]:
            result["capture_members_actual"] = 0
        if "managed_job" in result:
            owned = Path(result["managed_job"])
            result["cleanup"] = {
                "job_absent": not owned.exists(),
                "remaining_jobs": [item.name for item in owned.parent.glob("job-*")],
            }
            if not result["cleanup"]["job_absent"] and result["status"] == "pass":
                result["status"] = "failed_cleanup"
                result["error"] = "Managed scratch job remained after context cleanup"
        if result.get("protocol_sha256"):
            try:
                result["protocol_stable"] = prior.sha(PROTOCOL) == result["protocol_sha256"]
            except Exception as exc:
                result["protocol_stable"] = False
                result["protocol_check_error"] = str(exc)
            if not result["protocol_stable"] and result["status"] == "pass":
                result["status"] = "failed_identity"
                result["error"] = "Light protocol changed during managed run"
        result["wall_seconds"] = time.perf_counter() - started
        result["timing"] = pipeline_timing(result)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        with receipt.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps({"status": result["status"], "receipt": str(receipt)}), flush=True)


if __name__ == "__main__":
    main()
