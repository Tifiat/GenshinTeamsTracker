"""Run one saved All Sets request in managed scratch and export a small receipt.

This is a bounded performance/quality comparison for the current coordinator,
not a product run or gameplay acceptance. Heavy contexts and Go build cache are
owned by ``managed_scratch`` and deleted on exit. The committed receipt replaces
the disposable run; tests pin only its small summary.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / "native" / "gcsim_optimizer"
sys.path.insert(0, str(ROOT))

from tools.managed_optimizer_experiment import managed_scratch


def _sha(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=610.0)
    args = parser.parse_args()

    source = args.source_run.resolve()
    request = source / "request.json"
    sources = source / "set-sources.json"
    if not request.is_file() or not sources.is_file():
        raise SystemExit("saved request or set source bundle is missing")
    receipt = args.receipt.resolve()
    receipt.relative_to(ROOT)

    with managed_scratch() as scratch:
        cache, temporary = scratch / "go-cache", scratch / "temp"
        cache.mkdir()
        temporary.mkdir()
        run_root = scratch / "all-sets-run"
        env = dict(
            os.environ,
            GOCACHE=str(cache),
            GOTMPDIR=str(temporary),
            TMP=str(temporary),
            TEMP=str(temporary),
        )
        command = [
            "go",
            "run",
            "./cmd/gtt-optimizer",
            "optimize-all-sets",
            str(request),
            str(sources),
            str(run_root),
        ]
        started = time.monotonic()
        completed = subprocess.run(
            command,
            cwd=MODULE,
            env=env,
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
            tail = "\n".join(completed.stderr.splitlines()[-12:])
            raise RuntimeError(f"All Sets benchmark failed ({completed.returncode}):\n{tail}")
        result = json.loads(completed.stdout)
        product = result["product_result"]
        measured = product.get("measured") or {}
        candidates = product.get("candidates") or []
        summary = {
            "schema_version": 1,
            "date": date.today().isoformat(),
            "status": "measurement_only_unreviewed",
            "scope": "saved_request_two_stage_all_sets_backend_benchmark",
            "source_run": source.name,
            "wall_seconds": wall_seconds,
            "native_elapsed_ms": result.get("total_elapsed_ms"),
            "search_seconds": result.get("search_seconds"),
            "search_stop_reason": result.get("search_stop_reason"),
            "search_expansions": result.get("search_expansions"),
            "pending": result.get("pending"),
            "queued": result.get("queued"),
            "guides": result.get("guides"),
            "capture_members": result.get("capture_members"),
            "search_config": result.get("search_config"),
            "search_work": result.get("search_work"),
            "screening_elapsed_ms": (result.get("screening") or {}).get("total_elapsed_ms"),
            "verification_elapsed_ms": (result.get("verification") or {}).get("total_elapsed_ms"),
            "measured_dps": measured.get("dps"),
            "standard_error": measured.get("standard_error"),
            "formula_dps": product.get("formula_dps"),
            "formula_residual": product.get("formula_residual"),
            "winner_assignment_sha256": _sha(product.get("winner") or []),
            "candidate_assignment_sha256": [
                _sha(row.get("artifacts") or []) for row in candidates
            ],
            "candidate_count": len(candidates),
            "warnings": product.get("warnings") or [],
            "generated_state_removed_on_exit": True,
            "progress_tail": completed.stderr.splitlines()[-8:],
        }
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(
            json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
