"""Measure one strict-read substep over saved evidence; zero engine calls."""
from pathlib import Path
import argparse
import json
import os
import subprocess


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--member", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    root = here.parents[3]
    output = args.output.resolve()
    output.relative_to(root / ".codex_tmp")
    output.mkdir(exist_ok=False)
    overlay = output / "overlay.json"
    overlay.write_text(json.dumps({"Replace": {
        str(root / "native/gcsim_optimizer/internal/contracts/gtt_decode_benchmark_test.go"):
        str(here / "decode_benchmark_test.go"),
    }}), encoding="utf-8")
    env = dict(os.environ, GTT_CANONICAL_INPUT=str(args.member.resolve()), GTT_CANONICAL_OUTPUT=str(output))
    subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(overlay),
                    "./internal/contracts", "-run", "TestAllSetsCanonicalReadBenchmark", "-count=1", "-v"],
                   cwd=root / "native/gcsim_optimizer", env=env, check=True, timeout=45)


if __name__ == "__main__":
    main()
