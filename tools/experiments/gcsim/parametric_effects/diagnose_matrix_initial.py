"""Managed Bountiful attempt2 startup diagnosis, never an inventory search.

Owner: dated Go design preparation receipt. Retire after this startup gate.
Two neutral captures only; all expanded output/cache is managed and removed.
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
from tools.experiments.gcsim.all_sets_inventory_regression.run import json_bytes, receipt_bytes, sha
from tools.experiments.gcsim.mode_matrix.run_product_matrix import _request
from run_workspace.gcsim.optimizer_go_selected import _prepare_inputs
from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsSession
from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context


def main():
    job = owned_job()
    after = json.loads((ROOT/'docs/optimizer-evidence/all-sets-inventory-20260919/after.json').read_bytes())
    rows = [r for r in after['runs'] if r['id'] == 'bountiful_core_all_sets']
    if [r['attempt'] for r in rows] != [1, 2] or rows[-1]['success']:
        raise ValueError('Only the retained failed Bountiful attempt2 is in scope')
    row = rows[-1]
    engine = load_active_gcsim_optimizer_engine_context()
    if engine.engine_id != row['engine_identity']['id'] or engine.artifact_sha256 != row['engine_identity']['artifact_sha256']:
        raise ValueError('Active engine differs from failed row')
    manifest = json.loads((ROOT/'tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json').read_bytes())
    run = job/'diagnosis'
    run.mkdir()
    request = _request(row['input_entry'], db_path=ROOT/manifest['db_path'], run_root=job/'unused')
    session = GcsimOptimizerGoAllSetsSession(request)
    prepared = _prepare_inputs(request, run, virtual_artifact_policy=session.virtual_artifact_policy)
    req = prepared['request']
    # Attempt2 was recorded during a receipt-only formatter change that also
    # affected its inventory digest. Verify that exact encoding, then print the
    # established identity too. Subsequent rows again use the historical codec.
    if sha(receipt_bytes(req['artifacts'])) != row['inventory_search']['inventory_sha256']:
        raise ValueError('Inventory differs from failed row')
    if req['context']['prepared_config']['text'] != row['inventory_search']['prepared_config']:
        raise ValueError('Prepared config differs from failed row')
    print('INITIAL_IDENTITY '+json.dumps(dict(inventory_sha256=sha(json_bytes(req['artifacts'])),
        attempt2_compact_inventory_sha256=sha(receipt_bytes(req['artifacts'])),
        engine_id=engine.engine_id, engine_sha256=engine.artifact_sha256)), flush=True)
    started = time.monotonic()
    session._validate_optimizer_request(run_dir=run, started=started)
    session._prepare_formula_inputs(prepared=prepared, run_dir=run, started=started)
    go = shutil.which('go') or r'C:\Program Files\Go\bin\go.exe'
    print(execute([go,'test','-p','1','./internal/allsets','-run','^TestMatrixInitialDiagnosis$',
        '-count=1','-v','-timeout=150s'], cwd=ROOT/'native/gcsim_optimizer',
        env=dict(os.environ,GTT_MATRIX_INITIAL_RUN=str(run)),timeout=180), flush=True)
    if load_active_gcsim_optimizer_engine_context() != engine:
        raise ValueError('Active engine changed during diagnosis')


if __name__ == '__main__':
    main()
