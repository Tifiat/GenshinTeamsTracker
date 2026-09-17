"""Cold product-CLI gate on the preserved copied-account request.

At most eight two-seed contexts, seven n128, seven n500 and four n1000.
No install/live DB writes. The Go CLI owns the420s search/600s overall limits.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(root))
from run_workspace.gcsim.optimizer_go_contracts import canonical_json_bytes, canonical_sha256

p = argparse.ArgumentParser(__doc__)
for name in ("guide", "output"):
    p.add_argument("--" + name, type=Path, required=True)
a = p.parse_args()
out = a.output.resolve()
out.relative_to(root / ".codex_tmp")
out.mkdir(exist_ok=False)
req = json.loads((root / ".codex_tmp/selected-2plus2-20260916/run/request.json").read_bytes())
req["engine"] = json.loads((a.guide / "engine.json").read_bytes())
req["engine"]["capabilities"] = sorted(req["engine"]["capabilities"])
req["budgets"] = {"product_timeout_ms": 600_000, "development_timeout_ms": 600_000}
req["context"]["trace_context_sha256"] = canonical_sha256({"kind": "all_sets_cli_gate", "engine": req["engine"], "context": req["context"]["context_sha256"]})
(out / "request.json").write_bytes(canonical_json_bytes(req))
binary = out / "gtt-optimizer.exe"
subprocess.run(["C:/Program Files/Go/bin/go.exe", "build", "-o", str(binary), "./cmd/gtt-optimizer"], cwd=root / "native/gcsim_optimizer", check=True)
started = time.monotonic()
with (out / "output.json").open("wb") as stdout, (out / "progress.jsonl").open("wb") as stderr:
    result = subprocess.run([str(binary), "optimize-all-sets", str(out / "request.json"), str(a.guide.resolve() / "sources.json"), str(out / "verification")], stdout=stdout, stderr=stderr, timeout=615)
summary = {"exit_code": result.returncode, "wall_seconds": time.monotonic() - started}
if result.returncode == 0:
    data = json.loads((out / "output.json").read_bytes())
    summary.update(measured_dps=data["product_result"]["measured"]["dps"], formula_dps=data["product_result"]["formula_dps"], capture_members=data["capture_members"], stop_reason=data["search_stop_reason"])
(out / "cli-receipt.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary))
if result.returncode:
    print((out / "progress.jsonl").read_text(encoding="utf-8")[-4000:])
    raise SystemExit(result.returncode)
