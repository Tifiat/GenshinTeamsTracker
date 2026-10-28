"""Two-seed, full-schema Gaming Melt trace of one frozen Theory point.

Run only inside one managed_optimizer_experiment job. Full trace files remain
inside that job; the separate receipt retains bounded hit/branch summaries.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
from run_workspace.gcsim.optimizer_go_inputs import prepare_optimizer_inputs
from tools.experiments.gcsim.mode_matrix import run_product_matrix as matrix
from tools.experiments.gcsim.theory_verification import run_case as base
from tools.experiments.gcsim.theory_verification.render import render_candidate_config
from tools.managed_optimizer_experiment import owned_job


CASE = base.ROOT / "tools/experiments/gcsim/theory_verification/cases/gaming_melt_saved_rank1.json"
CURRENT = base.ROOT / "docs/optimizer-evidence/2026-10-03-theory-current-matrix/gaming_melt_theory.json"
CURRENT_SHA256 = "1b44298224294625520a17bdcf28b50442170caeedc7748fd32a39548cb60fa8"
POINT = base.ROOT / "docs/optimizer-evidence/2026-10-03-theory-verification/matrix/gaming_melt_rank1_response.json"
POINT_SHA256 = "37157ae52a29285394ba5b22465591e817e44357f835ededeff7ebcd8d6677e6"
OWNER = "docs/optimizer-evidence/2026-10-03-theory-current-matrix/README.md"
MAX_CALLS = 2
TRACE_SCHEMA = 6
GAMING_PLUNGE_TAG = 3  # AttackTagPlunge in active pkg/core/attacks/attack.go.
SOURCE_FILES = (
    "tools/experiments/gcsim/theory_verification/trace_case.py",
    "tools/experiments/gcsim/theory_verification/run_case.py",
    "tools/experiments/gcsim/theory_verification/render.py",
    "run_workspace/gcsim/optimizer_go_inputs.py",
    "tools/experiments/gcsim/mode_matrix/run_product_matrix.py",
    "tools/managed_optimizer_experiment.py",
)


def bind_saved_sources() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Bind the historical case, current product receipt and prior point receipt."""
    case, entry, candidate, provenance = base.load_case(CASE, with_provenance=True)
    if case["case_id"] != "gaming_melt_saved_rank1" or entry["id"] != "gaming_melt_theory":
        raise ValueError("Gaming case or manifest entry changed")
    if base.digest(CURRENT) != CURRENT_SHA256 or base.digest(POINT) != POINT_SHA256:
        raise ValueError("Pinned Gaming product or point receipt changed")
    current, point = base.read_object(CURRENT), base.read_object(POINT)
    expected_profiles = [
        {"character_key": row["character_key"], "weapon_key": row["weapon_key"]}
        for row in entry["virtual_profiles"]
    ]
    source_input = current.get("input", {})
    product = current.get("product", {})
    current_candidates = product.get("candidates") if isinstance(product, dict) else None
    if not isinstance(current_candidates, list):
        raise ValueError("Current Gaming product candidates missing")
    rank_one = [row for row in current_candidates if isinstance(row, dict) and type(row.get("rank")) is int and row["rank"] == 1]
    if (
        current.get("schema_version") != 1 or current.get("execution", {}).get("success") is not True
        or product.get("status") != "success" or len(rank_one) != 1
        or not isinstance(source_input, dict)
        or source_input.get("run_id") != entry["id"]
        or source_input.get("team") != case["team"]
        or source_input.get("manifest_sha256") != case["manifest_sha256"]
        or source_input.get("profiles") != expected_profiles
        or source_input.get("profiles_sha256") != base.canonical_digest(entry["virtual_profiles"])
        or source_input.get("rotation_path") != entry["rotation_file"]
        or source_input.get("rotation_sha256") != case["rotation_sha256"]
        or current.get("cleanup", {}).get("job_absent_after_cleanup") is not True
    ):
        raise ValueError("Current Gaming Theory receipt input/product binding changed")
    chosen = rank_one[0]
    if chosen.get("packages") != candidate.get("packages") or chosen.get("allocations") != candidate.get("allocations"):
        raise ValueError("Historical case vector differs from current Gaming Theory rank one")
    if chosen.get("formula_dps") != candidate.get("formula_dps"):
        raise ValueError("Current Gaming Theory score differs from saved point")
    current_engine = current.get("binding", {})
    if (
        not isinstance(current_engine, dict)
        or current_engine.get("engine_id") != case["engine_id"]
        or current_engine.get("engine_artifact_sha256") != case["engine_artifact_sha256"]
    ):
        raise ValueError("Current Gaming Theory engine binding differs from case")

    point_input, point_binding = point.get("input", {}), point.get("binding", {})
    point_provenance = point.get("candidate_provenance", {})
    if (
        point.get("schema_version") != 1 or point.get("status") != "verification_completed"
        or point.get("case_id") != case["case_id"] or point.get("case_sha256") != base.digest(CASE)
        or not isinstance(point_input, dict) or not isinstance(point_binding, dict)
        or point_input.get("team") != case["team"]
        or point_input.get("manifest_sha256") != case["manifest_sha256"]
        or point_input.get("rotation_sha256") != case["rotation_sha256"]
        or point_input.get("seeds") != case["seeds"]
        or point_input.get("energy") != "infinite"
        or point_input.get("candidate", {}).get("packages") != candidate["packages"]
        or point_input.get("candidate", {}).get("allocations") != candidate["allocations"]
        or not isinstance(point_input.get("config_text"), str)
        or point_input.get("config_sha256") != base.text_digest(point_input["config_text"])
        or point_binding.get("engine_id") != case["engine_id"]
        or point_binding.get("artifact_sha256") != case["engine_artifact_sha256"]
        or point_provenance != provenance
        or point.get("cleanup", {}).get("verified_after_outer_runner") is not True
    ):
        raise ValueError("Prior Gaming point receipt binding changed")
    return case, entry, candidate, current, point


