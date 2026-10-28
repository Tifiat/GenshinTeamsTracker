"""Managed-only GCSIM point verification of one frozen theoretical build.

Research boundary: no optimizer search, installation, account writes or matrix
loop. Owner/retention: docs/optimizer-evidence/2026-10-03-theory-verification.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from hoyolab_export.paths import PROJECT_ROOT
from run_workspace.gcsim.artifact_investment_rules import ARTIFACT_INVESTMENT_RULES_SHA256
from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
from run_workspace.gcsim.optimizer_go_inputs import prepare_optimizer_inputs
from tools.experiments.gcsim.mode_matrix import run_product_matrix as matrix
from tools.experiments.gcsim.theory_verification.render import render_candidate_config
from tools.managed_optimizer_experiment import owned_job

OWNER = "docs/optimizer-evidence/2026-10-03-theory-verification/README.md"
MANIFEST = ROOT / "tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json"
HISTORICAL_MATRIX = ROOT / "tests/fixtures/gcsim_optimizer_go_v1/optimizer_archetype_full_matrix_lineage5_20260919.json"
HISTORICAL_MATRIX_SHA256 = "00a0cd81711081e867faf06cad9230471ada6c4ecd956104181a69187231a152"
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_CALLS = 3
SOURCES = (
    "tools/experiments/gcsim/theory_verification/run_case.py",
    "tools/experiments/gcsim/theory_verification/render.py",
    "tools/experiments/gcsim/mode_matrix/run_product_matrix.py",
    "run_workspace/gcsim/artifact_investment_rules.py",
    "run_workspace/gcsim/optimizer_go_inputs.py",
    "run_workspace/gcsim/selected_team_config.py",
    "tools/managed_optimizer_experiment.py",
)


def inside_worker(value: str | Path) -> Path:
    path = Path(value).expanduser()
    resolved = (path if path.is_absolute() else ROOT / path).resolve()
    resolved.relative_to(ROOT.resolve())
    return resolved


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_digest(value: Any) -> str:
    return text_digest(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON number: {value}")


def read_object(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"JSON exceeds {MAX_FILE_BYTES} bytes: {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return value


def finite_nonnegative(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"Invalid {label}")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"Non-finite or negative {label}")
    return number


def _source_engine_identity(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("Candidate source has no engine identity")
    engine_id, artifact = value.get("id"), value.get("artifact_sha256")
    if not isinstance(engine_id, str) or not engine_id or not isinstance(artifact, str) or not re.fullmatch(r"[0-9a-f]{64}", artifact):
        raise ValueError("Candidate source engine identity is invalid")
    result = {"id": engine_id, "artifact_sha256": artifact}
    for key in ("source_manifest_sha256", "patch_manifest_sha256"):
        extra = value.get(key)
        if extra is not None:
            if not isinstance(extra, str) or not re.fullmatch(r"[0-9a-f]{64}", extra):
                raise ValueError(f"Candidate source {key} is invalid")
            result[key] = extra
    return result


def _ranked_candidate(product: Any, rank: int) -> dict[str, Any]:
    if not isinstance(product, dict) or product.get("status") != "success":
        raise ValueError("Candidate source product did not succeed")
    rows = product.get("candidates")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Candidate source candidates are malformed")
    matches = [row for row in rows if type(row.get("rank")) is int and row["rank"] == rank]
    if len(matches) != 1:
        raise ValueError("Candidate source rank ambiguous/missing")
    return matches[0]


def select_candidate_source(
    case: dict[str, Any], entry: dict[str, Any], ref: dict[str, Any],
    document: dict[str, Any], source: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve a hash-checked saved candidate and its comparison provenance.

    Historical matrix rows have no original profile/rotation hashes. The exact
    current entry match identifies the intended case, but cannot reconstruct
    those absent historical input hashes.
    """
    rank = ref.get("rank")
    if type(rank) is not int or rank < 1:
        raise ValueError("Candidate source rank must be a positive integer")
    provenance: dict[str, Any] = {
        "path": source.relative_to(ROOT).as_posix(),
        "sha256": ref["sha256"],
        "rank": rank,
        "current_manifest_sha256": case["manifest_sha256"],
        "current_rotation_sha256": case["rotation_sha256"],
    }
    if "run_id" in ref:
        if source != HISTORICAL_MATRIX.resolve() or ref["sha256"] != HISTORICAL_MATRIX_SHA256:
            raise ValueError("Historical run_id requires the pinned lineage-5 matrix fixture")
        run_id = ref["run_id"]
        if not isinstance(run_id, str) or run_id != entry.get("id"):
            raise ValueError("Historical run_id differs from the current manifest entry")
        if document.get("schema_version") != 1 or document.get("manifest") != read_object(MANIFEST).get("name"):
            raise ValueError("Historical matrix schema/name differs from the current manifest")
        runs = document.get("runs")
        if not isinstance(runs, list) or any(not isinstance(row, dict) for row in runs):
            raise ValueError("Historical matrix runs are malformed")
        matches = [row for row in runs if row.get("id") == run_id]
        if len(matches) != 1:
            raise ValueError("Historical run_id ambiguous/missing")
        row = matches[0]
        if (
            row.get("mode") != "theory" or row.get("status") != "success"
            or row.get("success") is not True or row.get("infinite_energy") is not True
            or row.get("characters") != entry.get("characters")
            or row.get("rotation_file") != entry.get("rotation_file")
            or ("team" in row and row["team"] != case["team"])
            or entry.get("team") != case["team"]
        ):
            raise ValueError("Historical Theory run differs from the exact current matrix entry")
        candidate = _ranked_candidate(row.get("product"), rank)
        provenance.update(
            kind="historical_matrix_run", run_id=run_id,
            engine_identity=_source_engine_identity(row.get("engine_identity")),
            source_input_hashes={"profiles_sha256": None, "rotation_sha256": None},
            limitations=["Historical fixture omits original profile and rotation hashes; matching current manifest fields cannot prove identical historical inputs."],
        )
    else:
        if document.get("schema_version") != 1:
            raise ValueError("Candidate audit receipt schema changed")
        source_input = document.get("input")
        if not isinstance(source_input, dict):
            raise ValueError("Candidate audit receipt has no input binding")
        profiles = entry.get("virtual_profiles")
        expected_profiles = [
            {"character_key": row.get("character_key"), "weapon_key": row.get("weapon_key")}
            for row in profiles
        ] if isinstance(profiles, list) else []
        if (
            source_input.get("team") != case["team"]
            or source_input.get("run_id") != entry.get("id")
            or source_input.get("manifest_sha256") != case["manifest_sha256"]
            or source_input.get("rotation_path") != entry.get("rotation_file")
            or source_input.get("rotation_sha256") != case["rotation_sha256"]
            or source_input.get("profiles") != expected_profiles
            or source_input.get("profiles_sha256") != canonical_digest(profiles)
        ):
            raise ValueError("Candidate audit receipt differs from the bound current team/rotation")
        binding = document.get("binding")
        if not isinstance(binding, dict):
            raise ValueError("Candidate audit receipt has no engine binding")
        request_engine = binding.get("request_engine")
        if not isinstance(request_engine, dict):
            raise ValueError("Candidate audit receipt has no request engine binding")
        candidate = _ranked_candidate(document.get("product"), rank)
        provenance.update(
            kind="audited_product_receipt", run_id=source_input["run_id"],
            engine_identity=_source_engine_identity({
                "id": binding.get("engine_id"),
                "artifact_sha256": binding.get("engine_artifact_sha256"),
                "source_manifest_sha256": request_engine.get("source_manifest_sha256"),
                "patch_manifest_sha256": request_engine.get("patch_manifest_sha256"),
            }),
            source_input_hashes={
                "manifest_sha256": source_input["manifest_sha256"],
                "profiles_sha256": source_input.get("profiles_sha256"),
                "rotation_sha256": source_input["rotation_sha256"],
            },
            limitations=[],
        )
    return candidate, provenance


