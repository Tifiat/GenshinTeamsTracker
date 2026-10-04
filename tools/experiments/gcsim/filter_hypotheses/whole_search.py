"""Managed same-executable baseline/gate comparison on one saved Chasca request.

Uses the actual All Sets CLI coordinator with strictly bound saved neutral
captures. Only output fast_mode changes, equally for both variants: no new
ordinary finalist simulation, fallback engine, account/settings write or install.
All overlays, CLI binaries, raw output and caches die with the managed job.
"""
from __future__ import annotations

import argparse
import hashlib
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
from tools.managed_optimizer_experiment import assert_unlinked, owned_job
from tools.experiments.gcsim.filter_hypotheses.run import (
    MAX_RECEIPT_BYTES, digest, receipt_target,
)
from run_workspace.gcsim.engine_store import GcsimEngineStore

EVIDENCE = ROOT / "docs/optimizer-evidence/2026-10-03-filter-hypotheses/whole-search"
NATIVE = ROOT / "native/gcsim_optimizer"
HERE = Path(__file__).resolve().parent
GO = "C:/Program Files/Go/bin/go.exe"
# Reviewed pre-promotion baseline. Git supplies this one source file to an
# overlay; never rewind the checkout or use a different engine/source bundle.
BASELINE_REVISION = "bde62f972ac77c50bffcf6f54cd08beeb0558457"


def source_digest():
    files = sorted(p for p in NATIVE.rglob("*") if p.is_file() and
                   (p.suffix == ".go" or p.name in {"go.mod", "go.sum"}))
    return hashlib.sha256(b"".join(p.relative_to(NATIVE).as_posix().encode() + b"\0" +
                                 p.read_bytes() for p in files)).hexdigest()


def make_overlay(job):
    replacements = {}
    for source, target in (
        ("neighborhood_gate.go", "internal/domain/hypothesis_neighborhood.go"),
        ("neighborhood_gate_test.go", "internal/domain/hypothesis_neighborhood_test.go"),
        ("search_hook.go", "internal/search/hypothesis_neighborhood.go"),
        ("search_hook_test.go", "internal/search/hypothesis_neighborhood_test.go"),
    ):
        replacements[str(NATIVE / target)] = str(HERE / source)
    edits = json.loads((HERE / "search_gate.patch.json").read_text(encoding="utf-8"))
    edits["cmd/gtt-optimizer/all_sets.go"] = [
        {"old": "setcontext.NewEffectEngineProvider(binding, captureRoot)",
         "new": "newHypothesisProvider(binding, captureRoot)"},
        {"old": '\twrapper["reservation_deferred"] = result.ReservationDeferred',
         "new": '\twrapper["hypothesis_search"] = search.HypothesisNeighborhoodSnapshot()\n\twrapper["reservation_deferred"] = result.ReservationDeferred'},
    ]
    for relative, changes in edits.items():
        original = NATIVE / relative
        if relative == "internal/search/candidates.go":
            code = subprocess.run(
                ["git", "show", f"{BASELINE_REVISION}:native/gcsim_optimizer/{relative}"],
                cwd=ROOT, capture_output=True, check=True, encoding="utf-8",
            ).stdout
        else:
            code = original.read_text(encoding="utf-8")
        for edit in changes:
            if code.count(edit["old"]) != 1:
                raise ValueError(f"Overlay drift: {relative}")
            code = code.replace(edit["old"], edit["new"], 1)
        generated = job / relative
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text(code, encoding="utf-8")  # Generated mechanical overlay.
        replacements[str(original)] = str(generated)
    # Reuse the accepted strict saved-capture provider, excluding its test driver.
    provider = (HERE.parent / "search_hypotheses/replay_test.go").read_text(encoding="utf-8")
    if provider.count("func TestHypothesisReplay(") != 1:
        raise ValueError("Saved-capture provider has changed")
    provider = provider.split("func TestHypothesisReplay(")[0]
    for unused in ('\n\t"runtime"', '\n\t"testing"'):
        if provider.count(unused) != 1:
            raise ValueError("Saved-capture provider import has changed")
        provider = provider.replace(unused, "", 1)
    provider_path = job / "provider_replay.go"
    provider_path.write_text(provider, encoding="utf-8")  # Generated reusable-provider slice.
    replacements[str(NATIVE / "cmd/gtt-optimizer/hypothesis_provider.go")] = str(provider_path)
    overlay = job / "whole-overlay.json"
    overlay.write_text(json.dumps({"Replace": replacements}), encoding="utf-8")
    return overlay