def _ignore_energy(config: str) -> bool:
    rows = re.findall(r"(?m)^options ([^;\r\n]+);\r?$", config)
    if len(rows) != 1:
        raise ValueError("Exactly one canonical options row required")
    flags = [token.split("=", 1)[1] for token in rows[0].split() if token.startswith("ignore_burst_energy=")]
    if len(flags) != 1 or flags[0] not in {"true", "false"}:
        raise ValueError("Exactly one Boolean ignore_burst_energy flag required")
    return flags[0] == "true"


def trace_request(config: str, seed: int) -> dict[str, Any]:
    if type(seed) is not int or seed <= 0 or seed >= 2**63:
        raise ValueError("Trace seed must be a positive int64")
    return {
        "schema_version": 1,
        "context_sha256": base.text_digest(config),
        "seed": str(seed),
        "iterations": 1,
        "workers": 1,
        "ignore_burst_energy": _ignore_energy(config),
    }


def engine_source_config_sha256(config: str) -> str:
    """Mirror ReadConfig's no-import row join for the exact bound LF config."""
    if "\r" in config or any(re.fullmatch(r'import "(.+)"', row) for row in config.split("\n")):
        raise ValueError("Full trace requires an LF-only config without imports")
    # ReadConfig splits at LF, then writes each row followed by LF, including
    # the empty final row when the input already ended in LF.
    return base.text_digest(config + "\n")


def _count_map(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, dict) or len(value) > 32:
        raise ValueError(f"{label} is missing or exceeds the bounded shape")
    if any(not isinstance(key, str) or not key or type(count) is not int or count < 0 for key, count in value.items()):
        raise ValueError(f"{label} has an invalid count")
    return dict(sorted(value.items()))


