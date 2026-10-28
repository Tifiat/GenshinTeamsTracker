"""Two n1 winner response controls, not ordinary-DPS or UI acceptance.

Reuses the bounded joint-capture receipt and candidate source binding. No install.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

here = Path(__file__).resolve().parent
root = here.parents[3]
p = argparse.ArgumentParser(__doc__)
for name in ("guide", "capture", "output"):
    p.add_argument("--" + name, type=Path, required=True)
a = p.parse_args()
output = a.output.resolve()
output.relative_to(root / ".codex_tmp")
output.mkdir(exist_ok=False)
overlay = output / "overlay.json"
overlay.write_text(json.dumps({"Replace": {str(root / "native/gcsim_optimizer/internal/allsets/transfer_winner_test.go"): str(here / "transfer_winner_test.go")}}), encoding="utf-8")
subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(overlay), "./internal/allsets", "-run", "TestJointWinnerResponse", "-count=1", "-timeout", "120s", "-v"],
               cwd=root / "native/gcsim_optimizer", check=True, timeout=130,
               env=dict(os.environ, GTT_TRANSFER_ROOT=str(root), GTT_TRANSFER_GUIDE=str(a.guide.resolve()), GTT_TRANSFER_CAPTURE=str(a.capture.resolve()), GTT_TRANSFER_OUTPUT=str(output)))
