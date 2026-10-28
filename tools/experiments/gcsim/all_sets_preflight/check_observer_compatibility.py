"""Check consolidated patch and standard bundle gate; exactly three tiny n1 runs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from run_workspace.gcsim.engine_compatibility import verify_engine_application_bundle  # noqa: E402

parser = argparse.ArgumentParser(__doc__)
parser.add_argument("--candidate", type=Path, required=True)
args = parser.parse_args()
candidate = args.candidate.resolve()
candidate.relative_to(ROOT / ".codex_tmp")
receipt = candidate / "compatibility-receipt.json"
if receipt.exists():
    raise SystemExit("existing compatibility receipt; refusing repeated simulations")
patch = candidate / "patch_stack/0001-gtt-engine-adapter-v245.patch"
prefix = (candidate / "upstream/expanded/v2.45.0").relative_to(ROOT).as_posix()
subprocess.run(["git", "apply", "--check", "--directory", prefix, str(patch)], cwd=ROOT, check=True)
build = SimpleNamespace(**json.loads((candidate / "build-summary.json").read_text()))
error = verify_engine_application_bundle(candidate / "source", build)
row = {"status":"passed" if not error else "failed", "error":error,
       "new_n1_calls":3, "checks":["patch_applies_to_pristine", "catalog", "ordinary_compact_parity", "installed_consumer_validation", "sequential_waves", "binaries_unchanged"],
       "installed":False,"binary_sha256":build.artifact_sha256,"source_manifest_sha256":build.source_manifest_body_sha256}
receipt.write_text(json.dumps(row, indent=2), encoding="utf-8")
print(json.dumps(row))
if error:
    raise SystemExit(1)
