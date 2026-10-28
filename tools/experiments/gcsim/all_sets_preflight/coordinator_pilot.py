"""Four-context coordinator pilot; reuse three saved panels, at most six new n1.

No installed files, ordinary runs or live account state are changed. The fixed
pilot bounds are evidence, not product defaults or exhaustive All Sets coverage.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

here = Path(__file__).resolve().parent
root = here.parents[3]
p = argparse.ArgumentParser(__doc__)
for name in ("guide", "transport", "capture", "output"):
    p.add_argument("--" + name, type=Path, required=True)
a = p.parse_args()
output = a.output.resolve()
output.relative_to(root / ".codex_tmp")
output.mkdir(exist_ok=False)
overlay = output / "overlay.json"
overlay.write_text(json.dumps({"Replace": {str(root / "native/gcsim_optimizer/internal/allsets/coordinator_pilot_test.go"): str(here / "coordinator_pilot_test.go")}}), encoding="utf-8")
env = dict(os.environ, GTT_COORD_ROOT=str(root))
for name in ("guide", "transport", "capture", "output"):
    env["GTT_COORD_" + name.upper()] = str(getattr(a, name).resolve())
subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(overlay), "./internal/allsets", "-run", "TestBoundedCoordinatorPilot", "-count=1", "-timeout", "350s", "-v"],
               cwd=root / "native/gcsim_optimizer", check=True, timeout=360, env=env)
