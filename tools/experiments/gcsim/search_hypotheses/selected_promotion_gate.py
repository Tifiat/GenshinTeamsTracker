"""Source-built Selected gate on one retained request and fresh engine evidence.

Run only inside managed_optimizer_experiment.py. The saved run contributes its
request.json alone: never its compact panel, partial result, or Finish marker.
No account database, production source, installed binary, or engine is edited.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
from run_workspace.gcsim.optimizer_go_contracts import canonical_sha256
from run_workspace.gcsim.optimizer_go_selected import (
    GcsimOptimizerGoSelectedRequest, GcsimOptimizerGoSelectedSession, _write_canonical,
)
from tools.experiments.gcsim.search_hypotheses.promotion_gate import (
    INSTALLED, POINTER, SOURCE, assert_engine, receipt_path, save_receipt, source_sha256,
)
from tools.experiments.gcsim.search_hypotheses.run import sha
from tools.managed_optimizer_experiment import owned_job

SAVED_REQUEST = ROOT / "data/gcsim/optimizer-go-runs/selected-20260927-211900-45b74566/request.json"
SAVED_REQUEST_SHA256 = "9a20a3b60d93fb2cd47ce0a3d2fa2ef5ad730a3806cd3c5a6227fa2747c8662d"
FAST_PASS = "selected_fast_formula_pair_pass"
ORDINARY_PASS = "selected_ordinary_n500_smoke_pass"


def retained_request():
    if sha(SAVED_REQUEST) != SAVED_REQUEST_SHA256:
        raise ValueError("Pinned Selected request changed")
    raw = json.loads(SAVED_REQUEST.read_text(encoding="utf-8"))
    if raw.get("result_options") != {"builds_per_group": 7, "fast_mode": True, "set_group_limit": 1}:
        raise ValueError("Pinned Selected fast result options changed")
    if raw.get("cancellation") != {"mode": "process_interrupt_v1"}:
        raise ValueError("Pinned Selected cancellation contract changed")
    return raw


def ordinary_request(raw):
    clone = json.loads(json.dumps(raw))
    clone["result_options"] = {"builds_per_group": 3, "fast_mode": False, "set_group_limit": 1}
    return clone


def adapter_request(job: Path, raw, binary: Path):
    options = raw["result_options"]
    seeds = tuple(raw["stochastic"]["seeds"])
    request = GcsimOptimizerGoSelectedRequest(
        db_path=str(job / "unused-account.db"), selected_team={}, team_index=0,
        rotation_shell_text="", run_root=str(job / "unused-runs"),
        seeds=seeds, product_timeout_ms=0,
        set_group_limit=options["set_group_limit"], builds_per_group=options["builds_per_group"],
        fast_mode=options["fast_mode"], optimizer_binary_path=str(binary),
    )
    default = GcsimOptimizerGoSelectedRequest("unused", {}, 0, "")
    if Path(default.optimizer_binary_path).resolve() != INSTALLED.resolve():
        raise ValueError("Default Selected adapter consumer is not the installed optimizer")
    return request


def stage_inputs(captured: Path, target: Path):
    """Only these two newly created inputs cross runs, never Finish or old output."""
    target.mkdir(exist_ok=False)
    for name in ("request.json", "compact.json"):
        shutil.copy2(captured / name, target / name)
        if sha(captured / name) != sha(target / name):
            raise ValueError(f"Selected {name} changed while staging")
    if (target / "finish-requested").exists():
        raise ValueError("A stale Selected Finish marker entered a fresh run")


def _decimal(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid Selected formula DPS") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError("Nonpositive or nonfinite Selected formula DPS")
    return number


def _measured(row):
    measured = row.get("measured")
    if (not isinstance(measured, dict) or type(measured.get("iterations")) is not int or
            measured["iterations"] != 500 or
            not isinstance(measured.get("engine_result_sha256"), str) or
            not measured["engine_result_sha256"]):
        raise ValueError("Ordinary Selected candidate lacks n500 measurement identity")
    dps = _decimal(measured.get("dps"))
    try:
        error = Decimal(str(measured.get("standard_error")))
        residual = Decimal(str(row.get("formula_residual")))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Ordinary Selected measurement numbers are invalid") from exc
    if not error.is_finite() or error < 0 or not residual.is_finite():
        raise ValueError("Ordinary Selected measurement uncertainty or residual is invalid")
    return {"iterations": 500, "dps": str(dps), "standard_error": str(error),
            "engine_result_sha256": measured["engine_result_sha256"],
            "formula_residual": str(residual)}


def validate_legal_rows(rows, request):
    """Explicit exported-inventory checks; never depend on Python assertions."""
    slots = {"flower", "plume", "sands", "goblet", "circlet"}
    wearers = {w["wearer_key"] for w in request["wearers"]}
    items = {a["artifact_id"]: a for a in request["artifacts"]}
    expected = {(wearer, slot) for wearer in wearers for slot in slots}
    if len(wearers) != 4 or len(items) != len(request["artifacts"]):
        raise ValueError("Selected candidate legality failed: ambiguous inventory")
    identities, signatures, groups = set(), {}, {}
    for row in rows:
        assignment = tuple(sorted((a["wearer_key"], a["slot"], a["artifact_id"])
                                  for a in row["artifacts"]))
        if (len(assignment) != 20 or len({x[2] for x in assignment}) != 20 or
                {(x[0], x[1]) for x in assignment} != expected or assignment in identities or
                any(x[2] not in items or items[x[2]]["slot"] != x[1] for x in assignment)):
            raise ValueError("Selected candidate legality failed: assignment")
        group = row["set_group_key"]
        signature = tuple((wearer, tuple(sorted((key, 4 if count >= 4 else 2)
                           for key, count in Counter(items[x[2]]["set_uid"]
                           for x in assignment if x[0] == wearer).items() if count >= 2)))
                          for wearer in sorted(wearers))
        if group in signatures and signatures[group] != signature:
            raise ValueError("Selected candidate legality failed: group signature")
        signatures[group] = signature
        identities.add(assignment)
        groups.setdefault(group, []).append({(x[0], x[1]): x[2] for x in assignment})
    if len(set(signatures.values())) != len(signatures):
        raise ValueError("Selected candidate legality failed: duplicate group signature")
    for alternatives in groups.values():
        if any(sum(row[key] != alternatives[0][key] for key in expected) != 1
               for row in alternatives[1:]):
            raise ValueError("Selected candidate legality failed: non-single replacement")


def summarize_selected(wrapper, raw, *, ordinary: bool):
    result = wrapper["product_result"]
    rows = result["candidates"]
    validate_legal_rows(rows, raw)
    options = raw["result_options"]
    if not rows or len(rows) > options["builds_per_group"]:
        raise ValueError("Selected candidate count exceeds request")
    if result.get("request_sha256") != canonical_sha256(raw):
        raise ValueError("Selected result request identity differs")
    if result.get("ranking_basis") != ("gcsim" if ordinary else "formula"):
        raise ValueError("Selected ranking mode differs from request")
    policy = wrapper.get("verification_policy")
    if ordinary:
        if policy != "single_n500":
            raise ValueError("Ordinary Selected n500 finalist verification is absent")
    elif policy != "formula_only" or result.get("measured") is not None or "formula_only_unverified" not in result.get("warnings", ()):
        raise ValueError("Fast Selected result is not formula-only")
    fingerprints = []
    for index, row in enumerate(rows, 1):
        if row.get("rank") != index:
            raise ValueError("Selected candidate ranks are not consecutive")
        ids = sorted((a["wearer_key"], a["slot"], a["artifact_id"]) for a in row["artifacts"])
        fingerprint = {"rank": index, "set_group_key": row["set_group_key"],
                       "set_group_rank": row["set_group_rank"],
                       "alternative_rank": row["alternative_rank"],
                       "ids": ids, "formula_dps": str(_decimal(row["formula_dps"]))}
        if ordinary:
            fingerprint["measured"] = _measured(row)
        elif row.get("measured") is not None or row.get("formula_residual"):
            raise ValueError("Fast Selected candidate unexpectedly carries measured evidence")
        fingerprints.append(fingerprint)
    winner = sorted((a["wearer_key"], a["slot"], a["artifact_id"]) for a in result["winner"])
    if winner != fingerprints[0]["ids"] or _decimal(result["formula_dps"]) != _decimal(rows[0]["formula_dps"]):
        raise ValueError("Selected winner identity or formula DPS differs from rank one")
    if len({x["set_group_key"] for x in fingerprints}) > options["set_group_limit"]:
        raise ValueError("Selected set group limit exceeded")
    winner_measured = _measured(result) if ordinary else None
    if ordinary and winner_measured != fingerprints[0]["measured"]:
        raise ValueError("Ordinary Selected winner measurement differs from rank one")
    return {"legal_output_checked": True, "rows": fingerprints, "winner": winner,
            "formula_dps": str(_decimal(result["formula_dps"])),
            "warnings": result.get("warnings", []), "ranking_basis": result["ranking_basis"],
            "verification_policy": policy, "winner_measured": winner_measured,
            "search_elapsed_ms": wrapper.get("search_elapsed_ms")}


def exact_fast_parity(installed, candidate):
    keys = ("rows", "winner", "formula_dps", "warnings", "ranking_basis", "verification_policy")
    # A compact retained receipt rehydrates ID tuples as JSON arrays.
    old, new = json.loads(json.dumps(installed)), json.loads(json.dumps(candidate))
    differences = [key for key in keys if old[key] != new[key]]
    return {"passed": not differences, "differences": differences,
            "installed_rows": len(installed["rows"]), "candidate_rows": len(candidate["rows"])}


def run_adapter(session, captured: Path, target: Path, prepared, compact, raw, *, ordinary):
    stage_inputs(captured, target)
    started = time.monotonic()
    session._validate_optimizer_request(run_dir=target, started=started)
    preflight_seconds = time.monotonic() - started
    session._run_go_optimizer(prepared=prepared, compact=compact, run_dir=target, started=started)
    process_seconds = time.monotonic() - started - preflight_seconds
    if (sha(target / "request.json") != sha(captured / "request.json") or
            sha(target / "compact.json") != sha(captured / "compact.json") or
            (target / "finish-requested").exists()):
        raise ValueError("Selected shared inputs or Finish state changed during adapter run")
    wrapper = json.loads((target / "optimizer-output.json").read_text(encoding="utf-8"))
    if wrapper["product_result"].get("compact_ir_sha256") != canonical_sha256(compact):
        raise ValueError("Selected result is not bound to the freshly captured compact")
    return summarize_selected(wrapper, raw, ordinary=ordinary), {
        "preflight_seconds": preflight_seconds, "process_seconds": process_seconds}


def main() -> int:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--mode", choices=("fast-pair", "ordinary-smoke"), required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    job = owned_job()
    path = receipt_path(args.receipt)
    receipt = {"schema_version": 1, "mode": args.mode, "status": "preparing",
               "scope": "pinned Selected request; fresh compact; real Python adapter; no DB or install"}
    save_receipt(path, job, receipt, first=True)
    stage = "saved_request"
    try:
        raw = retained_request()
        if args.mode == "ordinary-smoke":
            raw = ordinary_request(raw)
        active = load_active_gcsim_optimizer_engine_context()
        assert_engine({"request": raw, "engine_sha256": raw["engine"]["artifact_sha256"]}, active)
        installed_sha, pointer_sha, production_sha = sha(INSTALLED), sha(POINTER), source_sha256()
        receipt.update(saved_request_path=str(SAVED_REQUEST.relative_to(ROOT)).replace("\\", "/"),
                       saved_request_sha256=SAVED_REQUEST_SHA256, request_sha256=canonical_sha256(raw),
                       installed_sha256=installed_sha, active_pointer_sha256=pointer_sha,
                       engine_sha256=active.artifact_sha256,
                       engine_tree_sha256=active.engine_tree_sha256,
                       engine_binding_sha256=active.binding_sha256,
                       production_source_sha256=production_sha)
        stage = "build"
        candidate = job / "selected-candidate.exe"
        go = shutil.which("go") or "C:/Program Files/Go/bin/go.exe"
        started = time.monotonic()
        with (job / "selected-build.log").open("w", encoding="utf-8") as log:
            built = subprocess.run([go, "build", "-mod=readonly", "-trimpath", "-o", str(candidate),
                                    "./cmd/gtt-optimizer"], cwd=SOURCE, stdout=log,
                                   stderr=subprocess.STDOUT, timeout=300, check=False)
        receipt["build_seconds"] = time.monotonic() - started
        if built.returncode:
            receipt["compiler_log_tail"] = (job / "selected-build.log").read_text(
                encoding="utf-8", errors="replace")[-3000:]
            raise RuntimeError(f"Selected source build failed with exit {built.returncode}")
        receipt["candidate_sha256"] = sha(candidate)
        if sha(INSTALLED) != installed_sha or source_sha256() != production_sha:
            raise ValueError("Installed optimizer or production source changed during build")
        stage = "fresh_capture"
        capture_dir = job / "fresh-capture"
        capture_dir.mkdir()
        if args.mode == "fast-pair":
            shutil.copy2(SAVED_REQUEST, capture_dir / "request.json")
            if sha(capture_dir / "request.json") != SAVED_REQUEST_SHA256:
                raise ValueError("Pinned Selected request changed while copying")
        else:
            _write_canonical(capture_dir / "request.json", raw)
        request_file_sha = sha(capture_dir / "request.json")
        receipt["request_file_sha256"] = request_file_sha
        prepared = {"request": raw, "request_sha256": canonical_sha256(raw)}
        capture_session = GcsimOptimizerGoSelectedSession(adapter_request(job, raw, INSTALLED))
        started = time.monotonic()
        compact = capture_session._prepare_formula_inputs(prepared=prepared, run_dir=capture_dir,
                                                          started=started)
        receipt["fresh_capture_seconds"] = time.monotonic() - started
        if compact.get("request_sha256") != prepared["request_sha256"] or sha(capture_dir / "request.json") != request_file_sha:
            raise ValueError("Fresh Selected compact is not bound to request")
        compact_sha = sha(capture_dir / "compact.json")
        receipt.update(compact_file_sha256=compact_sha, compact_sha256=canonical_sha256(compact),
                       compact_members=len(compact.get("members", ())))
        results = {}
        binaries = (("candidate", candidate),) if args.mode == "ordinary-smoke" else (
            ("installed", INSTALLED), ("candidate", candidate))
        for name, binary in binaries:
            stage = name + "_adapter"
            session = GcsimOptimizerGoSelectedSession(adapter_request(job, raw, binary))
            summary, timings = run_adapter(session, capture_dir, job / name,
                                           prepared, compact, raw, ordinary=args.mode == "ordinary-smoke")
            results[name] = summary
            receipt[name] = {"summary": summary, "timings": timings}
            receipt["status"] = name + "_complete"
            save_receipt(path, job, receipt)
        if args.mode == "fast-pair":
            stage = "parity"
            verdict = exact_fast_parity(results["installed"], results["candidate"])
            receipt["parity"] = verdict
            if not verdict["passed"]:
                raise ValueError("Selected source-built fast formula result differs from installed: " +
                                 ", ".join(verdict["differences"]))
        if (sha(INSTALLED) != installed_sha or sha(POINTER) != pointer_sha or
                source_sha256() != production_sha or sha(SAVED_REQUEST) != SAVED_REQUEST_SHA256 or
                sha(capture_dir / "request.json") != request_file_sha or
                sha(capture_dir / "compact.json") != compact_sha):
            raise ValueError("Selected binary, engine pointer, source, or immutable inputs changed")
        final_active = load_active_gcsim_optimizer_engine_context()
        assert_engine({"request": raw, "engine_sha256": raw["engine"]["artifact_sha256"]}, final_active)
        if final_active.engine_tree_sha256 != active.engine_tree_sha256:
            raise ValueError("Active engine tree changed during Selected gate")
        receipt["status"] = ORDINARY_PASS if args.mode == "ordinary-smoke" else FAST_PASS
        print("SELECTED_PROMOTION_GATE " + json.dumps({"status": receipt["status"],
              "receipt": str(path.relative_to(ROOT)).replace("\\", "/"),
              "candidate_sha256": receipt["candidate_sha256"],
              "request_sha256": receipt["request_sha256"]}), flush=True)
        return 0
    except BaseException as exc:
        receipt["status"] = "failed"
        receipt["failure"] = {"stage": stage, "type": type(exc).__name__, "message": str(exc)[:512]}
        raise
    finally:
        save_receipt(path, job, receipt)


if __name__ == "__main__":
    raise SystemExit(main())