def compare_point_response(
    predicted: float | None, actual: float, *,
    source_provenance: dict[str, Any], active_engine_id: str, active_artifact_sha256: str,
) -> dict[str, Any]:
    """Classify one numeric witness without certifying historical/inline formulas."""
    actual = finite_nonnegative(actual, "fresh expected DPS")
    result: dict[str, Any] = {"fresh_two_seed_expected_dps": actual}
    if predicted is None:
        result["point_response_status"] = "no_formula_prediction"
        return result
    predicted = finite_nonnegative(predicted, "candidate formula DPS")
    delta = actual - predicted
    relation = "roundoff_match" if math.isclose(predicted, actual, rel_tol=1e-6, abs_tol=1e-6) else "different"
    result.update(formula_predicted_dps=predicted, delta_dps=delta,
                  relative_delta=delta / max(abs(actual), 1e-12), numerical_relation=relation)
    identity = source_provenance.get("engine_identity")
    if not isinstance(identity, dict):
        result["point_response_status"] = "unbound_formula_reference"
        result["comparison_scope"] = "inline_unbound"
    elif source_provenance.get("kind") == "historical_matrix_run":
        if identity.get("id") != active_engine_id or identity.get("artifact_sha256") != active_artifact_sha256:
            result["point_response_status"] = "historical_cross_engine_reference"
            result["comparison_scope"] = "historical_drift"
        else:
            result["point_response_status"] = "historical_input_hashes_missing"
            result["comparison_scope"] = "historical_unbound_inputs"
    elif identity.get("id") != active_engine_id or identity.get("artifact_sha256") != active_artifact_sha256:
        result["point_response_status"] = "cross_engine_reference"
        result["comparison_scope"] = "cross_engine_drift"
    else:
        result["point_response_status"] = "roundoff_match" if relation == "roundoff_match" else "mismatch_requires_attribution"
        result["comparison_scope"] = "same_engine_point_response"
    return result


