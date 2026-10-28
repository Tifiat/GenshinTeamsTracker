"""Eight opt-in compact calls for first four automatic package proposals."""
from pathlib import Path
import argparse
import json
import os
import subprocess

p = argparse.ArgumentParser(__doc__)
p.add_argument("--verify-winner", action="store_true", help="Two fresh compact controls for the previous four-proposal winner")
for key in ("source", "catalog", "receipt", "output"):
    p.add_argument("--"+key, type=Path, required=True)
a = p.parse_args()
here = Path(__file__).resolve().parent
root = here.parents[3]
output = a.output.resolve()
output.relative_to(root / ".codex_tmp")
output.mkdir(exist_ok=False)
overlay = output / "overlay.json"
overlay.write_text(json.dumps({"Replace": {
    str(root / "native/gcsim_optimizer/internal/allsets/queue_capture_test.go"):
    str(here / ("queue_winner_test.go" if a.verify_winner else "queue_capture_test.go"))}}), encoding="utf-8")
subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(overlay),
                "./internal/allsets", "-run", "TestAutomaticQueueWinnerResponse" if a.verify_winner else "TestFourAutomaticPackageCaptures", "-count=1", "-v", "-timeout", "180s"],
               cwd=root / "native/gcsim_optimizer", check=True, timeout=190,
               env=dict(os.environ, **{"GTT_QUEUE_"+key.upper(): str(getattr(a,key).resolve()) for key in ("source","catalog","receipt","output")}))
