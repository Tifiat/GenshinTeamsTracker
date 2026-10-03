"""Source-rule gate on the production-selected engine; zero simulations.

Temporary source envelope/build caches belong to the managed experiment job.
Remove this research entrypoint after equivalent installed producer validation;
its owner is the parametric section of the Go optimizer design.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))


def main() -> None:
    raw_job = os.environ.get("GTT_SCRATCH_DIR")
    if not raw_job:
        raise RuntimeError("Run inside managed_optimizer_experiment.py")
    job = Path(raw_job).resolve(strict=True)
    if job.parent != (ROOT / ".codex_tmp/managed-optimizer").resolve(strict=True) or not job.name.startswith("job-"):
        raise ValueError("Not an owned managed optimizer job")
    run_gate(job)


def run_gate(job: Path, *, extra_environment: dict[str, str] | None = None) -> None:
    raw_job = os.environ.get("GTT_SCRATCH_DIR")
    if not raw_job:
        raise RuntimeError("Run inside managed_optimizer_experiment.py")
    job = job.resolve(strict=True)
    if job != Path(raw_job).resolve(strict=True) or job.parent != (ROOT / ".codex_tmp/managed-optimizer").resolve(strict=True) or not job.name.startswith("job-"):
        raise ValueError("Not an owned managed optimizer job")
    from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
    from run_workspace.gcsim.optimizer_go_all_sources import prepare_all_set_effect_sources
    from run_workspace.gcsim.source_manifest_build import canonical_json

    engine = load_active_gcsim_optimizer_engine_context()
    root = Path(engine.engine_root)
    manifest = json.loads((root / "build/gtt-source-manifest-body.json").read_bytes())
    binding = {"binary_path": engine.artifact_path, "artifact_sha256": engine.artifact_sha256,
               "source_manifest_sha256": hashlib.sha256(canonical_json(manifest).encode()).hexdigest(),
               "capabilities": engine.capabilities}
    envelope = prepare_all_set_effect_sources(root, binding, include_neutral_rules=True)
    target = job / "rule-sources.json"
    target.write_text(json.dumps(envelope), encoding="utf-8")
    environment = dict(os.environ, GTT_RULE_SOURCE_BUNDLE=str(target), **(extra_environment or {}))
    go = shutil.which("go")
    if not go:
        raise RuntimeError("Configured Go toolchain is unavailable")
    test_timeout = 180 if environment.get("GTT_NEUTRAL_INVENTORY_REQUEST") else 90
    if environment.get("GTT_NEUTRAL_FINISH_PASSES") == "1":
        test_timeout = 600  # Emergency watchdog, not a candidate-search deadline.
    subprocess.run([go, "test", "./internal/seteffects", "./internal/engineclient", "./internal/setcontext", "./internal/allsets", "./internal/search", "./internal/formula", "./internal/domain", "-run", "Test(Rule|Neutral|Candidates|Parametric|PackageLinearPlan)", "-v", "-count=1", f"-timeout={test_timeout}s"],
                   cwd=ROOT / "native/gcsim_optimizer", env=environment, check=True, timeout=test_timeout + 20)
    if hashlib.sha256(Path(engine.artifact_path).read_bytes()).hexdigest() != engine.artifact_sha256:
        raise RuntimeError("Selected engine changed during source gate")
    print(f"Source rules bound to {engine.engine_id}; zero captures/ordinary simulations.", flush=True)


if __name__ == "__main__":
    main()
