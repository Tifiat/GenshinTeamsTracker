"""Bounded post-change comparison; NEVER regenerates the supplied baseline.

Exactly one immutable before.json, one after.json, one report.md and one
install.json survive in the declared docs folder. The legacy receipt is capped
at 8 MiB (normally <=3 attempts per team); one explicitly authorized fourth
Lunar Bloom row may add up to 3 MiB, with an 11 MiB total cap. All build
caches, expanded runs and capture graphs use managed_scratch. No
equipment/settings/database writes. The installed optimizer is the button's
normal executable; the active engine is never replaced by this runner.
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

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.managed_optimizer_experiment import managed_scratch
from tools.experiments.gcsim.mode_matrix.run_product_matrix import (
    _artifact_catalog, _expanded_manifest_entries, _run_entry, _scratch_environment,
)

BASELINE = ROOT / "tests/fixtures/gcsim_optimizer_go_v1/optimizer_archetype_full_matrix_lineage5_20260919.json"
MANIFEST = ROOT / "tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json"
OUTPUT = ROOT / "docs/optimizer-evidence/all-sets-inventory-20260919"
BINARY = ROOT / "native/gcsim_optimizer/gtt-optimizer.exe"
MAX_RECEIPT = 8 * 1024 * 1024
MAX_AUTHORIZED_ROW = 3 * 1024 * 1024
MAX_AUTHORIZED_RECEIPT = 11 * 1024 * 1024
LUNAR_JOINT_ATTEMPT_CASE = "lunar_bloom_all_sets"
LUNAR_JOINT_ATTEMPT4_AUTHORIZATION = {
    "approval_reason": "User approved one additional Lunar Bloom matrix run after the three existing attempts.",
    "stage": "bounded joint package repair",
    "scope": LUNAR_JOINT_ATTEMPT_CASE,
    "attempt": 4,
    "search_budgets_changed": False,
}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def json_bytes(value):
    # Historical inventory/control identities depend on this exact encoding.
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def receipt_bytes(value):
    # Machine evidence keeps every field/attempt. Human-readable tables live in
    # report.md; repeated indentation must not crowd later rows out of the cap.
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def compact_search_work(rows):
    """Bound future receipts, never rewrite already retained attempts.

    Detailed examples are NOT the full explored population. Preserve its exact
    hash, lane counts/totals and score extrema; all final verification and
    stabilization rows are retained separately by extract_work.
    """
    groups = {}
    for row in rows:
        lane = str(row.get("lane", ""))
        group = groups.setdefault(lane, {"count": 0, "expansions": 0,
            "search_seconds": 0.0, "capture_seconds": 0.0,
            "formula_min": row.get("formula_dps"), "formula_max": row.get("formula_dps")})
        group["count"] += 1
        group["expansions"] += row.get("Expansions", 0)
        group["search_seconds"] += row.get("SearchSeconds", 0)
        group["capture_seconds"] += row.get("CaptureSeconds", 0)
        score = row.get("formula_dps")
        if score is not None:
            group["formula_min"] = min(score, group["formula_min"] if group["formula_min"] is not None else score)
            group["formula_max"] = max(score, group["formula_max"] if group["formula_max"] is not None else score)
    # First/last plus strongest and slowest rows; max 64 examples regardless of
    # inventory size. Original order and precise individual fields survive.
    keep = set(range(min(8, len(rows)))) | set(range(max(0, len(rows)-8), len(rows)))
    keep.update(sorted(range(len(rows)), key=lambda i: rows[i].get("formula_dps", 0), reverse=True)[:24])
    keep.update(sorted(range(len(rows)), key=lambda i: rows[i].get("SearchSeconds", 0), reverse=True)[:24])
    return [rows[i] for i in sorted(keep)], {
        "schema_version": 1, "full_count": len(rows), "retained_count": len(keep),
        "full_sha256": sha(json_bytes(rows)), "lanes": groups,
        "detail_complete": len(keep) == len(rows),
    }

def validate_lunar_joint_attempt4(args, runs):
    """Return the fixed approval record only for the one authorized fourth row."""
    if not args.authorize_lunar_bloom_joint_package_attempt_4:
        return None
    if args.case != LUNAR_JOINT_ATTEMPT_CASE:
        raise ValueError("Fourth-attempt authorization requires --case lunar_bloom_all_sets")
    if not args.retry:
        raise ValueError("Fourth-attempt authorization requires --retry")
    if args.only:
        raise ValueError("Fourth-attempt authorization cannot be combined with --only")
    prior = [row for row in runs if row.get("id") == LUNAR_JOINT_ATTEMPT_CASE]
    attempts = [row.get("attempt") for row in prior]
    if any(type(attempt) is not int for attempt in attempts) or sorted(attempts) != [1, 2, 3]:
        raise ValueError("Fourth-attempt authorization is valid only once after attempts 1-3")
    return dict(LUNAR_JOINT_ATTEMPT4_AUTHORIZATION)

def _has_lunar_attempt4_authorization(row):
    return (
        row.get("id") == LUNAR_JOINT_ATTEMPT_CASE
        and row.get("attempt") == 4
        and row.get("attempt_authorization") == LUNAR_JOINT_ATTEMPT4_AUTHORIZATION
    )

def preserve_before(source: Path, output: Path):
    data = source.read_bytes()
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("Baseline exceeds its finite retention limit")
    if output.exists():
        if output.read_bytes() != data:
            raise ValueError("Immutable baseline copy differs; refusing overwrite")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as stream:
            stream.write(data)
    return sha(data)

def store_after(path: Path, payload, scratch: Path):
    rows = payload["runs"]
    ids = [str(row["id"]) for row in rows]
    by_id = {key: [row for row in rows if str(row["id"]) == key] for key in set(ids)}
    auth_rows = [row for row in rows if "attempt_authorization" in row]
    lunar_attempts = [row.get("attempt") for row in by_id.get(LUNAR_JOINT_ATTEMPT_CASE, [])]
    if auth_rows and (
        len(auth_rows) != 1
        or not _has_lunar_attempt4_authorization(auth_rows[0])
        or any(type(attempt) is not int for attempt in lunar_attempts)
        or sorted(lunar_attempts) != [1, 2, 3, 4]
    ):
        raise ValueError("Invalid fourth-attempt authorization record")
    if len(set(ids)) > 14 or len(rows) > 43 or any(
        len(attempts) > 3 and not (
            key == LUNAR_JOINT_ATTEMPT_CASE
            and len(attempts) == 4
            and auth_rows
        )
        for key, attempts in by_id.items()
    ):
        raise ValueError("Post-change evidence retention/attempt limit exceeded")
    if auth_rows:
        authorized_row = auth_rows[0]
        legacy_payload = dict(payload)
        legacy_payload["runs"] = [row for row in rows if row is not authorized_row]
        if len(receipt_bytes(legacy_payload)) > MAX_RECEIPT:
            raise ValueError("Legacy post-change receipt exceeds 8 MiB")
        if len(receipt_bytes(authorized_row)) > MAX_AUTHORIZED_ROW:
            raise ValueError("Authorized fourth-attempt row exceeds 3 MiB")
    data = receipt_bytes(payload)
    if auth_rows:
        if len(data) > MAX_AUTHORIZED_RECEIPT:
            raise ValueError("Authorized post-change receipt exceeds 11 MiB")
    elif len(data) > MAX_RECEIPT:
        raise ValueError("Post-change receipt exceeds 8 MiB")
    temporary = scratch / "after.pending.json"
    temporary.write_bytes(data)
    temporary.replace(path)

def build_install(scratch: Path):
    before = sha(BINARY.read_bytes())
    candidate = scratch / "gtt-optimizer.exe"
    cache, temporary = scratch / "go-cache", scratch / "go-temp"
    cache.mkdir(); temporary.mkdir()
    env = dict(os.environ, GOCACHE=str(cache), GOTMPDIR=str(temporary))
    command = ["C:/Program Files/Go/bin/go.exe", "-C", str(ROOT / "native/gcsim_optimizer")]
    subprocess.run([*command, "test", "./..."], check=True, env=env)
    subprocess.run([*command, "build", "-trimpath", "-o", str(candidate), "./cmd/gtt-optimizer"], check=True, env=env)
    if sha(BINARY.read_bytes()) != before:
        raise ValueError("Installed optimizer changed during build")
    # Old executable is recoverable in this managed job until successful copy.
    backup = scratch / "previous-optimizer.exe"
    shutil.copy2(BINARY, backup)
    try:
        shutil.copy2(candidate, BINARY)
        if sha(BINARY.read_bytes()) != sha(candidate.read_bytes()):
            raise ValueError("Installed optimizer hash differs from tested build")
    except BaseException:
        shutil.copy2(backup, BINARY)
        raise
    record = {"previous_optimizer_sha256": before, "optimizer_sha256": sha(BINARY.read_bytes()),
              "installed_path": str(BINARY), "go_suite": "pass", "engine_changed": False,
              "time_unix": time.time()}
    (OUTPUT / "install.json").write_bytes(json_bytes(record))

def extract_work(scratch: Path):
    runs = sorted((scratch / "runs").glob("*"), key=lambda p: p.stat().st_mtime_ns)
    if not runs:
        return {}
    run = runs[-1]
    result = {}
    req = None
    request_path = run / "request.json"
    if request_path.is_file():
        req = json.loads(request_path.read_text(encoding="utf-8"))
        result["request_sha256"] = sha(request_path.read_bytes())
        result["inventory_sha256"] = sha(json_bytes(req["artifacts"]))
        result["prepared_config"] = req["context"]["prepared_config"]["text"]
    paths = sorted(run.glob("**/all-sets-result.json"))
    if paths:
        wrapper = json.loads(paths[0].read_text(encoding="utf-8"))
        for key in ("search_config", "search_work", "search_stop_reason", "capture_members", "search_expansions",
                    "guides", "queued", "unqueued_across_guides", "pending", "guide_seconds", "proposal_seconds",
                    "search_seconds", "provider_timings", "total_elapsed_ms", "reservation_deferred", "search_algorithm",
                    "neutral_cycles", "neutral_model", "neutral_joint_seconds", "neutral_package_joint",
                    "neutral_stabilization", "effect_boundaries"):
            result[key] = wrapper.get(key)
        if isinstance(result.get("search_work"), list):
            result["search_work"], result["search_work_summary"] = compact_search_work(result["search_work"])
        # Keep final-refinement coverage and every bounded ordinary comparison,
        # including the current-equipment anchor omitted by the top-five UI.
        result["verification"] = wrapper.get("verification")
        if req is not None:
            # Freeze only the displayed top-three items BEFORE scratch cleanup.
            # A later inventory import must not silently change report substats.
            candidates = wrapper.get("product_result", {}).get("candidates", [])[:3]
            ids = {int(a["artifact_id"]) for c in candidates for a in c.get("artifacts", [])}
            if len(ids) > 60:
                raise ValueError("Top-three artifact receipt exceeds physical scope")
            result["finalist_artifact_rows"] = sorted(
                (a for a in req["artifacts"] if int(a["artifact_id"]) in ids),
                key=lambda a: int(a["artifact_id"]),
            )
    return result

def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--case", action="append", default=[], help="Select one exact matrix row (mutually exclusive with --only)")
    parser.add_argument("--retry", action="store_true")
    parser.add_argument(
        "--authorize-lunar-bloom-joint-package-attempt-4", action="store_true",
        help="Authorize only attempt 4 of lunar_bloom_all_sets for bounded joint package repair; requires --case lunar_bloom_all_sets and --retry",
    )
    parser.add_argument("--build-install", action="store_true")
    args = parser.parse_args()
    if len(args.case) > 1:
        raise ValueError("--case may be specified exactly once")
    args.case = args.case[0] if args.case else None
    baseline_sha = preserve_before(BASELINE, OUTPUT / "before.json")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = [e for e in _expanded_manifest_entries(manifest) if e["mode"] == "all_sets"]
    expected = {row["id"]: row for row in json.loads(BASELINE.read_text(encoding="utf-8"))["runs"] if row["mode"] == "all_sets"}
    if {e["id"] for e in entries} != set(expected) or len(entries) != 14:
        raise ValueError("Post-change manifest is not the supplied 14-team matrix")
    for entry in entries:
        for key in ("characters", "rotation_file", "infinite_energy"):
            if entry.get(key) != expected[entry["id"]].get(key):
                raise ValueError(f"Baseline input identity differs: {entry['id']} {key}")
    after = OUTPUT / "after.json"
    receipt = json.loads(after.read_text(encoding="utf-8")) if after.exists() else {
        "schema_version": 1, "before_sha256": baseline_sha, "scope": "post_change_same_product_sessions",
        "old_inventory_hash_available": False, "runs": [],
    }
    if receipt["before_sha256"] != baseline_sha:
        raise ValueError("Comparison baseline changed")
    done = {row["id"] for row in receipt["runs"]}
    if args.case and args.only:
        raise ValueError("Choose either --case or --only")
    selectors = [args.case] if args.case else args.only
    authorization = validate_lunar_joint_attempt4(args, receipt["runs"])
    if args.retry and len(selectors) != 1:
        raise ValueError("A retry must name exactly one diagnostic row")
    if args.only and not set(args.only) <= set(expected):
        raise ValueError("Unknown matrix row")
    if args.case and args.case not in expected:
        raise ValueError("Unknown matrix row")
    entries = [e for e in entries if (not selectors or e["id"] in selectors) and (args.retry or e["id"] not in done)]
    if any(sum(r["id"] == e["id"] for r in receipt["runs"]) >= 3 for e in entries):
        if not authorization or any(
            e["id"] != LUNAR_JOINT_ATTEMPT_CASE
            or sum(r["id"] == e["id"] for r in receipt["runs"]) != 3
            for e in entries
        ):
            raise ValueError("Three substantive attempts exhausted")
    db = ROOT / manifest["db_path"]
    catalog = _artifact_catalog(db)
    for entry in entries:
        # One disposable job per row bounds disk use even for the full matrix.
        with managed_scratch() as scratch, _scratch_environment(scratch):
            if args.build_install:
                build_install(scratch)
                args.build_install = False
            before_binary = sha(BINARY.read_bytes())
            print(f"Post-change {entry['id']}", flush=True)
            row = _run_entry(entry, db_path=db, scratch=scratch, catalog=catalog)
            row["input_entry"] = entry
            row["rotation_sha256"] = sha((ROOT / entry["rotation_file"]).read_bytes())
            row["optimizer_sha256"] = before_binary
            row["inventory_search"] = extract_work(scratch)
            if sha(BINARY.read_bytes()) != before_binary:
                raise ValueError("Optimizer binary changed during comparison")
            row["attempt"] = 1 + sum(r["id"] == entry["id"] for r in receipt["runs"])
            if authorization:
                row["attempt_authorization"] = authorization
            receipt["runs"].append(row)
            receipt["matrix_status"] = "row_complete_awaiting_parent_review" if row.get("success") else "stopped_on_failed_row"
            receipt["stop_reason"] = (
                f"Latest row {entry['id']} attempt {row['attempt']}; "
                "sequential matrix, no next row without parent review. Gaming remains deferred."
            )
            store_after(after, receipt, scratch)
            from tools.experiments.gcsim.all_sets_inventory_regression.report import write_report
            write_report(OUTPUT)
            print(f"Saved {entry['id']}: success={row.get('success')}", flush=True)
            if not row.get("success"):
                return 1  # diagnose the first failure; do not repeat it 14 times
    if BASELINE.read_bytes() != (OUTPUT / "before.json").read_bytes():
        raise ValueError("Source baseline mutated")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
