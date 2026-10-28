"""Join source recipes/neutral inputs on retained captures, no simulations."""
from pathlib import Path
import argparse
import json
import os
import subprocess

p = argparse.ArgumentParser(__doc__)
p.add_argument("--catalog", type=Path, required=True)
p.add_argument("--captures", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
here = Path(__file__).resolve().parent
root = here.parents[3]
output = a.output.resolve()
output.relative_to(root / ".codex_tmp")
output.mkdir(exist_ok=False)
overlay = output / "overlay.json"
overlay.write_text(json.dumps({"Replace": {
    str(root / "native/gcsim_optimizer/internal/seteffects/guide_probe_test.go"):
    str(here / "guide_probe_test.go")}}), encoding="utf-8")
subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(overlay),
                "./internal/seteffects", "-run", "TestJoinedGuideFeatures", "-count=1", "-v"],
               cwd=root / "native/gcsim_optimizer", check=True, timeout=90,
               env=dict(os.environ, GTT_GUIDE_OUTPUT=str(output), GTT_GUIDE_CATALOG=str(a.catalog.resolve()), GTT_GUIDE_CAPTURES=str(a.captures.resolve())))
