"""Ordinary verification of seven already selected All Sets finalists.

Replays retained complete contexts, no new compact captures or artifact search.
Budget: seven n128 + seven n500 + at most four n1000, shared 180s deadline.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

here = Path(__file__).resolve().parent
root = here.parents[3]
p = argparse.ArgumentParser(__doc__)
for name in ("guide", "transport", "capture", "coordinator", "output"):
    p.add_argument("--" + name, type=Path, required=True)
a = p.parse_args()
output = a.output.resolve()
output.relative_to(root / ".codex_tmp")
output.mkdir(exist_ok=False)
overlay = output / "overlay.json"
overlay.write_text(json.dumps({"Replace": {str(root / "native/gcsim_optimizer/internal/allsets/coordinator_verify_test.go"): str(here / "coordinator_verify_test.go")}}), encoding="utf-8")
env = dict(os.environ, GTT_VERIFY_ROOT=str(root))
for name in ("guide", "transport", "capture", "coordinator", "output"):
    env["GTT_VERIFY_" + name.upper()] = str(getattr(a, name).resolve())
subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(overlay), "./internal/allsets", "-run", "TestCoordinatorOrdinaryFinalists", "-count=1", "-timeout", "240s", "-v"],
               cwd=root / "native/gcsim_optimizer", check=True, timeout=250, env=env)
