"""One parent-reviewed matrix pair; never install a binary or modify the account.

Run only inside managed_optimizer_experiment.py. Prepare one immutable current
request through the button's adapter, run installed and experimental CLI on it,
and retain a bounded receipt before managed cleanup. No unattended matrix loop.
Owner: isolated speed gate in the Go optimizer design. Keep receipts/prototype
through integration review, then retire rejected overlays. Gaming stays deferred.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.managed_optimizer_experiment import owned_job
from tools.experiments.gcsim.mode_matrix.run_product_matrix import _expanded_manifest_entries, _request
from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsSession
from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsRequest
from run_workspace.gcsim.optimizer_go_selected import _prepare_inputs, _write_canonical
from tools.experiments.gcsim.search_hypotheses.run import (apply_timing_overlay,
    check, copy_variant_support, fingerprint, replace_once, sha)
from tools.experiments.gcsim.search_hypotheses.variants import apply_variant
from tools.experiments.gcsim.parametric_effects.capture_equivalence import (
    canonical_capture, capture_comparison_kind, encoded)

EVIDENCE = ROOT / "docs/optimizer-evidence/2026-09-27-search-hypotheses/matrix"
EVIDENCE_ROOT = ROOT / "docs/optimizer-evidence"
HISTORICAL_BASELINE_OWNER = EVIDENCE.parent / "combined.json"
MANIFEST = ROOT / "tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json"
HISTORICAL = ROOT / "tests/fixtures/gcsim_optimizer_go_v1/optimizer_archetype_full_matrix_lineage5_20260919.json"
INSTALLED = ROOT / "native/gcsim_optimizer/gtt-optimizer.exe"

MATRIX_VARIANTS = (
    "combined_narrow_reuse", "combined_exact_reuse", "wide_program_cache",
    "context_dispatch_memo", "player_point32_adaptive", "player_point96_adaptive",
    "player_point32", "player_refine_one", "player_safe_wide", "amount_plan",
)
EXACT_REUSE_VARIANTS = frozenset(("combined_exact_reuse", "wide_program_cache", "context_dispatch_memo", "player_safe_wide"))
HEURISTIC_VARIANTS = frozenset(("combined_narrow_reuse", "player_point32_adaptive",
                                "player_point96_adaptive", "player_point32", "player_refine_one", "amount_plan"))


def requires_exact_rows(variant):
    if variant not in MATRIX_VARIANTS or (variant in EXACT_REUSE_VARIANTS) == (variant in HEURISTIC_VARIANTS):
        raise ValueError(f"Matrix variant has no unique quality policy: {variant}")
    return variant in EXACT_REUSE_VARIANTS


def validated_evidence_dir(raw):
    target = Path(raw)
    target = (target if target.is_absolute() else ROOT / target).resolve()
    base = EVIDENCE_ROOT.resolve()
    if target == base or not target.is_relative_to(base):
        raise ValueError("Matrix evidence directory must be inside docs/optimizer-evidence")
    return target


def validated_reuse_baseline(raw, *, case, source_sha, installed_sha, manifest_sha):
    path = Path(raw).resolve(strict=True)
    if not path.is_relative_to(EVIDENCE_ROOT.resolve()):
        raise ValueError("Reused baseline must be retained optimizer evidence")
    reference = json.loads(path.read_text(encoding="utf-8"))
    for key, expected in (("case", case), ("source_sha256", source_sha),
                          ("installed_sha256", installed_sha), ("manifest_sha256", manifest_sha)):
        if reference.get(key) != expected:
            raise ValueError(f"Reused baseline {key} differs from current input")
    if reference.get("status") in (None, "preparing") or not all(
        reference.get(key) is True for key in ("installed_unchanged", "active_pointer_unchanged", "engine_unchanged")
    ):
        raise ValueError("Reused baseline lacks completed installed-run integrity checks")
    installed = [run for run in reference.get("runs", ()) if run.get("name") == "installed"]
    raw_request = reference.get("request")
    if (len(installed) != 1 or not isinstance(raw_request, dict) or
            not installed[0].get("legal_output_checked") or
            not installed[0].get("rows") or not installed[0].get("leaders") or
            not installed[0].get("captures") or
            not reference.get("request_sha256") or not reference.get("sources_sha256") or
            not reference.get("engine_sha256")):
        raise ValueError("Reused baseline lacks complete request/installed evidence")
    return path, reference, installed[0]


def prepare_reused_input(inp, raw_request, session, *, request_sha, sources_sha):
    _write_canonical(inp / "request.json", raw_request)
    session._prepare_formula_inputs(prepared={"request": raw_request}, run_dir=inp,
                                    started=time.monotonic())
    if sha(inp / "request.json") != request_sha or sha(inp / "set-sources.json") != sources_sha:
        raise ValueError("Active-engine regenerated request/source differs from retained baseline")


def _windows_process_memory(pid):
    """One optimizer-process sample; private peak is accumulated by polling."""
    if os.name != "nt":
        return None
    size_t = ctypes.c_size_t
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("page_fault_count", ctypes.c_ulong),
                    ("peak_working_set", size_t), ("working_set", size_t),
                    ("quota_peak_paged_pool", size_t), ("quota_paged_pool", size_t),
                    ("quota_peak_nonpaged_pool", size_t), ("quota_nonpaged_pool", size_t),
                    ("pagefile", size_t), ("peak_pagefile", size_t), ("private", size_t)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    psapi.GetProcessMemoryInfo.argtypes = (ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong)
    handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
    if not handle:
        return None
    try:
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return None
        return (int(counters.peak_working_set), int(counters.private), "windows_psapi")
    finally:
        kernel.CloseHandle(handle)


def _process_memory(pid):
    sample = _windows_process_memory(pid)
    if sample is not None:
        return sample
    try:
        import psutil  # optional; never install for the matrix
        info = psutil.Process(pid).memory_info()
        private = getattr(info, "private", None)
        return (int(getattr(info, "peak_wset", info.rss)),
                int(private) if private is not None else None, "psutil")
    except (ImportError, OSError, ValueError):
        return None


def run_measured(command, *, env, stdout, cwd=None, poll_seconds=0.1):
    """Bounded polling of the CLI child only; engine grandchildren excluded."""
    if not 0.02 <= poll_seconds <= 1.0:
        raise ValueError("Memory poll interval must be bounded")
    started = time.monotonic()
    process = subprocess.Popen(command, env=env, stdout=stdout, stderr=None, cwd=cwd)
    peak_working, peak_private, samples, source = None, None, 0, "unavailable"
    while True:
        sample = _process_memory(process.pid)
        if sample is not None:
            working, private, source = sample
            peak_working = working if peak_working is None else max(peak_working, working)
            if private is not None:
                peak_private = private if peak_private is None else max(peak_private, private)
            samples += 1
        if process.poll() is not None:
            break
        time.sleep(poll_seconds)
    elapsed = time.monotonic() - started
    return process.returncode, elapsed, {
        "scope": "optimizer_cli_process_only; excludes active_engine_children",
        "source": source, "poll_seconds": poll_seconds, "samples": samples,
        "peak_working_set_bytes": peak_working,
        "peak_private_bytes_sampled": peak_private,
    }


def store(path, receipt):
    data = (json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("Matrix pair receipt exceeds 2 MiB retention cap")
    pending = owned_job() / "matrix-receipt.pending.json"
    pending.write_bytes(data)
    pending.replace(path)


def summarize(output, request):
    rows = output["product_result"]["candidates"]
    check(rows, request)
    points = fingerprint(rows)
    result = {"rows": points, "leaders": [r for r in points if r["rank"] == 1],
              "legal_output_checked": True, "warnings": output["product_result"].get("warnings", [])}
    for key in ("search_seconds", "proposal_seconds", "search_expansions", "search_stop_reason",
                "total_elapsed_ms", "source_preparation_seconds", "neutral_model", "neutral_cycles",
                "neutral_package_joint", "effect_boundaries", "provider_timings", "search_config"):
        result[key] = output.get(key)
    result["stabilization"] = [{k: r.get(k) for k in ("evaluations", "accepted", "single_stationary", "stop")}
                               for r in output.get("neutral_stabilization", [])]
    return result


def compare(baseline, candidate):
    # Quality ranks are by score, not by serialization/group-discovery order.
    old = sorted(baseline["leaders"], key=lambda row: (-row["dps"], row["group"]))
    new = sorted(candidate["leaders"], key=lambda row: (-row["dps"], row["group"]))
    new_by_group = {r["group"]: r for r in new}
    groups = [{"group": r["group"], "old_dps": r["dps"],
               "new_dps": new_by_group.get(r["group"], {}).get("dps"),
               "delta": new_by_group[r["group"]]["dps"] - r["dps"] if r["group"] in new_by_group else None}
              for r in old]
    rank_deltas = [b["dps"] - a["dps"] for a, b in zip(old, new)]
    alternatives = {}
    for group in new_by_group:
        before = sorted((r["dps"] for r in baseline["rows"] if r["group"] == group), reverse=True)
        after = sorted((r["dps"] for r in candidate["rows"] if r["group"] == group), reverse=True)
        alternatives[group] = {"before_count": len(before), "after_count": len(after),
                               "rank_deltas": [b - a for a, b in zip(before, after)]}
    # Exact-source numerical path: no simulator confidence tolerance here.
    regressions = [f"leader_rank_{i + 1}" for i, d in enumerate(rank_deltas) if d < -1e-6]
    regressions += ["retained_group_leader" for row in groups if row["delta"] is not None and row["delta"] < -1e-6]
    if len(new) < len(old):
        regressions.append("fewer_bonus_groups")
    alternative_warnings = []
    for group, row in alternatives.items():
        if row["before_count"] and row["after_count"] < row["before_count"]:
            alternative_warnings.append({"group": group, "reason": "fewer_alternatives"})
        if any(d < -1e-6 for d in row["rank_deltas"]):
            alternative_warnings.append({"group": group, "reason": "lower_alternative_rank"})
    # Fingerprints made in-process contain ID tuples; retained JSON contains
    # arrays. Compare their JSON data meaning, not Python container types.
    exact_rows = json.loads(json.dumps(baseline["rows"])) == json.loads(json.dumps(candidate["rows"]))
    return {"exact_rows": exact_rows, "leader_rank_deltas": rank_deltas,
            "groups": groups, "alternatives": alternatives, "regressions": regressions,
            "alternative_review": alternative_warnings,
            "replaced_groups": [r["group"] for r in groups if r["new_dps"] is None],
            "search_speedup": baseline["search_seconds"] / candidate["search_seconds"]}


def captures(root):
    rows = {}
    for path in sorted(root.glob("contexts/context-*/seed-*/member.json.effects.json")):
        member = path.with_name("member.json").read_bytes()
        effects = path.read_bytes()
        # Node IDs/discovery order are not gameplay identities. The existing
        # gate keeps ordered expressions, events, ownership and multiplicity.
        canonical = canonical_capture(member, effects)
        independent = canonical_capture(member, effects, independent_status_adds=True)
        folded = canonical_capture(member, effects, independent_status_adds=True,
                                   fold_unbound_constants=True)
        algebraic = canonical_capture(member, effects, independent_status_adds=True,
                                      algebraic_commutative=True)
        rows[path.parent.parent.name + "/" + path.parent.name] = {
            "member_sha256": hashlib.sha256(member).hexdigest(),
            "sidecar_sha256": hashlib.sha256(effects).hexdigest(),
            "canonical_sha256": hashlib.sha256(encoded(canonical)).hexdigest(),
            "independent_status_sha256_v1": hashlib.sha256(encoded(independent)).hexdigest(),
            "independent_status_constant_fold_sha256_v1": hashlib.sha256(encoded(folded)).hexdigest(),
            "algebraic_capture_sha256_v1": hashlib.sha256(encoded(algebraic)).hexdigest(),
        }
    return rows


def point_screen_diagnostics(path, limit=16, width=512):
    """Retain only bounded marker snippets, never the CLI's raw stdout."""
    marker = b"HYPOTHESIS_POINT_SCREEN"
    rows = []
    with Path(path).open("rb") as stream:
        carry = b""
        while len(rows) < limit:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            data = carry + chunk
            pos = 0
            while len(rows) < limit:
                at = data.find(marker, pos)
                if at < 0:
                    break
                end = data.find(b"\n", at)
                if end < 0:
                    end = min(len(data), at + width)
                rows.append(data[at:end][:width].decode("utf-8", errors="replace"))
                pos = at + len(marker)
            carry = data[-(len(marker) - 1):]
    return rows


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--variant", choices=MATRIX_VARIANTS, default="combined_narrow_reuse")
    parser.add_argument("--evidence-dir", type=Path, default=EVIDENCE)
    parser.add_argument("--reuse-baseline", type=Path,
                        help="Reuse one complete retained installed run; regenerate active-engine sources")
    args = parser.parse_args()
    evidence = validated_evidence_dir(args.evidence_dir)
    strict_rows = requires_exact_rows(args.variant)
    if args.attempt not in (1, 2, 3):
        raise ValueError("At most three attempts per unresolved case")
    job = owned_job()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = {x["id"]: x for x in _expanded_manifest_entries(manifest) if x["mode"] == "all_sets"}
    if args.case not in entries or args.case == "gaming_melt_all_sets":
        raise ValueError("Unknown matrix row or deferred Gaming case")
    evidence.mkdir(parents=True, exist_ok=True)
    path = evidence / f"{args.case}-{args.variant}-attempt{args.attempt}.json"
    if path.exists():
        raise ValueError("Refusing to overwrite retained matrix evidence")
    installed_sha = sha(INSTALLED)
    pointer = ROOT / "data/gcsim/engines/active_engine.json"
    pointer_sha = sha(pointer)
    receipt = {"schema_version": 2, "case": args.case, "attempt": args.attempt, "variant": args.variant,
               "scope": ("retained installed reference plus fresh candidate/active-engine sources; not a new paired wall sample"
                         if args.reuse_baseline else
                         "paired frozen current input; actual active-engine CLI; formula quality, not n500 verification"),
               "installed_sha256": installed_sha, "manifest_sha256": sha(MANIFEST),
               "quality_policy": "exact_rows_required" if strict_rows else "heuristic_quality_review",
               "baseline_owner": str(HISTORICAL_BASELINE_OWNER.relative_to(ROOT)).replace("\\", "/"),
               "baseline_owner_sha256": sha(HISTORICAL_BASELINE_OWNER),
               "historical_sha256": sha(HISTORICAL), "runs": [], "status": "preparing"}
    engine = None
    reference = None
    reference_installed = None
    try:
        source = ROOT / "native/gcsim_optimizer"
        native = job / "candidate-source"
        files = sorted(p for p in source.rglob("*") if p.is_file() and (p.suffix == ".go" or p.name in {"go.mod", "go.sum"}))
        receipt["source_sha256"] = hashlib.sha256(b"".join(str(p.relative_to(source)).encode() + b"\0" + p.read_bytes() for p in files)).hexdigest()
        previous = json.loads(HISTORICAL_BASELINE_OWNER.read_text(encoding="utf-8"))
        if receipt["source_sha256"] != previous["source_sha256"] or installed_sha != previous["installed_sha256"]:
            raise ValueError("Production source/installed baseline differs from the validated hypothesis input")
        if args.reuse_baseline:
            reference_path, reference, reference_installed = validated_reuse_baseline(
                args.reuse_baseline, case=args.case, source_sha=receipt["source_sha256"],
                installed_sha=installed_sha, manifest_sha=receipt["manifest_sha256"])
            raw = reference["request"]
            engine = Path(raw["engine"]["binary_path"]).resolve(strict=True)
            active = json.loads(pointer.read_text(encoding="utf-8"))
            if (sha(engine) != reference["engine_sha256"] or
                    sha(engine) != raw["engine"]["artifact_sha256"] or
                    active.get("active_engine_id") not in engine.parts):
                raise ValueError("Retained engine no longer matches the active engine")
            receipt.update(reference_baseline_reused=True,
                           reference_baseline_path=str(reference_path.relative_to(ROOT)).replace("\\", "/"),
                           reference_baseline_sha256=sha(reference_path),
                           input_reconstruction="retained_request_active_engine_sources_no_account_db")
        for original in files:
            target = native / original.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
        apply_timing_overlay(native)
        apply_variant(native, args.variant, replace_once)
        copy_variant_support(native, args.variant, job)
        candidate = job / "candidate.exe"
        go = shutil.which("go") or "C:/Program Files/Go/bin/go.exe"
        with (job / "build.log").open("w", encoding="utf-8") as log:
            result = subprocess.run([go, "build", "-trimpath", "-o", str(candidate), "./cmd/gtt-optimizer"], cwd=native, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError((job / "build.log").read_text(encoding="utf-8")[-6000:])
        receipt["candidate_sha256"] = sha(candidate)
        entry = entries[args.case]
        inp = job / "input"
        inp.mkdir()
        started = time.monotonic()
        if reference is not None:
            # This object is only used for source regeneration and the CLI
            # environment. Its DB/team fields are never consulted in this route.
            request = GcsimOptimizerGoAllSetsRequest(
                db_path=str(job / "unused-account.db"), selected_team={}, team_index=0,
                rotation_shell_text="", infinite_energy_enabled=bool(entry.get("infinite_energy", True)),
                run_root=str(job / "runs"), fast_mode=True, set_group_limit=7, builds_per_group=7)
            session = GcsimOptimizerGoAllSetsSession(request)
            raw = reference["request"]
            prepare_reused_input(inp, raw, session,
                                 request_sha=reference["request_sha256"],
                                 sources_sha=reference["sources_sha256"])
        else:
            frozen_db = job / "account-snapshot.db"
            with sqlite3.connect((ROOT / manifest["db_path"]).resolve().as_uri() + "?mode=ro", uri=True) as live:
                with sqlite3.connect(frozen_db) as snapshot:
                    live.backup(snapshot)
            request = replace(_request(entry, db_path=frozen_db, run_root=job / "runs"),
                              fast_mode=True, set_group_limit=7, builds_per_group=7)
            prepared = _prepare_inputs(request, inp, virtual_artifact_policy=GcsimOptimizerGoAllSetsSession.virtual_artifact_policy)
            session = GcsimOptimizerGoAllSetsSession(request)
            session._prepare_formula_inputs(prepared=prepared, run_dir=inp, started=started)
            raw = prepared["request"]
        receipt["shared_input_preparation_seconds"] = time.monotonic() - started
        engine = Path(raw["engine"]["binary_path"])
        receipt.update(request=raw, request_sha256=sha(inp / "request.json"), sources_sha256=sha(inp / "set-sources.json"),
                       inventory_sha256=hashlib.sha256(json.dumps(raw["artifacts"], sort_keys=True).encode()).hexdigest(),
                       rotation_file=entry["rotation_file"], virtual_profiles=entry["virtual_profiles"], engine_sha256=sha(engine))
        if receipt["engine_sha256"] != raw["engine"]["artifact_sha256"]:
            raise ValueError("Active engine artifact mismatch")
        historical = json.loads(HISTORICAL.read_text(encoding="utf-8"))
        receipt["historical"] = [{"id": r["id"], "wall_seconds": r.get("wall_seconds"),
                                  "product": r.get("product"), "engine_identity": r.get("engine_identity")}
                                 for r in historical.get("runs", []) if r.get("id") == args.case]
        if reference_installed is not None:
            reused = dict(reference_installed)
            reused["process_seconds_historical"] = reused.pop("process_seconds", None)
            reused["search_seconds_historical"] = reused["search_seconds"]
            reused["timing_origin"] = "retained_reference_not_rerun"
            receipt["runs"].append(reused)
            receipt["status"] = "reference_baseline_reused"
        store(path, receipt)
        execution = [(args.variant, candidate)] if reference is not None else [("installed", INSTALLED), (args.variant, candidate)]
        # Counterbalance teams rather than doubling every expensive run. This
        # does not make one paired wall-time sample a statistical speed proof.
        if reference is None and list(entries).index(args.case) % 2 == 0:
            execution.reverse()
        receipt["execution_order"] = [name for name, _ in execution]
        for name, binary in execution:
            if sha(inp / "request.json") != receipt["request_sha256"] or sha(inp / "set-sources.json") != receipt["sources_sha256"]:
                raise ValueError("Shared input changed between paired runs")
            work = job / name
            work.mkdir()
            env = session._optimizer_environment()
            env["GTT_RULE_CACHE_DIR"] = str(work / "rule-cache")
            command = [str(binary), "optimize-all-sets", str(inp / "request.json"), str(inp / "set-sources.json"), str(work / "verification")]
            print(f"Starting {args.case}: {name}", flush=True)
            with (work / "stdout.json").open("w", encoding="utf-8") as stdout:
                returncode, elapsed, process_memory = run_measured(command, env=env, stdout=stdout)
            if returncode:
                raise RuntimeError(f"{name} exited {returncode}: " + (work / "stdout.json").read_text(encoding="utf-8")[-6000:])
            if sha(inp / "request.json") != receipt["request_sha256"] or sha(inp / "set-sources.json") != receipt["sources_sha256"]:
                raise ValueError("Optimizer mutated shared input")
            output = json.loads((work / "verification/all-sets-result.json").read_text(encoding="utf-8"))
            row = summarize(output, raw)
            row.update(name=name, process_seconds=elapsed, process_memory=process_memory,
                       point_screen_diagnostics=point_screen_diagnostics(work / "stdout.json"),
                       captures=captures(work / "verification"))
            receipt["runs"].append(row)
            receipt["status"] = name + "_complete"
            store(path, receipt)
            print(json.dumps({"case": args.case, "variant": name, "seconds": row["search_seconds"],
                              "leader_dps": row["leaders"][0]["dps"], "rows": len(row["rows"])}), flush=True)
        by_name = {r["name"]: r for r in receipt["runs"]}
        baseline, candidate_result = by_name["installed"], by_name[args.variant]
        receipt["comparison"] = compare(baseline, candidate_result)
        if reference is not None:
            receipt["comparison"]["timing_basis"] = "historical_installed_vs_fresh_candidate_not_paired"
        common = baseline["captures"].keys() & candidate_result["captures"].keys()
        receipt["common_captures_raw_equal"] = bool(common) and all(baseline["captures"][k] == candidate_result["captures"][k] for k in common)
        exact_49 = (receipt["comparison"]["exact_rows"] and len(baseline["rows"]) == 49 and
                    len(candidate_result["rows"]) == 49)
        receipt["capture_comparison_kinds"] = {
            k: capture_comparison_kind(baseline["captures"][k], candidate_result["captures"][k],
                                       allow_algebraic=exact_49) for k in sorted(common)}
        receipt["algebraic_capture_gate_exact_49"] = exact_49
        receipt["common_captures_equal"] = bool(common) and all(
            kind != "unmatched" for kind in receipt["capture_comparison_kinds"].values())
        receipt["capture_key_difference"] = {
            "baseline_only": sorted(baseline["captures"].keys() - candidate_result["captures"].keys()),
            "candidate_only": sorted(candidate_result["captures"].keys() - baseline["captures"].keys())}
        pass_status = "reference_baseline_reused_gate_pass" if reference is not None else "paired_formula_gate_pass"
        receipt["status"] = "quality_regression" if receipt["comparison"]["regressions"] else pass_status
        if strict_rows and not receipt["comparison"]["exact_rows"]:
            receipt["status"] = "exact_reuse_parity_failed"
        elif not receipt["common_captures_equal"] or any(receipt["capture_key_difference"].values()):
            receipt["status"] = "capture_evidence_review_required"
        elif receipt["comparison"]["alternative_review"] and receipt["status"] == pass_status:
            receipt["status"] = "alternative_quality_review_required"
    except BaseException as exc:
        receipt["status"] = "failed"
        receipt["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        receipt["installed_unchanged"] = sha(INSTALLED) == installed_sha
        receipt["active_pointer_unchanged"] = sha(pointer) == pointer_sha
        receipt["engine_unchanged"] = engine is None or sha(engine) == receipt.get("engine_sha256")
        store(path, receipt)
    if not all(receipt[k] for k in ("installed_unchanged", "active_pointer_unchanged", "engine_unchanged")):
        raise RuntimeError("Installed engine/consumer changed during the paired experiment")
    print("PAIR_RESULT " + json.dumps({"case": args.case, "status": receipt["status"],
          "reference_baseline_reused": reference is not None,
          "common_captures_equal": receipt["common_captures_equal"], "comparison": receipt["comparison"]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
