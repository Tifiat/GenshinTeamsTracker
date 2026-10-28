"""Run bounded parity/coverage against an already-built isolated engine."""
from pathlib import Path
import argparse
import json
import os
import subprocess

p = argparse.ArgumentParser(__doc__)
p.add_argument("--engine", type=Path, required=True)
p.add_argument("--matrix", type=Path, required=True)
p.add_argument("--case", default="", help="Narrow diagnostic; writes separately named parity results")
p.add_argument("--support-source", type=Path, help="Reviewed support.go-only compiler probe, not a product installation")
args = p.parse_args()
engine = args.engine.resolve()
matrix = args.matrix.resolve()
overlay = json.loads((engine / "build/gtt-source-overlay.json").read_text())
staging = engine.parents[1] / "staging" / engine.name
def relocated(value):
    path = Path(value)
    try:
        return engine / path.relative_to(staging)
    except ValueError:
        return path
overlay["Replace"] = {str(relocated(k)): str(relocated(v)) for k, v in overlay["Replace"].items()}
assert overlay["Replace"] and all(Path(v).exists() for v in overlay["Replace"].values())
assert any(str(engine / "internal/characters/nahida/asc.go") == k for k in overlay["Replace"])
overlay["Replace"][str(engine / "pkg/optimization/gtt_dependency_audit_test.go")] = str(Path(__file__).with_name("engine_parity_test.go").resolve())
overlay["Replace"][str(engine / "pkg/gttcompact/dependency_audit_support_probe.go")] = str(Path(__file__).with_name("support_graph_probe.go").resolve())
if args.support_source:
    assert args.case and args.support_source.is_file()
    overlay["Replace"][str(engine / "pkg/gttcompact/support.go")] = str(args.support_source.resolve())
overlay_path = matrix / "parity-overlay.json"
overlay_path.write_text(json.dumps(overlay), encoding="utf-8")
env = dict(os.environ, GTT_AUDIT_MATRIX=str(matrix))
if args.case:
    env["GTT_AUDIT_CASE"] = args.case
subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(overlay_path), "./pkg/optimization", "-run", "TestDependencyAuditOrdinaryParity", "-count=1", "-v"], cwd=engine, env=env, check=True)
