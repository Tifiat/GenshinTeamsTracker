"""Run one saved Theory request in managed scratch and export a small receipt."""
from __future__ import annotations

import argparse
import copy
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from tools.managed_optimizer_experiment import managed_scratch
from run_workspace.gcsim.engine_store import load_engine_manifest
from run_workspace.gcsim.optimizer_engine_context import (
    load_active_gcsim_optimizer_engine_context,
)
from run_workspace.gcsim.optimizer_go_all_sources import (
    prepare_all_set_effect_sources,
)
from run_workspace.gcsim.optimizer_go_contracts import canonical_sha256
from run_workspace.gcsim.source_manifest_build import canonical_json


def main() -> int:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=370.0)
    parser.add_argument(
        "--refresh-active-engine",
        action="store_true",
        help="Rebind the saved input to the current verified engine before replay.",
    )
    args = parser.parse_args()
    source = args.source_run.resolve()
    request = source / "request.json"
    sources = source / "set-sources.json"
    if not request.is_file() or not sources.is_file():
        raise SystemExit("saved request or set source bundle is missing")
    receipt = args.receipt.resolve()
    receipt.relative_to(ROOT)
    binary = ROOT / "native" / "gcsim_optimizer" / "gtt-optimizer.exe"
    if not binary.is_file():
        raise SystemExit("optimizer binary is missing")

    with managed_scratch() as scratch:
        run_root = scratch / "theory-run"
        temporary = scratch / "temp"
        temporary.mkdir()
        active_engine_id = "saved_request_engine"
        if args.refresh_active_engine:
            request, sources, active_engine_id = _refresh_active_engine_inputs(
                request,
                scratch,
            )
        started = time.monotonic()
        completed = subprocess.run(
            [str(binary), "optimize-theory", str(request), str(sources), str(run_root)],
            cwd=ROOT,
            env=dict(os.environ, TMP=str(temporary), TEMP=str(temporary)),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=args.timeout,
            check=False,
        )
        wall_seconds = time.monotonic() - started
        if completed.returncode != 0:
            raise RuntimeError(
                "Theory smoke failed: " + "\n".join(completed.stderr.splitlines()[-12:])
            )
        wrapper = json.loads(completed.stdout)
        product = wrapper["product_result"]
        candidates = product.get("candidates") or []
        compact_candidates = []
        for candidate in candidates[:5]:
            compact_candidates.append(
                {
                    "rank": candidate.get("rank"),
                    "formula_dps": candidate.get("formula_dps"),
                    "source": candidate.get("source"),
                    "packages": candidate.get("packages"),
                    "allocations": candidate.get("allocations"),
                    "opaque_reasons": candidate.get("opaque_reasons"),
                }
            )
        summary = {
            "schema_version": 1,
            "date": date.today().isoformat(),
            "status": "measurement_only_unreviewed",
            "scope": "saved_request_theory_backend_smoke",
            "source_run": source.name,
            "engine_id": active_engine_id,
            "wall_seconds": wall_seconds,
            "native_elapsed_ms": wrapper.get("total_elapsed_ms"),
            "coverage": product.get("coverage"),
            "warnings": product.get("warnings"),
            "candidates": compact_candidates,
            "progress_tail": completed.stderr.splitlines()[-8:],
            "generated_state_removed_on_exit": True,
        }
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(
            json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


def _refresh_active_engine_inputs(
    source_request: Path,
    scratch: Path,
) -> tuple[Path, Path, str]:
    request = copy.deepcopy(json.loads(source_request.read_text(encoding="utf-8")))
    context = load_active_gcsim_optimizer_engine_context()
    engine_root = Path(context.engine_root)
    manifest = load_engine_manifest(engine_root)
    source_manifest = json.loads(
        (engine_root / "build" / "gtt-source-manifest-body.json").read_text(
            encoding="utf-8"
        )
    )
    source_manifest_sha256 = hashlib.sha256(
        canonical_json(source_manifest).encode("utf-8")
    ).hexdigest()
    patch_manifest_sha256 = str(
        manifest.patch_metadata.get("patch_stack_sha256", "") or ""
    ).casefold()
    binding_sha256 = canonical_sha256(
        {
            "kind": "gtt.standalone_engine_binding.v1",
            "artifact_sha256": context.artifact_sha256,
            "source_manifest_sha256": source_manifest_sha256,
            "patch_manifest_sha256": patch_manifest_sha256,
        }
    )
    request["engine"] = {
        "binary_path": str(Path(context.artifact_path).resolve()).replace("\\", "/"),
        "artifact_sha256": context.artifact_sha256,
        "binding_sha256": binding_sha256,
        "source_manifest_sha256": source_manifest_sha256,
        "patch_manifest_sha256": patch_manifest_sha256,
        "capabilities": sorted(context.capabilities),
    }
    anchor = canonical_sha256(
        {
            "kind": "gtt.optimizer.theory_neutral_anchor.v2",
            "wearers": request["wearers"],
        }
    )
    prepared = request["context"]["prepared_config"]
    rotation = request["context"]["rotation"]
    target = request["context"]["target"]
    ignore_energy = bool(
        re.search(
            r"\bignore_burst_energy\s*=\s*true\b",
            str(prepared["text"]),
            re.IGNORECASE,
        )
    )
    request["context"]["trace_context_sha256"] = canonical_sha256(
        {
            "kind": "gtt.optimizer.selected.trace_context.v1",
            "engine_binding_sha256": binding_sha256,
            "artifact_database_input_sha256": anchor,
            "equipment_rows_sha256": anchor,
            "snapshot_sha256": anchor,
            "prepared_config_sha256": prepared["sha256"],
            "rotation_sha256": rotation["sha256"],
            "target_sha256": target["sha256"],
            "seeds": list(request["stochastic"]["seeds"]),
            "ignore_burst_energy": ignore_energy,
        }
    )
    refreshed_request = scratch / "request.json"
    refreshed_request.write_text(
        json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    sources = prepare_all_set_effect_sources(engine_root, request["engine"])
    refreshed_sources = scratch / "set-sources.json"
    refreshed_sources.write_text(
        json.dumps(sources, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    return refreshed_request, refreshed_sources, context.engine_id


if __name__ == "__main__":
    raise SystemExit(main())