def rows_of(output, request):
    rows = output["product_result"]["candidates"]
    items = {a["artifact_id"]: a for a in request["artifacts"]}
    wearers = {w["wearer_key"] for w in request["wearers"]}
    slots = {"flower", "plume", "sands", "goblet", "circlet"}
    result, anchors, signatures, seen = [], {}, {}, set()
    for row in rows:
        ids = sorted((a["wearer_key"], a["slot"], a["artifact_id"]) for a in row["artifacts"])
        if (len(ids) != 20 or len({i[2] for i in ids}) != 20 or
                {(i[0], i[1]) for i in ids} != {(w, s) for w in wearers for s in slots} or
                any(i[2] not in items or items[i[2]]["slot"] != i[1] for i in ids)):
            raise ValueError("Illegal exported physical assignment")
        identity = tuple(ids)
        if identity in seen:
            raise ValueError("Duplicate exported assignment")
        seen.add(identity)
        group = row["set_group_key"]
        declared = json.loads(group)
        actual = []
        for w in sorted(wearers):
            counts = {}
            for owner, _, item_id in ids:
                if owner == w:
                    uid = items[item_id]["set_uid"]
                    counts[uid] = counts.get(uid, 0) + 1
            actual.append({"wearer_key": w, "bonuses": [
                {"set_uid": uid, "pieces": 4 if n >= 4 else 2}
                for uid, n in sorted(counts.items()) if n >= 2
            ]})
        if declared != actual:
            raise ValueError("Exported group does not match actual piece counts")
        signature = json.dumps(actual, sort_keys=True)
        if signatures.setdefault(group, signature) != signature or len(set(signatures.values())) != len(signatures):
            raise ValueError("Groups duplicate/differ in physical bonuses")
        if group not in anchors:
            if row["alternative_rank"] != 1:
                raise ValueError("Group lacks its leader")
            anchors[group] = ids
        elif sum(a != b for a, b in zip(ids, anchors[group])) != 1:
            raise ValueError("Replacement is not exactly one physical item")
        result.append({"group": group, "rank": row["alternative_rank"],
                       "dps": row["formula_dps"], "ids": ids})
    return result