def summarize_full_trace(
    document: dict[str, Any], request: dict[str, Any], actors: list[str],
    *, source_config_sha256: str,
) -> dict[str, Any]:
    """Retain Gaming plunge Melt from actual trace flags, never EM coordinates."""
    if (
        document.get("schema_version") != TRACE_SCHEMA
        or document.get("capability") != "gtt_trace_equation_v6"
        or document.get("seed") != request["seed"]
        or document.get("context_sha256") != request["context_sha256"]
        or document.get("character_keys") != actors or len(actors) != 4
        or len(set(actors)) != 4 or "gaming" not in actors
        or document.get("source_config_sha256") != source_config_sha256
    ):
        raise ValueError("Full trace source/config/schema/character binding changed")
    for key in ("request_sha256", "source_config_sha256", "formula_sha256", "target_sha256"):
        value = document.get(key)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(f"Full trace {key} missing or malformed")
    frames = document.get("duration_frames")
    if type(frames) is not int or frames <= 0:
        raise ValueError("Full trace duration_frames invalid")
    hits = document.get("hits")
    if not isinstance(hits, list) or not hits:
        raise ValueError("Full trace has no hits")
    gaming = actors.index("gaming")
    totals = {name: {"count": 0, "reported_damage": 0.0} for name in ("total", "melted", "nonmelt")}
    amplified: list[Counter[str]] = [Counter() for _ in actors]
    for hit in hits:
        if not isinstance(hit, dict):
            raise ValueError("Full trace contains a malformed hit")
        index, tag, amped, amp_type = (
            hit.get("actor_index"), hit.get("attack_tag"), hit.get("amped"), hit.get("amp_type")
        )
        if (
            type(index) is not int or not 0 <= index < len(actors)
            or type(tag) is not int or type(amped) is not bool
            or not isinstance(amp_type, str)
        ):
            raise ValueError("Full trace hit actor/tag/amplification invalid")
        damage = base.finite_nonnegative(hit.get("reported_damage"), "trace reported_damage")
        if amped:
            amplified[index][amp_type or "unknown"] += 1
        if index == gaming and tag == GAMING_PLUNGE_TAG:
            group = "melted" if amped and amp_type == "melt" else "nonmelt"
            for name in ("total", group):
                totals[name]["count"] += 1
                totals[name]["reported_damage"] += damage
    if totals["total"]["count"] == 0:
        raise ValueError("Full trace has no Gaming tag-3 plunge hit")
    guard = document.get("guard_summary")
    if not isinstance(guard, dict):
        raise ValueError("Full trace guard_summary missing")
    if (
        type(guard.get("hit_count")) is not int or guard["hit_count"] != len(hits)
        or type(guard.get("reaction_topology_complete")) is not bool
        or type(guard.get("exact_replay_eligible")) is not bool
    ):
        raise ValueError("Full trace guard counts or branch flags invalid")
    topology = document.get("topology_events")
    if not isinstance(topology, list) or any(not isinstance(row, dict) for row in topology):
        raise ValueError("Full trace topology_events malformed")
    return {
        "seed": int(request["seed"]),
        "duration_frames": frames,
        "duration_seconds": frames / 60.0,
        "full_trace_schema_version": TRACE_SCHEMA,
        "trace_request_sha256": document["request_sha256"],
        "source_config_sha256": document["source_config_sha256"],
        "formula_sha256": document["formula_sha256"],
        "target_sha256": document["target_sha256"],
        "hit_count": len(hits),
        "gaming_tag3_plunge": {"damage_basis": "reported_damage_actual_hit", **totals},
        "amplified_hit_counts_by_actor": [
            {"actor_key": actor, "amp_type_counts": dict(sorted(amplified[index].items()))}
            for index, actor in enumerate(actors)
        ],
        "reaction_events": {
            "availability": "not_serialized_in_full_trace_v6",
            "per_actor": None,
        },
        "reaction_aura_topology_event_count": sum(row.get("phase") == "reaction" for row in topology),
        "guard": {
            "hit_count": guard.get("hit_count"),
            "formula_kind_counts": _count_map(guard.get("formula_kind_counts"), "formula_kind_counts"),
            "reaction_operator_counts": _count_map(guard.get("reaction_operator_counts"), "reaction_operator_counts"),
            "reaction_topology_complete": guard.get("reaction_topology_complete"),
            "exact_replay_eligible": guard.get("exact_replay_eligible"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    base.check_worker()
    receipt_path = base.inside_worker(args.receipt)
    if receipt_path.exists():
        raise FileExistsError(f"Refusing to replace trace evidence: {receipt_path}")
    job = owned_job()
    if job.parent != (base.ROOT / ".codex_tmp/managed-optimizer").resolve():
        raise ValueError("Trace scratch escaped Theory worker")
    for key in ("TMP", "TEMP", "GOCACHE", "GOTMPDIR", "GTT_MANAGED_GO_CACHE"):
        base.inside_worker(os.environ[key]).relative_to(job)

    case, entry, candidate, current, point = bind_saved_sources()
    source_hashes = {name: base.digest(base.ROOT / name) for name in SOURCE_FILES}
    engine = load_active_gcsim_optimizer_engine_context()
    binary, engine_root = base.inside_worker(engine.artifact_path), base.inside_worker(engine.engine_root)
    if (
        engine.engine_id != case["engine_id"] or engine.artifact_sha256 != case["engine_artifact_sha256"]
        or base.digest(binary) != engine.artifact_sha256
        or engine.binding_sha256 != current["binding"]["engine_binding_sha256"]
    ):
        raise ValueError("Active engine differs from bound Gaming receipts")
    base_dir = job / "gaming-melt-full-trace"
    prep = base_dir / "preparation"
    prep.mkdir(parents=True)
    request = matrix._request(entry, db_path=base.inside_worker(base.read_object(base.MANIFEST)["db_path"]), run_root=base_dir)
    if tuple(request.seeds) != tuple(case["seeds"]) or not request.infinite_energy_enabled:
        raise ValueError("Gaming Theory request seed/energy binding changed")
    wire = prepare_optimizer_inputs(request, prep, mode="theory")["request"]
    config = render_candidate_config(wire["context"]["prepared_config"]["text"], candidate,
                                     known_sets=base.known_sets(engine_root))
    if (
        config != point["input"]["config_text"]
        or base.text_digest(config) != point["input"]["config_sha256"]
        or wire["engine"]["binding_sha256"] != point["binding"]["engine_binding_sha256"]
        or wire["engine"]["source_manifest_sha256"] != point["binding"]["source_manifest_sha256"]
        or wire["engine"]["patch_manifest_sha256"] != point["binding"]["patch_manifest_sha256"]
    ):
        raise ValueError("Reprepared Gaming point differs from bound prior response")
    actors = re.findall(r"(?m)^([a-z][a-z0-9_]*) char [^;\r\n]+;\r?$", config)
    if actors != entry["characters"] or len(actors) != 4:
        raise ValueError("Rendered config declaration order differs from Gaming manifest")
    requests = [trace_request(config, seed) for seed in case["seeds"]]
    source_config_sha256 = engine_source_config_sha256(config)
    if any(row["ignore_burst_energy"] is not True for row in requests):
        raise ValueError("Gaming case requires ignore_burst_energy=true in rendered config")

    receipt: dict[str, Any] = {
        "schema_version": 1, "date": date.today().isoformat(), "owner": OWNER,
        "scope": "two fixed-seed full GCSIM traces of the exact saved/current Gaming Theory point; no optimizer, ordinary run, global optimum or physical-build claim",
        "status": "prepared_not_traced", "engine_calls": 0,
        "binding": {
            "case_path": CASE.relative_to(base.ROOT).as_posix(), "case_sha256": base.digest(CASE),
            "current_theory_path": CURRENT.relative_to(base.ROOT).as_posix(), "current_theory_sha256": base.digest(CURRENT),
            "prior_point_path": POINT.relative_to(base.ROOT).as_posix(), "prior_point_sha256": base.digest(POINT),
            "engine_id": engine.engine_id, "engine_artifact_sha256": engine.artifact_sha256,
            "engine_binding_sha256": engine.binding_sha256,
            "engine_binary": binary.relative_to(base.ROOT).as_posix(),
            "source_manifest_sha256": wire["engine"]["source_manifest_sha256"],
            "patch_manifest_sha256": wire["engine"]["patch_manifest_sha256"],
            "config_sha256": base.text_digest(config),
            "engine_source_config_sha256": source_config_sha256,
            "manifest_sha256": case["manifest_sha256"], "rotation_sha256": case["rotation_sha256"],
            "profiles_sha256": current["input"]["profiles_sha256"],
            "candidate_rank": 1, "candidate_formula_dps": candidate["formula_dps"],
            "candidate_vector_source": "current Theory rank one equals saved case and prior point allocation/package",
        },
        "source_sha256": source_hashes,
        "prior_ordinary_reaction_events": point.get("ordinary", {}).get("source_reactions_by_actor"),
        "trace_requests": requests,
        "traces": [],
        "limits": [
            "Full trace v6 does not serialize per-actor ReactionEvents; amplified hit flags are reported separately.",
            "Tag-3 Melt classification uses hit.amped and hit.amp_type, not EM coordinates.",
            "Two fixed seeds do not measure the ordinary 500-seed Melt distribution.",
        ],
        "cleanup": {"managed_job_relative": job.relative_to(base.ROOT).as_posix(),
                    "outer_cleanup_expected": True, "verified_after_outer_runner": False,
                    "removed_bytes": None},
    }
    started = time.monotonic()
    deadline = started + 180
    try:
        for trace_request_body in requests:
            if receipt["engine_calls"] >= MAX_CALLS:
                raise RuntimeError("Full trace call ceiling reached")
            seed = int(trace_request_body["seed"])
            folder = base_dir / f"seed-{seed}"
            folder.mkdir(parents=True)
            config_path, request_path, output_path = folder / "config.txt", folder / "request.json", folder / "full-trace.json"
            config_path.write_bytes(config.encode("utf-8"))
            request_path.write_text(json.dumps(trace_request_body, sort_keys=True), encoding="utf-8")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Full trace deadline reached")
            receipt["engine_calls"] += 1
            launched = time.monotonic()
            output = subprocess.run(
                [str(binary), "-gtt-trace-equation", str(request_path), "-c", str(config_path), "-out", str(output_path)],
                cwd=folder, env=dict(os.environ, GOMAXPROCS="4"), capture_output=True, text=True,
                errors="replace", timeout=min(remaining, 120),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if output.returncode:
                raise RuntimeError(f"GCSIM full trace failed: {(output.stdout + output.stderr)[-2500:]}")
            summary = summarize_full_trace(base.read_object(output_path), trace_request_body, actors,
                                           source_config_sha256=source_config_sha256)
            summary.update(full_trace_sha256=base.digest(output_path), full_trace_bytes=output_path.stat().st_size,
                           elapsed_ms=(time.monotonic() - launched) * 1000)
            receipt["traces"].append(summary)
        receipt["status"] = "trace_completed"
    except Exception as exc:
        receipt["status"] = "trace_failed"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        receipt["wall_ms"] = (time.monotonic() - started) * 1000
        try:
            if base.digest(binary) != engine.artifact_sha256 or load_active_gcsim_optimizer_engine_context() != engine:
                raise RuntimeError("Active engine changed during full trace")
        except Exception as exc:
            receipt["status"] = "trace_failed"
            receipt["binding_error"] = f"{type(exc).__name__}: {exc}"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        with receipt_path.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
    print(f"[gaming trace] {receipt['status']}; calls={receipt['engine_calls']}; receipt={receipt_path.relative_to(base.ROOT)}", flush=True)
    return 1 if receipt["status"] == "trace_failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
