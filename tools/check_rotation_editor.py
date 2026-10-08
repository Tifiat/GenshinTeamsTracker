"""Compare editor generation to the selected GCSIM parser, without simulation.

Explicit --engine-root is required. Only public test inputs are used. Go's
ordinary build cache is used; module/network updates are disabled. The helper
does not load a GTT engine executable, evaluator, settings or account database.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from run_workspace.gcsim.rotation_editor import parse, write
from tests.run_workspace.gcsim.test_rotation_editor import DIALECT, PUBLIC_CASES


def main() -> int:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--engine-root", type=Path, required=True)
    selected = args.parse_args().engine_root.resolve()
    if not (selected / "go.mod").is_file() or not (selected / "pkg/gcs/parser/parse.go").is_file():
        args.error("--engine-root must be an explicit public GCSIM source module")
    go = shutil.which("go")
    if not go:
        args.error("Go is required only for this development parser comparison")
    sources = list(PUBLIC_CASES)
    sources.append((ROOT / "run_workspace/gcsim/smoke_fixtures/rotation_chasca_ororon_furina_bennett.txt").read_text(encoding="utf-8"))
    pairs = [(source, write(parse(source, DIALECT), preserve=False)) for source in sources]
    payload = "".join(json.dumps({"source": text}) + "\n" for pair in pairs for text in pair)
    environment = dict(os.environ, GOPROXY="off", GOSUMDB="off", GOTOOLCHAIN="local", GOFLAGS="-mod=readonly", GOWORK="off")
    result = subprocess.run([go, "run", str(ROOT / "tools/gcsim_rotation_parse_oracle.go")], cwd=selected,
                            env=environment, input=payload, capture_output=True, text=True,
                            encoding="utf-8", timeout=120)
    if result.returncode:
        print(result.stderr, file=sys.stderr)
        return 1
    outputs = [json.loads(line) for line in result.stdout.splitlines()]
    if len(outputs) != len(pairs) * 2:
        print("FAIL: parser returned an unexpected number of records", file=sys.stderr)
        return 1
    failures = []
    for index, pair in enumerate(pairs):
        original, generated = outputs[2 * index:2 * index + 2]
        if original.get("error") or generated.get("error"):
            failures.append({"case": index + 1, "source_error": original.get("error"), "generated_error": generated.get("error"), "source": pair[0], "generated": pair[1]})
        elif original.get("tree") != generated.get("tree") or original.get("config") != generated.get("config"):
            failures.append({"case": index + 1, "different_tree": original.get("tree") != generated.get("tree"), "different_config": original.get("config") != generated.get("config"), "source": pair[0], "generated": pair[1]})
    if failures:
        print(json.dumps(failures, ensure_ascii=False, indent=2))
        return 1
    print(f"PASS: {len(pairs)} public code pairs have identical upstream parsed trees and configuration.")
    print("Parser-only comparison: per-character runtime registration, execution and UI are not exercised.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
