"""Measure the isolated source+raw-stat package proposal queue, zero simulations."""
from pathlib import Path
import argparse
import json
import os
import subprocess

p = argparse.ArgumentParser(__doc__)
for key in ("source", "catalog", "guide", "output"):
    p.add_argument("--"+key, type=Path, required=True)
a = p.parse_args()
here = Path(__file__).resolve().parent
root = here.parents[3]
output = a.output.resolve()
output.relative_to(root / ".codex_tmp")
output.mkdir(exist_ok=False)
overlay = output / "overlay.json"
overlay.write_text(json.dumps({"Replace": {
    str(root / "native/gcsim_optimizer/internal/allsets/proposal_queue_test.go"):
    str(here / "proposal_queue_test.go")}}), encoding="utf-8")
subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(overlay),
                "./internal/allsets", "-run", "TestSavedAccountProposalQueue", "-count=1", "-v"],
               cwd=root / "native/gcsim_optimizer", check=True, timeout=90,
               env=dict(os.environ, **{"GTT_QUEUE_"+key.upper(): str(getattr(a,key).resolve()) for key in ("source","catalog","guide","output")}))
