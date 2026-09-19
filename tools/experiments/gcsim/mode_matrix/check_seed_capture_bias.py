"""Temporary same-seed control for the Gaming formula/ordinary discrepancy.

Run only while the managed product-matrix job still owns its disposable run
directory. This does not copy account configs into permanent fixtures; the
extra engine output lives in a TemporaryDirectory and is removed on exit.
The control compares a finalized artifact config on the *same two trace seeds*
against the selected formula, separating seed-panel bias from a lost stat
dependency. Replace this narrow probe with a product-level diagnostic only if
the control shows a reproducible non-seed residual.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    run = args.run.resolve(strict=True)
    config = args.config.resolve(strict=True)
    config.relative_to(run)
    request = json.loads((run / "request.json").read_text(encoding="utf-8"))
    binary = Path(request["engine"]["binary_path"]).resolve(strict=True)
    actual = hashlib.sha256(binary.read_bytes()).hexdigest()
    if actual != request["engine"]["artifact_sha256"]:
        raise ValueError("bound engine artifact changed")
    config_text = config.read_text(encoding="utf-8")
    digest = hashlib.sha256(config_text.encode("utf-8")).hexdigest()
    seeds = tuple(request["stochastic"]["seeds"])
    if len(seeds) != 2:
        raise ValueError("expected the fixed two-seed formula panel")

    with tempfile.TemporaryDirectory(prefix="gaming-seed-control-", dir=run) as temp:
        root = Path(temp)
        for seed in seeds:
            job = root / str(seed)
            job.mkdir()
            conf = job / "config.txt"
            conf.write_text(config_text, encoding="utf-8")
            trace_request = job / "request.json"
            trace_request.write_text(json.dumps({
                "schema_version": 1,
                "output_mode": "compact_ir_v1",
                "context_sha256": digest,
                "seed": str(seed),
                "iterations": 1,
                "workers": 1,
                "ignore_burst_energy": True,
            }), encoding="utf-8")
            output = job / "member.json"
            environment = dict(os.environ, GOMAXPROCS="1")
            subprocess.run(
                [str(binary), "-c", str(conf), "-out", str(output),
                 "-gtt-trace-equation", str(trace_request)],
                cwd=job, env=environment, check=True, capture_output=True,
                timeout=120,
            )
            member = json.loads(output.read_text(encoding="utf-8"))
            channels = member["channels"]
            gaming = [row for row in channels if row["actor_key"] == "gaming"]
            plunges = [row for row in gaming if row["attack_tag"] == "tag/3"]
            melted = [row for row in plunges if "gaming.em" in row["response_coordinates"]]
            print(json.dumps({
                "seed": seed,
                "fixed_build_capture_dps": sum(float(row["baseline_damage"]) for row in channels)
                * 1000 / member["duration_ms"],
                "gaming_plunge_hits": len(plunges),
                "gaming_melt_plunge_hits": len(melted),
                "gaming_plunge_damage": sum(float(row["baseline_damage"]) for row in plunges),
            }, sort_keys=True), flush=True)
    if hashlib.sha256(binary.read_bytes()).hexdigest() != actual:
        raise ValueError("bound engine artifact changed during control")


if __name__ == "__main__":
    main()
