"""Source-derived resistance replay on saved captures; zero simulations."""
from pathlib import Path
import argparse
import json
import os
import subprocess

p = argparse.ArgumentParser(__doc__)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--curves", type=Path, required=True)
p.add_argument("--previous", type=Path, required=True)
a = p.parse_args()
here = Path(__file__).resolve().parent
root = here.parents[3]
output = a.output.resolve()
output.relative_to(root / ".codex_tmp")
overlay = output / "native-resistance-overlay.json"
overlay.write_text(json.dumps({"Replace": {
    str(root / "native/gcsim_optimizer/internal/seteffects/resistance_replay_test.go"):
    str(here / "resistance_replay_test.go")}}), encoding="utf-8")
subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(overlay),
                "./internal/seteffects", "-run", "TestSourceResistanceCapturedResponses", "-count=1", "-v"],
               cwd=root / "native/gcsim_optimizer", check=True, timeout=60,
               env=dict(os.environ, GTT_RESISTANCE_OUTPUT=str(output), GTT_CONTEXT_CURVES=str(a.curves.resolve()), GTT_PREVIOUS_INPUTS=str(a.previous.resolve())))
