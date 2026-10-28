"""Bounded All Sets capture/domain/FGBS integration, using frozen inventory only.

Research overlay, not the product queue or an installed CLI. Two named fixture
proposals, four fresh context members, four candidate-response members. No DB,
settings, installed binary or energy-mode mutation. See the Go design All Sets
plan; the measured result informs the still-unfrozen proposal scheduler.
"""
from pathlib import Path
import argparse
import json
import os
import subprocess


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    root = here.parents[3]
    output = args.output.resolve()
    output.relative_to(root / ".codex_tmp")
    output.mkdir(exist_ok=False)
    overlay = output / "overlay.json"
    overlay.write_text(json.dumps({"Replace": {
        str(root / "native/gcsim_optimizer/internal/setcontext/gtt_capture_pilot_test.go"):
        str(here / "capture_pilot_test.go"),
    }}), encoding="utf-8")
    env = dict(os.environ, GTT_ALLSETS_SOURCE=str(args.source_run.resolve()),
               GTT_ALLSETS_MATRIX=str(args.matrix.resolve()), GTT_ALLSETS_OUTPUT=str(output),
               GTT_ALLSETS_REPO=str(root))
    subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(overlay),
                    "./internal/setcontext", "-run", "TestAllSetsCapturePilot", "-count=1", "-v", "-timeout", "240s"],
                   cwd=root / "native/gcsim_optimizer", env=env, check=True, timeout=255)


if __name__ == "__main__":
    main()