def summarize_member(member: dict[str, Any], seed: int) -> dict[str, Any]:
    if member.get("seed") != seed:
        raise ValueError("Captured seed differs from requested seed")
    duration = finite_nonnegative(member.get("duration_ms"), "member duration")
    channels = member.get("channels")
    if duration == 0 or not isinstance(channels, list) or not channels:
        raise ValueError("Capture requires nonempty damage channels and duration")
    actor_damage: dict[str, float] = {}
    hits: dict[tuple[str, str, str, str], int] = {}
    for row in channels:
        actor = row.get("actor_key")
        if not isinstance(actor, str) or not actor:
            raise ValueError("Capture channel actor missing")
        damage = finite_nonnegative(row.get("baseline_damage"), "captured damage")
        actor_damage[actor] = actor_damage.get(actor, 0.0) + damage
        count = row.get("hit_count")
        if type(count) is not int or count < 0:
            raise ValueError("Capture hit_count invalid")
        key = (actor, str(row.get("damage_type")), str(row.get("attack_tag")), str(row.get("kind")))
        hits[key] = hits.get(key, 0) + count
    return {
        "seed": seed,
        "duration_ms": duration,
        "expected_dps": sum(actor_damage.values()) * 1000.0 / duration,
        "by_actor_expected_dps": {key: value * 1000.0 / duration for key, value in sorted(actor_damage.items())},
        "topology_sha256": member.get("topology_sha256"),
        "nodes": len(member.get("nodes", [])),
        "channels": len(channels),
        "channel_hit_counts": [dict(actor_key=a, damage_type=d, attack_tag=t, kind=k, hit_count=n)
                               for (a, d, t, k), n in sorted(hits.items())],
        "opaque_reasons": sorted({str(row["reason_code"]) for row in member.get("opaque_boundaries", []) if row.get("reason_code")}),
    }