def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--controls-only", action="store_true")
    parser.add_argument("--reverse", action="store_true")
    args = parser.parse_args()
    job = owned_job()
    receipt_path = receipt_target(args.receipt, owner=EVIDENCE)
    run = Path(args.run).resolve(strict=True)
    if not run.is_relative_to((ROOT / "data/gcsim/optimizer-go-runs").resolve()):
        raise ValueError("Saved run outside this checkout")
    active = GcsimEngineStore().get_active_engine()
    original = json.loads((run / "request.json").read_text(encoding="utf-8"))
    binary = Path(original["engine"]["binary_path"]).resolve(strict=True)
    engine_sha = original["engine"]["artifact_sha256"]
    if active is None or binary.parent.parent != active.path.resolve() or digest(binary) != engine_sha:
        raise ValueError("Saved input does not bind the current active engine")
    protected = {str(p): digest(p) for p in (
        run / "request.json", run / "set-sources.json", run / "optimizer-output.json",
        ROOT / "settings.json", NATIVE / "gtt-optimizer.exe",
    )}
    native_sha = source_digest()
    receipt = {
        "scope": "complete All Sets CLI search using exact saved active-engine captures; no ordinary verification or install",
        "request_sha256": protected[str(run / "request.json")],
        "engine_id": active.engine_id, "engine_sha256": engine_sha,
        "native_source_sha256": native_sha, "installed_optimizer_sha256": protected[str(NATIVE / "gtt-optimizer.exe")],
        "baseline_revision": BASELINE_REVISION,
        "prototype_sha256": {p.name: digest(p) for p in HERE.iterdir() if p.suffix in {".go", ".py", ".json"}},
        "saved_capture_provider_sha256": digest(HERE.parent / "search_hypotheses/replay_test.go"),
        "runs": [], "status": "preparing",
    }
    env = dict(os.environ, GTT_HYPOTHESIS_SAVED=str(run),
               GTT_RULE_BUNDLED_CACHE_DIR=str(NATIVE / "set-rule-cache"),
               PYTHONDONTWRITEBYTECODE="1")
    try:
        overlay = make_overlay(job)
        request = json.loads(json.dumps(original))
        old_fast = request["result_options"]["fast_mode"]
        request["result_options"]["fast_mode"] = True
        request_path = job / "request.json"
        request_path.write_text(json.dumps(request, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        sources_path = job / "set-sources.json"
        shutil.copy2(run / "set-sources.json", sources_path)
        receipt["controlled_request_sha256"] = digest(request_path)
        receipt["input_changes"] = {"fast_mode": [old_fast, True], "all_other_fields_equal": True}
        receipt["counts"] = request["result_options"]
        tests = [GO, "test", "-overlay", str(overlay), "./internal/domain", "./internal/search",
                 "-run", "TestHypothesisNeighborhood", "-count=1", "-v", "-timeout", "60s"]
        checked = subprocess.run(tests, cwd=NATIVE, env=env, check=False)
        receipt["controls_exit_code"] = checked.returncode
        if checked.returncode:
            raise RuntimeError("neighborhood controls failed")
        if args.controls_only:
            receipt["status"] = "controls_pass"
            return 0
        executable = job / "gtt-neighborhood.exe"
        compiled = subprocess.run([GO, "build", "-overlay", str(overlay), "-o", str(executable),
                                   "./cmd/gtt-optimizer"], cwd=NATIVE, env=env, check=False)
        receipt["build_exit_code"] = compiled.returncode
        if compiled.returncode:
            raise RuntimeError("research CLI build failed")
        receipt["research_executable_sha256"] = digest(executable)
        reference = None
        for name, flag in ([('gate', '1'), ('baseline', '0')] if args.reverse else
                           [('baseline', '0'), ('gate', '1')]):
            child_env = dict(env, GTT_NEIGHBORHOOD_GATE=flag, GTT_RULE_CACHE_DIR=str(job / f"cache-{name}"))
            started = time.perf_counter()
            with (job / f"progress-{name}.log").open("wb") as log:
                process = subprocess.run([str(executable), "optimize-all-sets", str(request_path),
                                          str(sources_path), str(job / name)], cwd=NATIVE,
                                         env=child_env, stdout=subprocess.DEVNULL, stderr=log, check=False)
            elapsed = time.perf_counter() - started
            if process.returncode:
                diagnostic = (job / f"progress-{name}.log").read_bytes()[-4000:].decode("utf-8", errors="replace")
                receipt["failed_child"] = {"name": name, "exit_code": process.returncode,
                                           "elapsed_seconds": elapsed, "diagnostic_tail": diagnostic}
                raise RuntimeError(f"research CLI failed: {name}; diagnostic retained in receipt")
            output = json.loads((job / name / "all-sets-result.json").read_text(encoding="utf-8"))
            rows = rows_of(output, request)
            data = {"name": name, "elapsed_seconds": elapsed, "search_seconds": output["search_seconds"],
                    "search_expansions": output["search_expansions"], "stop": output["search_stop_reason"],
                    "row_count": len(rows), "row_fingerprint": fingerprint(rows),
                    "top_dps": rows[0]["dps"], "hypothesis": output["hypothesis_search"],
                    "warnings": output["product_result"]["warnings"],
                    "parse_cache": output.get("rule_parse_cache"),
                    "source_seconds": output.get("source_preparation_seconds"),
                    "neutral_cycles": output.get("neutral_cycles")}
            receipt["runs"].append(data)
            print(f"{name}: {data['search_seconds']:.3f}s search; {len(rows)} rows; {data['search_expansions']} expansions", flush=True)
            if reference is None:
                reference = rows
                receipt["reference_rows"] = rows
            else:
                receipt["exact_rows"] = reference == rows
                receipt["same_ordered_score_trace"] = receipt["runs"][0]["hypothesis"]["ordered_score_sha256"] == data["hypothesis"]["ordered_score_sha256"]
                receipt["same_scored_count"] = receipt["runs"][0]["hypothesis"]["scored"] == data["hypothesis"]["scored"]
                receipt["same_work_stop"] = all(receipt["runs"][0][key] == data[key] for key in ("stop", "search_expansions"))
                if not all(receipt[k] for k in ("exact_rows", "same_ordered_score_trace", "same_scored_count", "same_work_stop")):
                    raise RuntimeError("complete-search parity failed")
        receipt["status"] = "complete_search_pair_pass"
        return 0
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["failure"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        after = GcsimEngineStore().get_active_engine()
        unchanged = (after is not None and active.engine_id == after.engine_id and
                     digest(binary) == engine_sha and source_digest() == native_sha and
                     all(digest(path) == sha for path, sha in protected.items()))
        receipt["protected_inputs_unchanged"] = unchanged
        if not unchanged:
            receipt["status"] = "protected_state_changed"
        payload = (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if len(payload) > MAX_RECEIPT_BYTES:
            raise ValueError("Whole-search receipt exceeds finite size budget")
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path = receipt_target(receipt_path, owner=EVIDENCE)
        with receipt_path.open("xb") as stream:
            stream.write(payload)
        if not unchanged:
            raise RuntimeError("Protected input/installed state changed")


if __name__ == "__main__":
    raise SystemExit(main())
