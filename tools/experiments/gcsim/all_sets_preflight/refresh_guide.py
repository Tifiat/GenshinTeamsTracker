"""Exercise bound source preparation and guide refresh on retained real capture.

No simulation. Only isolated output and pure native formula/item calculations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

here = Path(__file__).resolve().parent
root = here.parents[3]
sys.path.insert(0, str(root))
from run_workspace.gcsim.optimizer_go_all_sources import prepare_all_set_effect_sources  # noqa: E402

parser = argparse.ArgumentParser(__doc__)
parser.add_argument("--candidate", type=Path, required=True)
parser.add_argument("--capture", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
source = args.candidate.resolve() / "source"
output = args.output.resolve()
output.relative_to(root / ".codex_tmp")
output.mkdir(exist_ok=False)
build = json.loads((source.parent / "build-summary.json").read_text())
binding = {"binary_path": str(source / "build/gtt-gcsim.exe"), "artifact_sha256": build["artifact_sha256"],
           "source_manifest_sha256": build["source_manifest_body_sha256"], "capabilities": build["gtt_capabilities"],
           "patch_manifest_sha256": hashlib.sha256((source.parent / "patch_stack/0001-gtt-engine-adapter-v245.patch").read_bytes()).hexdigest()}
binding["binding_sha256"] = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
started = time.perf_counter()
envelope = prepare_all_set_effect_sources(source, binding)
prep_seconds = time.perf_counter() - started
(output / "sources.json").write_text(json.dumps(envelope), encoding="utf-8")
(output / "engine.json").write_text(json.dumps(binding), encoding="utf-8")
overlay = output / "overlay.json"
overlay.write_text(json.dumps({"Replace":{str(root / "native/gcsim_optimizer/internal/allsets/refresh_guide_test.go"):str(here / "refresh_guide_test.go")}}), encoding="utf-8")
subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(overlay), "./internal/allsets", "-run", "TestBoundGuideRefresh", "-count=1", "-v", "-timeout", "120s"],
               cwd=root / "native/gcsim_optimizer", check=True, timeout=130,
               env=dict(os.environ,GTT_REFRESH_ROOT=str(root),GTT_REFRESH_CAPTURE=str(args.capture.resolve()),GTT_REFRESH_OUTPUT=str(output)))
receipt = output / "refresh-guide-receipt.json"
result = json.loads(receipt.read_text())
result["source_preparation_seconds"] = prep_seconds
receipt.write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result))
