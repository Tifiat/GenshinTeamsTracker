"""Two explicit n1 parity captures through clean candidate binary, no install."""
import argparse
import json
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(__doc__)
parser.add_argument("--candidate", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
here = Path(__file__).resolve().parent
root = here.parents[3]
candidate, output = args.candidate.resolve(), args.output.resolve()
candidate.relative_to(root / ".codex_tmp")
output.relative_to(root / ".codex_tmp")
output.mkdir(exist_ok=False)
overlay = output / "overlay.json"
overlay.write_text(json.dumps({"Replace":{str(root / "native/gcsim_optimizer/internal/engineclient/observer_transport_test.go"):str(here / "observer_transport_test.go")}}), encoding="utf-8")
subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(overlay), "./internal/engineclient",
                "-run", "TestObserverCandidateTransportParity", "-count=1", "-timeout", "180s", "-v"],
               cwd=root / "native/gcsim_optimizer", check=True, timeout=190,
               env=dict(os.environ,GTT_OBSERVER_ROOT=str(root),GTT_OBSERVER_SOURCE=str(candidate / "source"),GTT_OBSERVER_OUTPUT=str(output)))
