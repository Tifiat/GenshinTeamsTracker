"""Isolated observer overlay; no installed source/binary/config changes.

The three changed source copies are reviewed with apply_patch. This runner only
binds those copies plus added observer files to the existing generated overlay.
It runs narrow unit tests, not a rotation or product engine update.
"""
from pathlib import Path
import argparse
import json
import os
import subprocess
import shutil


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--engine-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--capture-controls", action="store_true", help="Exactly four new n1 simulations; opt-in")
    p.add_argument("--prepare", action="store_true", help="Prepare new isolated source copies using the retained experimental delta")
    a = p.parse_args()
    root = Path(__file__).resolve().parents[4]
    here = Path(__file__).resolve().parent
    engine, output = a.engine_root.resolve(), a.output.resolve()
    output.relative_to(root / ".codex_tmp")
    if a.prepare:
        output.mkdir(exist_ok=False)
        for name, relative in {
            "mods.go": "pkg/core/player/character/mods.go",
            "model.go": "pkg/gttcompact/model.go",
            "compile.go": "pkg/gttcompact/compile.go",
        }.items():
            shutil.copyfile(engine / relative, output / name)
        prefix = output.relative_to(root).as_posix() + "/"
        delta = here / "effect_inputs_experiment.patch"
        subprocess.run(["git", "apply", "--check", "--directory", prefix, str(delta)], cwd=root, check=True)
        subprocess.run(["git", "apply", "--directory", prefix, str(delta)], cwd=root, check=True)
    overlay = json.loads((engine / "build/gtt-source-overlay.json").read_text())
    staging = engine.parents[1] / "staging" / engine.name

    def relocate(value):
        path = Path(value)
        try:
            return str(engine / path.relative_to(staging))
        except ValueError:
            return str(path)

    overlay["Replace"] = {relocate(k): relocate(v) for k, v in overlay["Replace"].items()}
    replacements = {
        "pkg/core/player/character/mods.go": output / "mods.go",
        "pkg/gttcompact/model.go": output / "model.go",
        "pkg/gttcompact/compile.go": output / "compile.go",
        "pkg/gttcompact/effect_input.go": here / "effect_input.go",
        "pkg/gtttrace/effect_read.go": here / "effect_read.go",
        "pkg/gtttrace/effect_read_test.go": here / "effect_read_test.go",
        "pkg/optimization/effect_input_capture_test.go": here / "effect_input_capture_test.go",
    }
    for name, source in replacements.items():
        if not source.is_file():
            raise ValueError(f"reviewed overlay file missing: {source}")
        if str(engine / name) in overlay["Replace"]:
            raise ValueError(f"overlay collision: {name}")
        overlay["Replace"][str(engine / name)] = str(source)
    path = output / "overlay.json"
    path.write_text(json.dumps(overlay), encoding="utf-8")
    subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(path),
                    "./pkg/gtttrace", "./pkg/core/player/character", "./pkg/gttcompact",
                    "-run", "Test(EffectRead|ReactionBonus)", "-count=1", "-v"],
                   cwd=engine, check=True, timeout=60)
    if a.capture_controls:
        jobs = [
            dict(Case="bloom", Config=str(root / ".codex_tmp/selected-2plus2-20260916/run/prepared-config.txt"), Owner="kukishinobu"),
            dict(Case="cloud", Config=str(root / ".codex_tmp/gob11-gp3-production-20260916/flins_1/selected-20260916-132613-fd420284/prepared-config.txt"), Owner="ineffa"),
        ]
        for job in jobs:
            if not Path(job["Config"]).is_file():
                raise ValueError("approved saved fixture missing")
            if (output / (job["Case"] + "-baseline.json")).exists():
                raise ValueError("refusing to recapture an existing control")
        jobs_path = output / "jobs.json"
        jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
        env = dict(os.environ, GTT_EFFECT_JOBS=str(jobs_path), GTT_EFFECT_INPUT_OUTPUT=str(output), GOMAXPROCS="1")
        subprocess.run(["C:/Program Files/Go/bin/go.exe", "test", "-overlay", str(path),
                        "./pkg/optimization", "-run", "TestEffectInputControlledCaptures", "-count=1", "-v", "-timeout", "180s"],
                       cwd=engine, env=env, check=True, timeout=190)


if __name__ == "__main__":
    main()
