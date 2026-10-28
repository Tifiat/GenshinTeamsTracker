"""Replay retained captures through the Go All Sets context pilot; no GCSIM calls.

Overlay only, not a product CLI. See the Go design's effect/context contract.
The normal two-seed product policy and installed consumer remain unchanged.
"""
from pathlib import Path
import argparse
import json
import os
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    root = here.parents[3]
    output = args.output.resolve()
    output.relative_to(root / ".codex_tmp")
    output.mkdir(exist_ok=False)
    overlay = output / "context-overlay.json"
    overlay.write_text(json.dumps({"Replace": {
        str(root / "native/gcsim_optimizer/internal/setcontext/gtt_context_replay_test.go"):
        str(here / "context_replay_test.go"),
    }}), encoding="utf-8")
    env = dict(os.environ, GTT_SET_CONTEXT_MATRIX=str(args.matrix.resolve()),
               GTT_SET_CONTEXT_SOURCE=str(args.source_run.resolve()),
               GTT_SET_CONTEXT_OUTPUT=str(output))
    subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(overlay),
                    "./internal/setcontext", "-run", "TestAllSetsContextReplay", "-count=1", "-v"],
                   cwd=root / "native/gcsim_optimizer", env=env, check=True, timeout=90)


if __name__ == "__main__":
    main()
