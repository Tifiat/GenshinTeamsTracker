"""One bounded saved-request product replay for the feather/preparation repair.

Uses the button's actual session preflight/source producer/process adapter and
installed consumer/active engine, but skips account input rebuilding in order
to preserve the user's exact request. No UI/equipment/DB changes. One immutable
receipt (<=1 MiB) is retained; all expanded output/builds live in managed scratch.
Retire this probe with the Flins acceptance research helpers.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.experiments.gcsim.parametric_effects.verify_candidates import owned_job

RECEIPT = ROOT / 'docs/optimizer-evidence/all-sets-inventory-20260919/flins-user-stabilization-20260926.json'
BINARY = ROOT / 'native/gcsim_optimizer/gtt-optimizer.exe'
MAX_BYTES = 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save_receipt(path: Path, value):
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    if len(data) > MAX_BYTES:
        raise ValueError('Receipt exceeds 1 MiB; previous evidence is untouched')
    # Fixed one-run slot. Never reset earlier failed or successful measurements.
    with path.open('xb') as stream:
        stream.write(data)


def main():
    job = owned_job()
    if len(sys.argv) != 2:
        raise ValueError('Pass the one saved user run directory')
    if RECEIPT.exists():
        raise ValueError('This single-run evidence slot is already used')
    run = Path(sys.argv[1]).resolve(strict=True)
    if run.parent != (ROOT / 'data/gcsim/optimizer-go-runs').resolve():
        raise ValueError('Expected a retained product run')
    raw = (run / 'request.json').read_bytes()
    req = json.loads(raw)
    old = json.loads((run / 'optimizer-output.json').read_bytes())
    from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
    from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsRequest, GcsimOptimizerGoAllSetsSession
    engine = load_active_gcsim_optimizer_engine_context()
    if (engine.artifact_sha256 != req['engine']['artifact_sha256'] or
            Path(engine.artifact_path).resolve() != Path(req['engine']['binary_path']).resolve()):
        raise ValueError('Saved request is not bound to the active button engine')
    previous = sha(BINARY.read_bytes())
    go = ['C:/Program Files/Go/bin/go.exe', '-C', str(ROOT / 'native/gcsim_optimizer')]
    env = dict(os.environ, GTT_RULE_SOURCE_BUNDLE=str(run / 'set-sources.json'), GTT_SAVED_FEATHER_RUN=str(run))
    subprocess.run([*go, 'test', '-p', '1', './...', '-count=1', '-timeout=300s'], env=env, check=True)
    candidate = job / 'gtt-optimizer.exe'
    subprocess.run([*go, 'build', '-trimpath', '-o', str(candidate), './cmd/gtt-optimizer'], check=True)
    if sha(BINARY.read_bytes()) != previous:
        raise ValueError('Installed optimizer changed during the build')
    backup = job / 'previous-optimizer.exe'
    shutil.copy2(BINARY, backup)
    work = job / 'replay'
    work.mkdir()
    shutil.copy2(run / 'request.json', work / 'request.json')
    request_sha = old['product_result']['request_sha256']
    request = GcsimOptimizerGoAllSetsRequest(db_path=str(ROOT / 'data/artifacts.db'),
        selected_team={}, team_index=0, rotation_shell_text='', infinite_energy_enabled=True,
        run_root=str(job / 'unused-runs'))
    prepared = dict(request=req, request_sha256=request_sha)
    stage = ''
    def progress(row):
        nonlocal stage
        if row.get('stage') != stage:
            stage = row.get('stage')
            print(f'PRODUCT_REPLAY {stage} at {float(row.get("elapsed_ms") or 0)/1000:.3f}s', flush=True)
    session = GcsimOptimizerGoAllSetsSession(request, progress_callback=progress)
    if Path(request.optimizer_binary_path).resolve() != BINARY.resolve():
        raise ValueError('Default button consumer path changed')
    receipt = dict(schema_version=1, scope='exact_saved_request_button_process_adapter',
        source_run=run.name, raw_request_sha256=sha(raw), canonical_request_sha256=request_sha,
        engine_id=engine.engine_id, engine_sha256=engine.artifact_sha256,
        previous_optimizer_sha256=previous, optimizer_sha256=sha(candidate.read_bytes()),
        prepared_config=req['context']['prepared_config']['text'], go_suite='pass',
        before={k:old.get(k) for k in ('total_elapsed_ms','search_seconds','neutral_model','neutral_cycles',
          'search_expansions','search_stop_reason','search_config','verification')}, success=False)
    started = time.monotonic()
    try:
        shutil.copy2(candidate, BINARY)
        session._validate_optimizer_request(run_dir=work, started=started)
        session._prepare_formula_inputs(prepared=prepared, run_dir=work, started=started)
        if json.loads((work / 'set-sources.json').read_bytes()) != json.loads((run / 'set-sources.json').read_bytes()):
            raise ValueError('Active source envelope differs from the saved run')
        result = session._run_go_optimizer(prepared=prepared, compact={}, run_dir=work, started=started)
        wrapper = json.loads((work / 'optimizer-output.json').read_bytes())
        receipt.update(success=True, replay_wall_seconds=time.monotonic()-started,
            after={k:wrapper.get(k) for k in ('total_elapsed_ms','search_seconds','proposal_seconds','neutral_model',
             'neutral_cycles','neutral_joint_seconds','neutral_stabilization','search_expansions','search_stop_reason',
             'search_config','capture_members','effect_boundaries','verification','product_result','search_work')})
        if sha((work / 'request.json').read_bytes()) != sha(raw) or sha(BINARY.read_bytes()) != receipt['optimizer_sha256']:
            raise ValueError('Request or installed consumer changed during replay')
        final_engine = load_active_gcsim_optimizer_engine_context()
        if final_engine.artifact_sha256 != engine.artifact_sha256 or final_engine.engine_id != engine.engine_id:
            raise ValueError('Active engine changed during replay')
        save_receipt(RECEIPT, receipt)
        print('REPLAY_RESULT ' + json.dumps(dict(success=True, receipt=str(RECEIPT), seconds=receipt['replay_wall_seconds'],
          search_seconds=wrapper['search_seconds'], model=wrapper['neutral_model'],
          stabilization=wrapper['neutral_stabilization'], winner=wrapper['verification']['winner']), ensure_ascii=False), flush=True)
    except BaseException as exc:
        shutil.copy2(backup, BINARY)
        receipt.update(success=False, error=str(exc), replay_wall_seconds=time.monotonic()-started, consumer_restored=True)
        if not RECEIPT.exists():
            save_receipt(RECEIPT, receipt)
        raise


if __name__ == '__main__':
    main()
