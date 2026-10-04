"""Gate the physical-only filter through real adapters, optionally install it.

Owned managed scratch contains builds, fresh captures, outputs and rollback.
Uses frozen retained requests, never an account DB, app or another worker.
No ordinary finalist runs: both variants explicitly use the same fast options.
Retire with this dated H4 research phase; receipts are immutable and bounded.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsRequest, GcsimOptimizerGoAllSetsSession
from run_workspace.gcsim.optimizer_go_contracts import canonical_sha256, write_canonical
from run_workspace.gcsim.optimizer_go_selected import GcsimOptimizerGoSelectedRequest, GcsimOptimizerGoSelectedSession
from run_workspace.gcsim.optimizer_go_requests import DEFAULT_OPTIMIZER_BINARY
from tools.experiments.gcsim.search_hypotheses.promotion_gate import assert_engine
from tools.experiments.gcsim.filter_hypotheses.run import MAX_RECEIPT_BYTES, digest, receipt_target
from tools.experiments.gcsim.filter_hypotheses.whole_search import EVIDENCE, GO, NATIVE, fingerprint, rows_of, source_digest
from tools.managed_optimizer_experiment import owned_job

SAVED = {
    "all_sets": ("all_sets-20261003-201232-82e3ec5d", "43db6218200f074fe182eaf66821f9b42e68f9fe39c07799f94e03fd3e65a6bf"),
    "selected": ("selected-20260928-122336-1a5e659e", "11532ecbe8925315e3f675c5b5680c72a7d32c2e1083a95d45af6e00927ab2ef"),
}


def accepted_pairs():
    pairs = [json.loads((EVIDENCE / name).read_text(encoding="utf-8"))
             for name in ("pair1.json", "pair2-reverse.json")]
    for pair in pairs:
        if pair.get("status") != "complete_search_pair_pass" or not all(pair.get(k) is True for k in (
                "exact_rows", "same_ordered_score_trace", "same_scored_count", "same_work_stop", "protected_inputs_unchanged")):
            raise ValueError("H4 pair failed its complete-search gates")
        by_name = {r["name"]: r for r in pair["runs"]}
        if by_name["gate"]["search_seconds"] >= by_name["baseline"]["search_seconds"]:
            raise ValueError("Both run orders must demonstrate a gain before promotion")
    if pairs[0]["reference_rows"] != pairs[1]["reference_rows"]:
        raise ValueError("The two research pairs disagree")
    return pairs[0]


def make_session(job, mode, raw, binary=None):
    request_type, session_type = (
        (GcsimOptimizerGoAllSetsRequest, GcsimOptimizerGoAllSetsSession) if mode == "all_sets" else
        (GcsimOptimizerGoSelectedRequest, GcsimOptimizerGoSelectedSession))
    options = raw["result_options"]
    kwargs = {} if binary is None else {"optimizer_binary_path": str(binary)}
    request = request_type(
        db_path=str(job / "unused.db"), selected_team={}, team_index=0,
        rotation_shell_text="", seeds=tuple(raw["stochastic"]["seeds"]), product_timeout_ms=0,
        set_group_limit=options["set_group_limit"], builds_per_group=options["builds_per_group"],
        expanded_limits=options.get("expanded_limits", False), fast_mode=True,
        run_root=str(job / "unused-runs"), **kwargs,
    )
    if binary is None and Path(request.optimizer_binary_path).resolve() != Path(DEFAULT_OPTIMIZER_BINARY).resolve():
        raise ValueError("Default adapter no longer resolves the installed path")
    return session_type(request)


def run_adapter(job, mode, raw, staged, prepared, compact, label, binary=None):
    target = job / f"{mode}-{label}"
    target.mkdir()
    for name in ("request.json", "set-sources.json" if mode == "all_sets" else "compact.json"):
        shutil.copy2(staged / name, target / name)
    session = make_session(job, mode, raw, binary)
    started = time.monotonic()
    session._validate_optimizer_request(run_dir=target, started=started)
    session._run_go_optimizer(prepared=prepared, compact=compact, run_dir=target, started=started)
    elapsed = time.monotonic() - started
    wrapper = json.loads((target / "optimizer-output.json").read_text(encoding="utf-8"))
    product = wrapper["product_result"]
    if (product["ranking_basis"] != "formula" or product.get("measured") is not None or
            "formula_only_unverified" not in product.get("warnings", ())):
        raise ValueError("Adapter failed to preserve formula-only mode")
    rows = rows_of(wrapper, raw)
    if not rows or any(c.get("measured") is not None for c in product["candidates"]):
        raise ValueError("Unexpected empty or ordinary finalist output")
    metadata = {"rows": len(rows), "row_sha256": fingerprint(rows), "top_dps": rows[0]["dps"],
                "elapsed_seconds": elapsed, "search_seconds": wrapper.get("search_seconds", wrapper.get("search_elapsed_ms", 0) / 1000),
                "warnings": product["warnings"], "command": session._optimizer_command(Path(session.request.optimizer_binary_path), target)}
    return rows, metadata


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--parent-reviewed", action="store_true")
    args = parser.parse_args()
    if args.install and not args.parent_reviewed:
        raise ValueError("Installation needs the parent's explicit review")
    job = owned_job()
    path = receipt_target(args.receipt, owner=EVIDENCE)
    reference = accepted_pairs()
    installed = Path(DEFAULT_OPTIMIZER_BINARY)
    previous = digest(installed)
    active = load_active_gcsim_optimizer_engine_context()
    native_sha = source_digest()
    protected = {str(ROOT / "settings.json"): digest(ROOT / "settings.json")}
    receipt = {"scope": "fresh active-engine captures and real All Sets/Selected adapters; formula-only; no account/UI/ordinary validation",
               "status": "preparing", "native_source_sha256": native_sha, "previous_optimizer_sha256": previous,
               "engine_id": active.engine_id, "engine_sha256": active.artifact_sha256, "modes": {}}
    changed = False
    backup = job / "previous-optimizer.exe"
    try:
        if previous != reference["installed_optimizer_sha256"]:
            raise ValueError("Installed consumer changed since reviewed pairs")
        candidate = job / "gtt-optimizer.exe"
        with (job / "native-checks.log").open("w", encoding="utf-8") as log:
            for command in ([GO, "vet", "./..."],
                            [GO, "test", "-p", "1", "./...", "-count=1", "-timeout", "120s"],
                            [GO, "build", "-mod=readonly", "-trimpath", "-o", str(candidate), "./cmd/gtt-optimizer"]):
                result = subprocess.run(command, cwd=NATIVE, stdout=log, stderr=subprocess.STDOUT, check=False)
                if result.returncode:
                    log.flush()
                    receipt["native_log_tail"] = (job / "native-checks.log").read_text(encoding="utf-8", errors="replace")[-4000:]
                    raise RuntimeError(f"Native validation failed: {command[1]}")
        receipt["native_checks"] = "vet and all package tests pass"
        expected = digest(candidate)
        receipt["candidate_optimizer_sha256"] = expected
        for mode in ("selected", "all_sets"):
            name, pinned = SAVED[mode]
            saved = ROOT / "data/gcsim/optimizer-go-runs" / name
            original_sha = digest(saved / "request.json")
            if pinned is not None and original_sha != pinned:
                raise ValueError("Saved request changed")
            protected[str(saved / "request.json")] = original_sha
            raw = json.loads((saved / "request.json").read_text(encoding="utf-8"))
            assert_engine({"request": raw, "engine_sha256": raw["engine"]["artifact_sha256"]}, active)
            old_fast = raw["result_options"]["fast_mode"]
            raw["result_options"]["fast_mode"] = True
            staged = job / f"{mode}-inputs"
            staged.mkdir()
            write_canonical(staged / "request.json", raw)
            prepared = {"request": raw, "request_sha256": canonical_sha256(raw)}
            started = time.monotonic()
            compact = make_session(job, mode, raw)._prepare_formula_inputs(prepared=prepared, run_dir=staged, started=started)
            entry = {"saved_request": name, "saved_request_sha256": original_sha,
                     "input_changes": {"fast_mode": [old_fast, True], "other_fields_equal": True},
                     "controlled_request_sha256": prepared["request_sha256"], "prepare_seconds": time.monotonic() - started,
                     "counts": raw["result_options"]}
            receipt["modes"][mode] = entry
            baseline_rows, entry["installed"] = run_adapter(job, mode, raw, staged, prepared, compact, "installed")
            candidate_rows, entry["candidate"] = run_adapter(job, mode, raw, staged, prepared, compact, "candidate", candidate)
            entry["exact_rows"] = baseline_rows == candidate_rows
            entry["same_warnings"] = entry["installed"]["warnings"] == entry["candidate"]["warnings"]
            if mode == "all_sets":
                entry["same_research_rows"] = fingerprint(candidate_rows) == fingerprint(reference["reference_rows"])
            if not entry["exact_rows"] or not entry["same_warnings"] or entry.get("same_research_rows") is False:
                raise ValueError(f"Product-path parity failed: {mode}")
            print(f"{mode}: {len(candidate_rows)} rows exactly match; installed {entry['installed']['search_seconds']:.3f}s / candidate {entry['candidate']['search_seconds']:.3f}s", flush=True)
        if source_digest() != native_sha or digest(installed) != previous:
            raise ValueError("Source/installed consumer changed during validation")
        final = load_active_gcsim_optimizer_engine_context()
        if final != active or any(digest(p) != sha for p, sha in protected.items()):
            raise ValueError("Protected engine/input changed")
        receipt["protected_inputs_unchanged"] = True
        if args.install:
            shutil.copy2(installed, backup)
            changed = True
            # Same-volume atomic publication; scratch owns the rollback bytes.
            os.replace(candidate, installed)
            if digest(installed) != expected:
                raise ValueError("Installed bytes differ from tested candidate")
            # Recheck the DEFAULT path after publication. The numerical paired
            # runs above used these exact bytes; no redundant full search.
            for mode in ("selected", "all_sets"):
                raw = json.loads((job / f"{mode}-inputs/request.json").read_text(encoding="utf-8"))
                session = make_session(job, mode, raw)
                session._validate_optimizer_request(run_dir=job / f"{mode}-inputs", started=time.monotonic())
            if (digest(installed) != expected or source_digest() != native_sha or
                    load_active_gcsim_optimizer_engine_context() != active or
                    any(digest(p) != sha for p, sha in protected.items())):
                raise ValueError("Installed candidate or protected inputs changed after publication")
            receipt["installed_optimizer_sha256"] = digest(installed)
            receipt["default_path_preflight_pass"] = True
        receipt["installed"] = args.install
        receipt["status"] = "installed_adapter_parity_pass" if args.install else "adapter_parity_pass"
        return 0
    except BaseException as exc:
        if changed and digest(installed) != previous:
            shutil.copy2(backup, installed)
            receipt["rolled_back"] = digest(installed) == previous
        receipt["status"] = "failed"
        receipt["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        payload = (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if len(payload) > MAX_RECEIPT_BYTES:
            raise ValueError("Promotion receipt exceeds finite retention")
        path.parent.mkdir(parents=True, exist_ok=True)
        receipt_target(path, owner=EVIDENCE)
        with path.open("xb") as stream:
            stream.write(payload)


if __name__ == "__main__":
    raise SystemExit(main())
