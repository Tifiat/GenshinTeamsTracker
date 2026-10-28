"""One bounded current Theory product-session reproduction for a saved team."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from hoyolab_export.paths import PROJECT_ROOT
from run_workspace.gcsim.engine_store import DEFAULT_GCSIM_ENGINE_STORE_DIR
from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
from run_workspace.gcsim.optimizer_go_requests import DEFAULT_OPTIMIZER_BINARY
from tools.experiments.gcsim.mode_matrix import run_product_matrix as matrix
from tools.managed_optimizer_experiment import owned_job

MANIFEST = ROOT / "tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json"
MANIFEST_SHA256 = "d00ed4463c535e136590548aad8e2d20f35a7efe8ca8bcb22a49b19c13ff1c86"
ROTATION = ROOT / "tools/experiments/gcsim/mode_matrix/rotations/lunar_charged_jahoda.txt"
RECEIPT = ROOT / "tests/fixtures/gcsim_optimizer_go_v1/theory_lunar_audit_20261003_v1.json"
RUN_ID = "lunar_charged_theory"
CURRENT_MATRIX_OWNER = "docs/optimizer-evidence/2026-10-03-theory-current-matrix/README.md"
LIMIT_MS = 360_000
CAPTURE_LIMIT = 32 * 1024 * 1024
SOURCE_FILES = (
    "tools/experiments/gcsim/mode_matrix/run_product_matrix.py",
    "tools/experiments/gcsim/theory_audit/run_lunar_audit.py",
    "tools/managed_optimizer_experiment.py",
    "run_workspace/gcsim/optimizer_go_theory.py",
    "run_workspace/gcsim/optimizer_go_all.py",
    "run_workspace/gcsim/optimizer_go_session.py",
    "run_workspace/gcsim/optimizer_go_inputs.py",
    "run_workspace/gcsim/optimizer_go_requests.py",
    "run_workspace/gcsim/optimizer_go_all_sources.py",
    "run_workspace/gcsim/optimizer_engine_context.py",
    "run_workspace/gcsim/engine_store.py",
)


def inside(path: Path, root: Path) -> Path:
    resolved = path.expanduser().resolve()
    resolved.relative_to(root.resolve())
    return resolved


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=RUN_ID)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-z][a-z0-9_]*_theory", args.run_id):
        parser.error("--run-id must name one saved Theory manifest run")
    if args.run_id != RUN_ID and args.receipt is None:
        parser.error("alternate --run-id requires an explicit new --receipt")
    if args.receipt is None:
        args.receipt = RECEIPT
    return args


def select_theory_entry(manifest: Mapping[str, Any], run_id: str) -> dict[str, Any]:
    matching = [row for row in matrix._expanded_manifest_entries(manifest) if row.get("id") == run_id]
    if len(matching) != 1:
        raise ValueError(f"Expected one saved run entry {run_id!r}")
    entry = matching[0]
    profiles = entry.get("virtual_profiles")
    if (
        entry.get("mode") != "theory" or entry.get("infinite_energy") is not True
        or not isinstance(entry.get("team"), str) or not entry["team"]
        or not isinstance(profiles, list) or len(profiles) != 4
        or any(not isinstance(row, Mapping) or not row.get("character_key") or not row.get("weapon_key") for row in profiles)
        or len({row["character_key"] for row in profiles}) != 4
        or entry.get("characters") != [row["character_key"] for row in profiles]
        or not isinstance(entry.get("rotation_file"), str) or not entry["rotation_file"]
    ):
        raise ValueError("Saved run is not one complete infinite-energy virtual Theory team")
    if run_id == RUN_ID and entry["team"] != "lunar_charged":
        raise ValueError("Default Theory audit no longer names Lunar Charged")
    return entry


def input_binding(entry: Mapping[str, Any], rotation: Path) -> dict[str, Any]:
    profiles = entry["virtual_profiles"]
    return {
        "run_id": entry["id"],
        "manifest_sha256": sha256(MANIFEST),
        "team": entry["team"],
        "profiles_sha256": canonical_sha256(profiles),
        "profiles": [
            {"character_key": row["character_key"], "weapon_key": row["weapon_key"]}
            for row in profiles
        ],
        "rotation_path": rotation.relative_to(ROOT.resolve()).as_posix(),
        "rotation_sha256": sha256(rotation),
    }


def safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(item) for item in value]
    return str(value)


def candidates(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = result.get("candidates")
    if not isinstance(rows, list):
        return []
    return [
        {
            "rank": row.get("rank"),
            "formula_dps": row.get("formula_dps"),
            "source": row.get("source"),
            "undistinguished_set_slots": safe(row.get("undistinguished_set_slots", [])),
            "packages": safe(row.get("packages", [])),
            "allocations": safe(row.get("allocations", [])),
            "opaque_reasons": safe(row.get("opaque_reasons", [])),
        }
        for row in rows
        if isinstance(row, Mapping)
    ]


def output_documents(run_dir: Path) -> list[tuple[str, Mapping[str, Any]]]:
    documents: list[tuple[str, Mapping[str, Any]]] = []
    for relative in ("optimizer-output.json", "theory/theory-result.json"):
        path = run_dir / relative
        if not path.is_file():
            continue
        document = load_json(path)
        documents.append((relative, document))
        for key in ("product_result", "theory_result", "result"):
            nested = document.get(key)
            if isinstance(nested, Mapping):
                documents.append((f"{relative}.{key}", nested))
    return documents


def proposal_report(result: Mapping[str, Any], run_dir: Path) -> dict[str, Any] | None:
    report = result.get("proposal_report")
    if not isinstance(report, Mapping):
        for _, document in output_documents(run_dir):
            candidate = document.get("proposal_report")
            if isinstance(candidate, Mapping):
                report = candidate
                break
    if not isinstance(report, Mapping):
        return None
    return {
        **{str(k): safe(v) for k, v in report.items() if k != "queue"},
        "report_keys": sorted(str(k) for k in report),
        "queue": [safe(row) for row in report.get("queue", []) if isinstance(row, Mapping)],
    }


def provider_timings(value: Any) -> dict[str, Any]:
    found: dict[str, Any] = {}

    def visit(node: Any, path: str = "", provider: bool = False) -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                name = str(key)
                next_path = f"{path}.{name}" if path else name
                context = provider or "provider" in name.casefold()
                if "timing" in name.casefold() and context:
                    found[next_path] = safe(child)
                visit(child, next_path, context)
        elif isinstance(node, list):
            for index, child in enumerate(node):
                visit(child, f"{path}[{index}]", provider)

    visit(value)
    return found


def capture_summary(run_dir: Path) -> dict[str, Any]:
    actor_set = re.compile(r"(?im)^\s*(?!#)[A-Za-z_][A-Za-z0-9_.-]*\s+add\s+set\s*=")
    contexts: dict[Path, list[Path]] = {}
    for config in run_dir.rglob("config.txt"):
        context = config.parent.parent
        contexts.setdefault(context, []).append(config)
    neutral_contexts = []
    for context, configs in contexts.items():
        config_members = [
            config.parent / "member.json"
            for config in configs
            if (config.parent / "member.json").is_file()
        ]
        if (
            len(configs) == 2
            and len(config_members) == 2
            and all(config.stat().st_size <= CAPTURE_LIMIT for config in configs)
            and all(not actor_set.search(config.read_text(encoding="utf-8", errors="replace")) for config in configs)
        ):
            neutral_contexts.append((context, sorted(config_members)))

    members = sorted(run_dir.rglob("member.json"))
    if len(neutral_contexts) != 1:
        return {
            "member_files_found": len(members),
            "neutral_contexts_found": len(neutral_contexts),
            "neutral_members_read": 0,
            "neutral_member_size_rejections": [],
            "member_size_limit_bytes": CAPTURE_LIMIT,
            "neutral_member_channel_hit_counts": [],
            "neutral_member_opaque_reason_code_counts": {},
            "jahoda_swirl_event_windows": {
                "on_swirl_electro_event_count": None,
                "active_actor_owner_match_count": None,
                "trigger_duration_coverage": "unverified",
            },
        }

    context, neutral = neutral_contexts[0]
    size_rejections = [
        {
            "member_path": path.relative_to(run_dir).as_posix(),
            "bytes": path.stat().st_size,
            "limit_bytes": CAPTURE_LIMIT,
        }
        for path in neutral
        if path.stat().st_size > CAPTURE_LIMIT
    ]
    if size_rejections:
        return {
            "member_files_found": len(members),
            "neutral_contexts_found": 1,
            "neutral_context": context.relative_to(run_dir).as_posix(),
            "neutral_members_read": 0,
            "neutral_member_size_rejections": size_rejections,
            "member_size_limit_bytes": CAPTURE_LIMIT,
            "neutral_member_channel_hit_counts": [],
            "neutral_member_opaque_reason_code_counts": {},
            "jahoda_swirl_event_windows": {
                "on_swirl_electro_event_count": None,
                "active_actor_owner_match_count": None,
                "trigger_duration_coverage": "unverified",
                "reason": "neutral member exceeded the configured read limit",
            },
        }

    formulas: list[dict[str, Any]] = []
    opaque = Counter()
    schemas: dict[str, list[str]] = {}
    for path in neutral:
        document = load_json(path)
        relative = path.relative_to(run_dir).as_posix()
        schemas[relative] = sorted(str(key) for key in document)
        channel_counts: Counter[tuple[str, str, str, str]] = Counter()
        for channel in document.get("channels", []):
            if not isinstance(channel, Mapping):
                continue
            actor_key = str(channel.get("actor_key") or "")
            tag = channel.get("attack_tag")
            damage_type = str(channel.get("damage_type") or "")
            kind = str(channel.get("kind") or "")
            count = channel.get("hit_count")
            if type(count) is int:
                channel_counts[(actor_key, damage_type, str(tag), kind)] += count
        for boundary in document.get("opaque_boundaries", []):
            if isinstance(boundary, Mapping):
                reason = str(boundary.get("reason_code") or "")
                if reason:
                    opaque[reason] += 1
        formulas.append(
            {
                "seed": path.parent.name,
                "member_path": relative,
                "channel_hit_counts": [
                    {
                        "actor_key": actor,
                        "damage_type": damage,
                        "attack_tag": tag,
                        "kind": kind,
                        "hit_count": count,
                    }
                    for (actor, damage, tag, kind), count in sorted(channel_counts.items())
                ],
            }
        )
    return {
        "member_files_found": len(members),
        "neutral_contexts_found": 1,
        "neutral_members_read": len(formulas),
        "neutral_member_size_rejections": [],
        "member_size_limit_bytes": CAPTURE_LIMIT,
        "neutral_context": context.relative_to(run_dir).as_posix(),
        "neutral_member_schema": schemas,
        "neutral_member_channel_hit_counts": formulas,
        "neutral_member_opaque_reason_code_counts": dict(sorted(opaque.items())),
        "jahoda_swirl_event_windows": {
            "on_swirl_electro_event_count": None,
            "active_actor_owner_match_count": None,
            "trigger_duration_coverage": "unverified",
            "reason": "the compact neutral member channel schema does not by itself prove trigger windows or uptime",
        },
    }


def scoped_capture_summary(run_dir: Path, run_id: str) -> dict[str, Any]:
    summary = capture_summary(run_dir)
    if run_id != RUN_ID:
        summary.pop("jahoda_swirl_event_windows", None)
    return summary


def main() -> int:
    args = parse_args()
    root = ROOT.resolve()
    if Path(PROJECT_ROOT).resolve() != root:
        raise RuntimeError(f"Project imports resolved outside worker: {PROJECT_ROOT}")
    branch = subprocess.run(
        ["git", "-C", str(root), "branch", "--show-current"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if branch != "codex/optimizer-theory" or head != "bde62f972ac77c50bffcf6f54cd08beeb0558457":
        raise RuntimeError(f"Worker branch/HEAD changed: {branch} {head}")
    receipt_path = args.receipt if args.receipt.is_absolute() else root / args.receipt
    receipt_path = inside(receipt_path, root)
    if receipt_path.exists():
        raise FileExistsError(f"Refusing to replace existing receipt: {receipt_path}")

    job = owned_job()
    if job.parent != (root / ".codex_tmp/managed-optimizer").resolve():
        raise RuntimeError("Managed job is outside this worker's scratch root")
    for key in ("TMP", "TEMP", "GOCACHE", "GOTMPDIR", "GTT_MANAGED_GO_CACHE"):
        value = os.environ.get(key)
        if not value or not inside(Path(value), job).is_relative_to(job.resolve()):
            raise RuntimeError(f"{key} is not bound inside the managed job")

    if sha256(MANIFEST) != MANIFEST_SHA256:
        raise ValueError("Current Theory matrix manifest changed")
    manifest = load_json(MANIFEST)
    entry = select_theory_entry(manifest, args.run_id)
    rotation = matrix._resolve_inside_root(str(entry["rotation_file"]))
    if args.run_id == RUN_ID and rotation.resolve() != ROTATION.resolve():
        raise ValueError("Saved run resolved to a different rotation")
    if not rotation.is_file():
        raise FileNotFoundError("Saved run rotation is missing")
    db_path = matrix._resolve_inside_root(str(manifest.get("db_path") or "data/artifacts.db"))
    if not db_path.is_file():
        raise FileNotFoundError("Saved manifest database is missing")

    engine = load_active_gcsim_optimizer_engine_context(store_dir=DEFAULT_GCSIM_ENGINE_STORE_DIR)
    engine_root = inside(Path(engine.engine_root), root)
    engine_binary = inside(Path(engine.artifact_path), root)
    optimizer_binary = inside(Path(DEFAULT_OPTIMIZER_BINARY), root)
    engine_store = inside(Path(DEFAULT_GCSIM_ENGINE_STORE_DIR), root)
    if not engine_binary.is_file() or not optimizer_binary.is_file() or not engine_root.is_relative_to(engine_store):
        raise RuntimeError("Active engine or optimizer binary is not worker-local and ready")

    run_root = job / "runs"
    request = matrix._request(entry, db_path=db_path, run_root=run_root)
    if request.product_timeout_ms != LIMIT_MS or not request.infinite_energy_enabled:
        raise RuntimeError("Unexpected Theory budget or energy policy")
    if inside(Path(request.engine_store_dir), root) != engine_store:
        raise RuntimeError("Theory request does not use the worker active engine store")
    if inside(Path(request.optimizer_binary_path), root) != optimizer_binary:
        raise RuntimeError("Theory request does not use the worker optimizer binary")
    if inside(Path(request.run_root), root) != run_root.resolve():
        raise RuntimeError("Theory request run root escaped managed scratch")
    source_hashes = {path: sha256(root / path) for path in SOURCE_FILES}

    _, session_type = matrix.SESSION_TYPES["theory"]
    stage = ""

    def progress(row: dict[str, Any]) -> None:
        nonlocal stage
        current = str(row.get("stage") or "")
        if current != stage or current in {"completed", "failed"}:
            stage = current
            print(f"[theory] {current} {row.get('completed_work')}/{row.get('total_work')}", flush=True)

    started = time.monotonic()
    payload = session_type(request, progress_callback=progress).run()
    wall_ms = int((time.monotonic() - started) * 1000)
    run_dir = inside(Path(str(payload.get("run_dir") or "")), job)
    request_doc = load_json(run_dir / "request.json") if (run_dir / "request.json").is_file() else {}
    request_engine = request_doc.get("engine") if isinstance(request_doc.get("engine"), Mapping) else {}
    if request_engine.get("binary_path"):
        inside(Path(str(request_engine["binary_path"])), root)
    result = payload.get("result") if isinstance(payload.get("result"), Mapping) else {}
    provider_time_rows = {"product_result": provider_timings(result)}
    for path, document in output_documents(run_dir):
        timings = provider_timings(document)
        if timings:
            provider_time_rows[path] = timings

    receipt = {
        "schema_version": 1,
        "date": date.today().isoformat(),
        "owner_path": (
            "docs/optimizer-evidence/2026-10-03-theory-audit/README.md"
            if args.run_id == RUN_ID else CURRENT_MATRIX_OWNER
        ),
        "receipt_path": receipt_path.relative_to(root).as_posix(),
        "acceptance_scope": "programmatic backend/session evidence only; no physical UI acceptance",
        "git": {"branch": branch, "head": head},
        "input": input_binding(entry, rotation),
        "binding": {
            "engine_id": engine.engine_id,
            "engine_root": engine_root.relative_to(root).as_posix(),
            "engine_binary": engine_binary.relative_to(root).as_posix(),
            "engine_artifact_sha256": engine.artifact_sha256,
            "engine_tree_sha256": engine.engine_tree_sha256,
            "engine_binding_sha256": engine.binding_sha256,
            "engine_trusted": engine.trusted,
            "engine_capabilities": list(engine.capabilities),
            "optimizer_binary": optimizer_binary.relative_to(root).as_posix(),
            "optimizer_binary_sha256": sha256(optimizer_binary),
            "request_engine": {
                key: safe(request_engine[key])
                for key in ("engine_id", "artifact_sha256", "patch_manifest_sha256", "source_manifest_sha256")
                if key in request_engine
            },
        },
        "execution": {
            "success": bool(payload.get("success")),
            "status": payload.get("status"),
            "error_code": payload.get("error_code"),
            "error": payload.get("error"),
            "wall_ms": wall_ms,
            "budget_ms": request.product_timeout_ms,
            "go_deadline_ms": 300_000,
            "adapter_timings": safe(payload.get("adapter_timings", {})),
            "adapter_warnings": safe(payload.get("adapter_warnings", [])),
        },
        "source_sha256": source_hashes,
        "product": {
            "status": result.get("status"),
            "schema_kind": result.get("schema_kind"),
            "warnings": safe(result.get("warnings", [])),
            "coverage": safe(result.get("coverage", {})),
            "energy": safe(result.get("energy")),
            "candidates": candidates(result),
            "proposal_report": proposal_report(result, run_dir),
            "provider_timings": provider_time_rows,
        },
        "compact_capture_summary": scoped_capture_summary(run_dir, args.run_id),
        "cleanup": {
            "managed_job_relative": job.relative_to(root).as_posix(),
            "verified_by_harness": False,
            "outer_runner_cleanup_expected": True,
            "removed_bytes": None,
        },
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"Receipt saved: {receipt_path.relative_to(root)}; success={payload.get('success')}; candidates={len(receipt['product']['candidates'])}", flush=True)
    return 0 if payload.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