def summarize_ordinary(payload: dict[str, Any], iterations: int) -> dict[str, Any]:
    stats = payload.get("statistics", {})
    if stats.get("iterations") != iterations:
        raise ValueError("Ordinary iteration count differs from requested count")
    dps = stats.get("dps", {})
    mean = finite_nonnegative(dps.get("mean"), "ordinary DPS mean")
    sd = finite_nonnegative(dps.get("sd"), "ordinary DPS SD")
    failed = stats.get("failed_actions", [])
    insufficient = [finite_nonnegative(row["insufficient_energy"]["max"], "failed energy metric") for row in failed]
    result = {"iterations": iterations, "dps": mean, "standard_deviation": sd,
              "standard_error": sd / math.sqrt(iterations),
              "insufficient_energy_max": max(insufficient, default=0.0),
              "rng": "ordinary GCSIM crypto-random seeds; not the fixed capture panel"}
    if "duration" in stats:
        duration = stats["duration"]
        if not isinstance(duration, dict):
            raise ValueError("Ordinary duration must be an object")
        # The active engine's overview aggregator divides frames by 60.
        result["duration_seconds"] = {
            "mean": finite_nonnegative(duration.get("mean", 0), "ordinary duration mean"),
            "sd": finite_nonnegative(duration.get("sd", 0), "ordinary duration SD"),
        }
    if "source_reactions" in stats:
        source_reactions = stats["source_reactions"]
        if not isinstance(source_reactions, list):
            raise ValueError("Ordinary source_reactions must be an array")
        per_index: list[dict[str, dict[str, float]]] = []
        for row in source_reactions:
            if not isinstance(row, dict):
                raise ValueError("Ordinary source reaction actor must be an object")
            sources = row.get("sources", {})
            if not isinstance(sources, dict):
                raise ValueError("Ordinary reaction sources must be an object")
            reactions: dict[str, dict[str, float]] = {}
            if any(not isinstance(name, str) or not name for name in sources):
                raise ValueError("Ordinary reaction source is malformed")
            for name in sorted(sources):
                description = sources[name]
                if not isinstance(description, dict):
                    raise ValueError("Ordinary reaction source is malformed")
                reactions[name] = {
                    "mean": finite_nonnegative(description.get("mean", 0), f"{name} reaction mean"),
                    "sd": finite_nonnegative(description.get("sd", 0), f"{name} reaction SD"),
                }
            per_index.append(reactions)
        result["source_reactions_by_declaration_index"] = per_index
    return result


def bind_ordinary_reaction_actors(summary: dict[str, Any], config: str) -> None:
    """Bind optional engine-indexed reaction counts to config declaration order."""
    if "source_reactions_by_declaration_index" not in summary:
        return
    actors = re.findall(r"(?m)^([a-z][a-z0-9_]*) char [^;\r\n]+;[ \t]*\r?$", config)
    rows = summary["source_reactions_by_declaration_index"]
    if len(actors) != 4 or len(set(actors)) != 4 or len(rows) != 4:
        raise ValueError("Ordinary reaction rows require exactly four declared actors in order")
    summary["source_reactions_by_actor"] = [
        {"declaration_index": index, "actor_key": actor, "reactions": rows[index]}
        for index, actor in enumerate(actors)
    ]
    del summary["source_reactions_by_declaration_index"]


def ordinary_options(config: str, iterations: int) -> str:
    rows = list(re.finditer(r"(?m)^(?P<indent>[ \t]*)options\s+(?P<body>[^;\r\n]+);[ \t]*$", config))
    if len(rows) != 1:
        raise ValueError("One canonical options row required")
    row = rows[0]
    tokens = row.group("body").split()
    seen: set[str] = set()
    kept = []
    for token in tokens:
        key = token.split("=", 1)[0]
        if key in seen:
            raise ValueError(f"Duplicate option {key}")
        seen.add(key)
        if key not in {"iteration", "workers"}:
            kept.append(token)
    replacement = f"{row.group('indent')}options {' '.join(kept)} iteration={iterations} workers=4;"
    return config[:row.start()] + replacement + config[row.end():]


