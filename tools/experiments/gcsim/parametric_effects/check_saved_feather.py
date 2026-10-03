"""Read-only saved-run feather diagnosis; all generated output is managed scratch.

Temporary Flins acceptance probe. No optimizer search, account writes, engine
changes or persistent output. Retain only compact measurements in the Go design;
remove this probe with the parametric research helpers at the Flins cleanup gate.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.experiments.gcsim.parametric_effects.verify_candidates import owned_job


def replace_feather(config: str, before: dict, after: dict) -> str:
    if (before['slot'], before['set_uid'], before['main_stat']) != (
        after['slot'], after['set_uid'], after['main_stat']
    ) or before['slot'] != 'plume':
        raise ValueError('Expected same-slot, same-set, same-main-stat substitution')
    keys = {'atk_percent': 'atk%', 'crit_rate': 'cr', 'crit_damage': 'cd', 'hp': 'hp'}
    delta = {}
    for item, sign in ((before, -1), (after, 1)):
        for stat in item['substats']:
            key = keys[stat['key']]
            delta[key] = delta.get(key, Decimal(0)) + sign * Decimal(stat['value'])
    match = re.search(r'^flins add stats ([^;]+);$', config, re.M)
    if match is None:
        raise ValueError('Missing Flins artifact row')
    fields = [part.split('=', 1) for part in match[1].split()]
    for field in fields:
        if field[0] in delta:
            field[1] = format(Decimal(field[1]) + delta.pop(field[0]), '.6f')
    if delta:
        raise ValueError('A changed stat was absent from the saved row')
    row = 'flins add stats ' + ' '.join('='.join(field) for field in fields) + ';'
    return config[:match.start()] + row + config[match.end():]


def main() -> None:
    job = owned_job()
    if len(sys.argv) != 2:
        raise ValueError('Pass one saved product run directory')
    run = Path(sys.argv[1]).resolve(strict=True)
    if run.parent != (ROOT / 'data/gcsim/optimizer-go-runs').resolve():
        raise ValueError('Expected a saved product run')
    request = json.loads((run / 'request.json').read_bytes())
    output = json.loads((run / 'optimizer-output.json').read_bytes())
    winner = output['verification']['winner']
    if winner['assignment'][1][1] != 1534 or request['wearers'][1]['wearer_key'] != 'flins':
        raise ValueError('Unexpected saved winner')
    configs = [path for path in (run / 'verification/final-n500').rglob('config.txt')
               if hashlib.sha256(path.read_bytes()).hexdigest() == winner['config_sha256']]
    if len(configs) != 1:
        raise ValueError('Exact saved winner config not found')
    config = configs[0].read_text(encoding='utf-8')
    artifacts = {item['artifact_id']: item for item in request['artifacts']}
    swap = replace_feather(config, artifacts[1534], artifacts[1535])
    from run_workspace.gcsim.artifact_runner import run_active_gcsim_artifact
    from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
    engine = load_active_gcsim_optimizer_engine_context()
    if Path(engine.artifact_path).resolve() != Path(request['engine']['binary_path']).resolve() or engine.artifact_sha256 != request['engine']['artifact_sha256']:
        raise ValueError('Saved run does not use the active button engine')
    old = json.loads((ROOT / 'docs/optimizer-evidence/all-sets-inventory-20260919/after.json').read_bytes())['runs'][-1]
    old_prepared = old['inventory_search']['prepared_config']
    if request['context']['prepared_config']['text'].replace('talent=10,10,10', 'talent=9,9,9').strip() != old_prepared.strip():
        raise ValueError('Input differences extend beyond the four talent rows')
    print('INPUT_COMPARISON ' + json.dumps(dict(engine_id=engine.engine_id, engine_sha256=engine.artifact_sha256,
        prepared_difference='four talent rows: 10,10,10 vs 9,9,9; trailing newline only',
        before=artifacts[1534], after=artifacts[1535], saved_dps=winner['measured_dps'])), flush=True)
    cases = [('exact_user_top1_n500', config),
             ('same_top1_talents9_n500', config.replace('talent=10,10,10', 'talent=9,9,9')),
             ('user_top1_n4000', config.replace('iteration=500', 'iteration=4000')),
             ('user_swap1535_n4000', swap.replace('iteration=500', 'iteration=4000'))]
    for name, text in cases:
        started = time.perf_counter()
        result = run_active_gcsim_artifact(text, run_dir=job / name, timeout_seconds=180,
                                          expected_engine_id=engine.engine_id)
        if not result.success:
            raise RuntimeError(f'{name}: {result.status}: {result.error}')
        print('FEATHER_SIM ' + json.dumps(dict(name=name, dps=result.summary.dps_mean,
            standard_error=result.summary.dps_se, iterations=result.summary.iterations,
            duration=result.summary.duration_mean, failed_actions=list(result.summary.failed_actions),
            seconds=time.perf_counter()-started, config_sha256=hashlib.sha256(text.encode()).hexdigest())), flush=True)
    env = dict(os.environ, GTT_SAVED_FEATHER_RUN=str(run))
    subprocess.run(['C:/Program Files/Go/bin/go.exe', 'test', './internal/allsets',
                    '-run', '^TestSavedFeatherDiagnosis$', '-count=1', '-v', '-timeout=180s'],
                   cwd=ROOT / 'native/gcsim_optimizer', env=env, check=True)
    after = load_active_gcsim_optimizer_engine_context()
    if (after.engine_id, after.artifact_sha256) != (engine.engine_id, engine.artifact_sha256):
        raise RuntimeError('Active engine changed during diagnosis')


if __name__ == '__main__':
    main()
