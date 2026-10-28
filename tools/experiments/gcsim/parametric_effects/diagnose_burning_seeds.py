"""Paired two-seed response of the retained Burning winner, never item search.

Managed-only: four captures total (neutral and winner per original seed), no
ordinary n500 rerun, engine install or equipment write. Keep only stdout facts
in the dated Go design; retire with matrix response diagnosis. The managed
launcher owns and deletes request, source bundle, captures and build cache.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.experiments.gcsim.parametric_effects.verify_candidates import owned_job
from tools.experiments.gcsim.parametric_effects.repair_hit_identity import execute
from tools.experiments.gcsim.all_sets_inventory_regression.run import json_bytes, sha
from tools.experiments.gcsim.mode_matrix.run_product_matrix import _request, _scratch_environment
from run_workspace.gcsim.optimizer_go_selected import _prepare_inputs
from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsSession
from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context


def main():
    job = owned_job()
    after = json.loads((ROOT/'docs/optimizer-evidence/all-sets-inventory-20260919/after.json').read_bytes())
    rows = [r for r in after['runs'] if r['id'] == 'burning_all_sets']
    if len(rows) != 1 or not rows[0]['success']:
        raise ValueError('Only saved Burning attempt1 is in scope')
    row = rows[0]
    engine = load_active_gcsim_optimizer_engine_context()
    if engine.engine_id != row['engine_identity']['id'] or engine.artifact_sha256 != row['engine_identity']['artifact_sha256']:
        raise ValueError('Active engine differs from saved row')
    manifest = json.loads((ROOT/'tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json').read_bytes())
    run = job/'seed-response'
    run.mkdir()
    with _scratch_environment(job):
        request = _request(row['input_entry'], db_path=ROOT/manifest['db_path'], run_root=job/'unused')
        session = GcsimOptimizerGoAllSetsSession(request)
        prepared = _prepare_inputs(request, run, virtual_artifact_policy=session.virtual_artifact_policy)
        req = prepared['request']
        if sha(json_bytes(req['artifacts'])) != row['inventory_search']['inventory_sha256']:
            raise ValueError('Current inventory differs from saved row')
        if req['context']['prepared_config']['text'] != row['inventory_search']['prepared_config']:
            raise ValueError('Prepared config differs from saved row')
        started = time.monotonic()
        session._validate_optimizer_request(run_dir=run, started=started)
        session._prepare_formula_inputs(prepared=prepared, run_dir=run, started=started)
        top = row['product']['candidates'][0]
        ids = {b['wearer_key']: b['artifact_ids'] for b in top['builds']}
        slots = ('flower', 'plume', 'sands', 'goblet', 'circlet')
        winner = dict(Assignment=[[ids[w['wearer_key']][slot] for slot in slots] for w in req['wearers']],
                      Expected=float(top['formula_dps']))
        (run/'winner.json').write_bytes(json_bytes(winner))
        go = shutil.which('go') or r'C:/Program Files/Go/bin/go.exe'
        print(execute([go, 'test', '-p', '1', './internal/allsets', '-run', '^TestMatrixWinnerSeedResponse$',
                       '-count=1', '-v', '-timeout=240s'], cwd=ROOT/'native/gcsim_optimizer',
                      env=dict(os.environ, GTT_MATRIX_SEED_RESPONSE_RUN=str(run)), timeout=270), flush=True)
    if load_active_gcsim_optimizer_engine_context() != engine:
        raise ValueError('Active engine changed during diagnosis')


if __name__ == '__main__':
    main()