def known_sets(engine_root: Path) -> set[str]:
    registry = engine_root / "pkg/core/keys/artifact.dm.go"
    source = registry.read_text(encoding="utf-8")
    match = re.search(r"var _SetNames\s*=\s*\[\.\.\.\]string\s*\{(?P<body>.*?)\}", source, re.S)
    if match is None:
        raise ValueError("Active GCSIM artifact registry shape changed")
    names = set(re.findall(r'"([a-z][a-z0-9_]*)"', match.group("body")))
    if not names:
        raise ValueError("Active GCSIM artifact registry is empty")
    return names


def check_worker() -> None:
    if Path(PROJECT_ROOT).resolve() != ROOT.resolve():
        raise ValueError("Product imports escaped the Theory worker")
    branch = subprocess.run(["git", "-C", str(ROOT), "branch", "--show-current"], check=True, capture_output=True, text=True).stdout.strip()
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    if branch != "codex/optimizer-theory" or head != "bde62f972ac77c50bffcf6f54cd08beeb0558457":
        raise ValueError(f"Worker branch/HEAD changed: {branch} {head}")


def load_case(
    path: Path, *, with_provenance: bool = False
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    case = read_object(path)
    if case.get("schema_version") != 1 or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", str(case.get("case_id", ""))):
        raise ValueError("Case schema/id invalid")
    if case.get("infinite_energy") is not True:
        raise ValueError("This Theory verification pilot supports explicit infinite energy only")
    if case.get("manifest_sha256") != digest(MANIFEST):
        raise ValueError("Saved profile matrix manifest changed")
    entries = matrix._expanded_manifest_entries(read_object(MANIFEST))
    rows = [row for row in entries if row.get("team") == case.get("team") and row.get("mode") == "theory"]
    if len(rows) != 1 or len(rows[0].get("virtual_profiles", [])) != 4:
        raise ValueError("Case requires exactly one saved virtual Theory team")
    entry = rows[0]
    rotation = inside_worker(entry["rotation_file"])
    if case.get("rotation_sha256") != digest(rotation):
        raise ValueError("Saved rotation changed")
    if ("candidate" in case) == ("candidate_source" in case):
        raise ValueError("Specify exactly one candidate or candidate_source")
    if "candidate" in case:
        candidate = case["candidate"]
        if not isinstance(candidate, dict):
            raise ValueError("Candidate object required")
        provenance: dict[str, Any] = {
            "kind": "inline_unbound", "path": None, "sha256": None,
            "run_id": None, "rank": candidate.get("rank"), "engine_identity": None,
            "current_manifest_sha256": case["manifest_sha256"],
            "current_rotation_sha256": case["rotation_sha256"],
            "source_input_hashes": None,
            "limitations": ["Inline formula DPS has no independently bound source engine or formula-point receipt."],
        }
    else:
        ref = case["candidate_source"]
        if not isinstance(ref, dict) or not isinstance(ref.get("path"), str):
            raise ValueError("Candidate source reference is malformed")
        source = inside_worker(ref["path"])
        source_hash = ref.get("sha256")
        if not isinstance(source_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", source_hash) or digest(source) != source_hash:
            raise ValueError("Candidate source receipt changed")
        document = read_object(source)
        candidate, provenance = select_candidate_source(case, entry, ref, document, source)
    seeds = case.get("seeds")
    if not isinstance(seeds, list) or len(seeds) != 2 or any(type(seed) is not int or seed < 0 or seed >= 2**63 for seed in seeds) or sorted(set(seeds)) != seeds:
        raise ValueError("Exactly two sorted distinct fixed seeds required")
    iterations = case.get("ordinary_iterations")
    if type(iterations) is not int or iterations not in {0, 128, 500}:
        raise ValueError("Ordinary iterations must be explicitly 0, 128 or 500")
    if with_provenance:
        return case, entry, candidate, provenance
    return case, entry, candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    check_worker()
    case_path, receipt_path = inside_worker(args.case), inside_worker(args.receipt)
    if receipt_path.exists():
        raise FileExistsError(f"Refusing to replace evidence: {receipt_path}")
    job = owned_job()
    if job.parent != (ROOT / ".codex_tmp/managed-optimizer").resolve():
        raise ValueError("Scratch escaped Theory worker")
    for key in ("TMP", "TEMP", "GOCACHE", "GOTMPDIR", "GTT_MANAGED_GO_CACHE"):
        inside_worker(os.environ[key]).relative_to(job)
    case, entry, candidate, provenance = load_case(case_path, with_provenance=True)
    source_hashes = {name: digest(ROOT / name) for name in SOURCES}
    engine = load_active_gcsim_optimizer_engine_context()
    binary, engine_root = inside_worker(engine.artifact_path), inside_worker(engine.engine_root)
    if engine.engine_id != case.get("engine_id") or engine.artifact_sha256 != case.get("engine_artifact_sha256") or digest(binary) != engine.artifact_sha256:
        raise ValueError("Active engine differs from frozen case binding")
    base = job / "cases" / case["case_id"]
    prep = base / "preparation"
    prep.mkdir(parents=True)
    request = matrix._request(entry, db_path=inside_worker(read_object(MANIFEST)["db_path"]), run_root=base)
    if tuple(request.seeds) != tuple(case["seeds"]) or not request.infinite_energy_enabled:
        raise ValueError("Case seed/energy policy differs from product preparation")
    wire = prepare_optimizer_inputs(request, prep, mode="theory")["request"]
    config = render_candidate_config(wire["context"]["prepared_config"]["text"], candidate, known_sets=known_sets(engine_root))
    predicted = candidate.get("formula_dps")
    if predicted is not None:
        predicted = finite_nonnegative(predicted, "predicted DPS")
    receipt: dict[str, Any] = {
        "schema_version": 1, "date": date.today().isoformat(), "owner": OWNER,
        "case_id": case["case_id"], "case_sha256": digest(case_path),
        "scope": "one frozen relaxed allocation, fresh installed-engine point response; not optimizer/global/physical/UI acceptance",
        "status": "prepared_not_verified", "engine_calls": 0,
        "binding": {"engine_id": engine.engine_id, "artifact_sha256": engine.artifact_sha256,
                    "engine_binary": binary.relative_to(ROOT).as_posix(),
                    "engine_binding_sha256": wire["engine"]["binding_sha256"],
                    "source_manifest_sha256": wire["engine"]["source_manifest_sha256"],
                    "patch_manifest_sha256": wire["engine"]["patch_manifest_sha256"]},
        "input": {"team": case["team"], "manifest_sha256": digest(MANIFEST),
                  "rotation_sha256": case["rotation_sha256"], "seeds": case["seeds"],
                  "energy": "infinite", "roll_budget_per_wearer": 45,
                  "roll_quality": "maximum-value equivalents, fractional relaxation",
                  "artifact_rules_sha256": ARTIFACT_INVESTMENT_RULES_SHA256,
                  "candidate": candidate, "config_text": config, "config_sha256": text_digest(config)},
        "candidate_provenance": provenance,
        "source_sha256": source_hashes, "captures": [],
        "comparison": {"formula_predicted_dps": predicted,
                       "point_response_status": "prepared_not_verified"},
        "cleanup": {"managed_job_relative": job.relative_to(ROOT).as_posix(), "outer_cleanup_expected": True,
                    "verified_after_outer_runner": False, "removed_bytes": None},
        "limits": ["Two fixed seeds establish a point witness, not general dependency coverage.",
                   "Fresh trace expected DPS uses actual engine hit damage with expected crit factors, not an offline candidate re-evaluation.",
                   "Ordinary seeds are crypto-random; ordinary means and fixed-panel expected values differ in RNG and schedules.",
                   "Fractional stat vectors do not prove realizability as five physical artifacts.",
                   "A mismatch requires schedule/response attribution; it does not identify its cause by itself."],
    }
    started = time.monotonic()
    deadline = started + 180

    def execute(arguments: list[str], folder: Path) -> float:
        if receipt["engine_calls"] >= MAX_CALLS:
            raise RuntimeError("Explicit engine call ceiling reached")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Verification deadline reached")
        receipt["engine_calls"] += 1
        print(f"[verification] engine call {receipt['engine_calls']}/{MAX_CALLS}", flush=True)
        launch = time.monotonic()
        output = subprocess.run(arguments, cwd=folder, env=dict(os.environ, GOMAXPROCS="4"),
                                capture_output=True, text=True, errors="replace", timeout=min(remaining, 120),
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if output.returncode:
            raise RuntimeError(f"GCSIM failed: {(output.stdout + output.stderr)[-2500:]}")
        return (time.monotonic() - launch) * 1000

    try:
        if not args.prepare_only:
            for seed in case["seeds"]:
                folder = base / "response" / f"seed-{seed}"
                folder.mkdir(parents=True)
                config_path, capture_path, member_path = folder / "config.txt", folder / "capture-request.json", folder / "member.json"
                config_path.write_text(config, encoding="utf-8", newline="")
                capture_path.write_text(json.dumps({"schema_version": 1, "output_mode": "compact_ir_v1",
                    "context_sha256": text_digest(config), "seed": str(seed), "iterations": 1, "workers": 1,
                    "ignore_burst_energy": True}), encoding="utf-8")
                elapsed = execute([str(binary), "-c", str(config_path), "-out", str(member_path), "-gtt-trace-equation", str(capture_path)], folder)
                summary = summarize_member(read_object(member_path), seed)
                summary.update(member_sha256=digest(member_path), elapsed_ms=elapsed)
                receipt["captures"].append(summary)
            actual = sum(row["expected_dps"] for row in receipt["captures"]) / 2
            receipt["comparison"].update(compare_point_response(
                predicted, actual, source_provenance=provenance,
                active_engine_id=engine.engine_id, active_artifact_sha256=engine.artifact_sha256,
            ))
            iterations = case["ordinary_iterations"]
            if iterations:
                folder = base / f"ordinary-n{iterations}"
                folder.mkdir()
                ordinary = ordinary_options(config, iterations)
                config_path, result_path = folder / "config.txt", folder / "result.json"
                config_path.write_text(ordinary, encoding="utf-8", newline="")
                elapsed = execute([str(binary), "-c", str(config_path), "-out", str(result_path)], folder)
                receipt["ordinary"] = summarize_ordinary(read_object(result_path), iterations)
                bind_ordinary_reaction_actors(receipt["ordinary"], config)
                receipt["ordinary"].update(elapsed_ms=elapsed, config_sha256=text_digest(ordinary), result_sha256=digest(result_path))
            receipt["status"] = "verification_completed"
    except Exception as exc:
        receipt["status"] = "verification_failed"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        receipt["wall_ms"] = (time.monotonic() - started) * 1000
        try:
            if digest(binary) != engine.artifact_sha256 or load_active_gcsim_optimizer_engine_context() != engine:
                raise RuntimeError("Active engine changed during point verification")
        except Exception as exc:
            receipt["status"] = "verification_failed"
            receipt["binding_error"] = f"{type(exc).__name__}: {exc}"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        with receipt_path.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
    print(f"[verification] {receipt['status']}; receipt={receipt_path.relative_to(ROOT)}", flush=True)
    return 1 if receipt["status"] == "verification_failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
