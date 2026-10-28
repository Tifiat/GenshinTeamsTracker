"""Replay existing four neutral-input captures through the native formula code."""
from pathlib import Path
import argparse
import json
import os
import subprocess

p = argparse.ArgumentParser(__doc__)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
here = Path(__file__).resolve().parent
root = here.parents[3]
output = a.output.resolve()
output.relative_to(root / ".codex_tmp")
overlay = output / "native-replay-overlay.json"
overlay.write_text(json.dumps({"Replace": {
    str(root / "native/gcsim_optimizer/internal/formula/effect_input_replay_test.go"):
    str(here / "effect_input_replay_test.go")}}), encoding="utf-8")
subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(overlay),
                "./internal/formula", "-run", "TestEffectInputCapturedResponses", "-count=1", "-v"],
               cwd=root / "native/gcsim_optimizer", env=dict(os.environ, GTT_EFFECT_INPUT_OUTPUT=str(output)),
               check=True, timeout=60)
