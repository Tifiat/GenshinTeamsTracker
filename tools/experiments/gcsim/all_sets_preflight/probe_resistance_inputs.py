"""Isolated resistance-port overlay. Exactly four opt-in n1 controls, no install.

Uses reviewed source copies. The generated numeric marker gets one mechanical
ABI-label substitution; its existing arithmetic is unchanged. This research
overlay is not an updater patch and is consolidated only after acceptance.
"""
from pathlib import Path
import argparse
import json
import os
import subprocess
import shutil
import sys

p = argparse.ArgumentParser(__doc__)
p.add_argument("--engine-root", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--capture-controls", action="store_true")
p.add_argument("--prepare", action="store_true")
a = p.parse_args()
here = Path(__file__).resolve().parent
root = here.parents[3]
engine, output = a.engine_root.resolve(), a.output.resolve()
output.relative_to(root / ".codex_tmp")
if a.prepare:
    subprocess.run([sys.executable, str(here / "probe_effect_inputs.py"), "--engine-root", str(engine),
                    "--output", str(output), "--prepare"], cwd=root, check=True)
    for name in ("builder.go", "direct.go", "numeric_recipe.go", "contributor_group.go"):
        shutil.copyfile(engine / "pkg/gttcompact" / name, output / name)
    shutil.copyfile(engine / "build/gtt-source-overlay/pkg/enemy/damage.go", output / "damage.go")
    prefix = output.relative_to(root).as_posix()+"/"
    patch = here / "resistance_inputs_experiment.patch"
    subprocess.run(["git", "apply", "--check", "--directory", prefix, str(patch)], cwd=root, check=True)
    subprocess.run(["git", "apply", "--directory", prefix, str(patch)], cwd=root, check=True)
overlay = json.loads((output / "overlay.json").read_text())
for name in ("builder.go", "direct.go", "numeric_recipe.go", "contributor_group.go"):
    overlay["Replace"][str(engine / "pkg/gttcompact" / name)] = str(output / name)
overlay["Replace"][str(engine / "pkg/gttcompact/resistance_input.go")] = str(here / "resistance_input.go")
damage = output / "damage.go"
source = damage.read_text()
before = 'Kind: "frozen",Value: resmod,Source:"resmod"'
after = 'Kind: "context_resistance_multiplier",Value: resmod,Source:"resmod"'
if source.count(before) == 1 and source.count(after) == 0:
    damage.write_text(source.replace(before, after), encoding="utf-8")
elif source.count(before) != 0 or source.count(after) != 1:
    raise ValueError("generated observer ABI changed; do not guess a binding")
overlay["Replace"][str(engine / "pkg/enemy/damage.go")] = str(damage)
path = output / "resistance-overlay.json"
path.write_text(json.dumps(overlay), encoding="utf-8")
go = "C:/Program Files/Go/bin/go.exe"
subprocess.run([go, "test", "-overlay", str(path), "./pkg/gttcompact", "-count=1"],
               cwd=engine, check=True, timeout=90)
if a.capture_controls:
    jobs = [
        dict(Case="bloom", Config=str(root / ".codex_tmp/selected-2plus2-20260916/run/prepared-config.txt"), Owner="kukishinobu", Element="dendro"),
        dict(Case="cloud", Config=str(root / ".codex_tmp/gob11-gp3-production-20260916/flins_1/selected-20260916-132613-fd420284/prepared-config.txt"), Owner="ineffa", Element="electro"),
    ]
    if any((output / (j["Case"]+"-baseline.json")).exists() or not Path(j["Config"]).is_file() for j in jobs):
        raise ValueError("missing approved fixture or existing control; refusing recapture")
    jobs_path = output / "jobs.json"
    jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
    env = dict(os.environ, GTT_EFFECT_JOBS=str(jobs_path), GTT_EFFECT_INPUT_OUTPUT=str(output),
               GTT_EFFECT_CONTROL="resistance", GOMAXPROCS="1")
    subprocess.run([go, "test", "-overlay", str(path), "./pkg/optimization", "-run",
                    "TestEffectInputControlledCaptures", "-count=1", "-v", "-timeout", "180s"],
                   cwd=engine, env=env, check=True, timeout=190)
