"""Explicit no-stat-snapshot observer attestation, Bountiful attempt2 gate.

Managed-only; exact retained input and current inventory, never an item search.
Reuses active-lineage reconstruction, invariant captures and transactional
promotion. Owner/retirement: Go design neutral preparation/startup receipt.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.experiments.gcsim.parametric_effects.repair_health_identity import run_repair
from tools.experiments.gcsim.all_sets_inventory_regression.run import json_bytes, receipt_bytes, sha
from tools.experiments.gcsim.mode_matrix.run_product_matrix import _request
from run_workspace.gcsim.optimizer_go_selected import _prepare_inputs
from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsSession
from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context


def exact_request(job):
    after = json.loads((ROOT/'docs/optimizer-evidence/all-sets-inventory-20260919/after.json').read_bytes())
    rows = [r for r in after['runs'] if r['id'] == 'bountiful_core_all_sets']
    if [r['attempt'] for r in rows] != [1, 2] or rows[-1]['success']:
        raise ValueError('Only failed Bountiful attempt2 is in scope')
    row = rows[-1]
    engine = load_active_gcsim_optimizer_engine_context()
    if engine.engine_id != row['engine_identity']['id'] or engine.artifact_sha256 != row['engine_identity']['artifact_sha256']:
        raise ValueError('Active engine differs from failed row')
    manifest = json.loads((ROOT/'tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json').read_bytes())
    run = job/'original-request'
    run.mkdir()
    request = _request(row['input_entry'], db_path=ROOT/manifest['db_path'], run_root=job/'unused')
    session = GcsimOptimizerGoAllSetsSession(request)
    prepared = _prepare_inputs(request, run, virtual_artifact_policy=session.virtual_artifact_policy)
    req = prepared['request']
    if sha(receipt_bytes(req['artifacts'])) != row['inventory_search']['inventory_sha256']:
        raise ValueError('Inventory differs from failed row')
    if req['context']['prepared_config']['text'] != row['inventory_search']['prepared_config']:
        raise ValueError('Prepared config differs from failed row')
    print('EMPTY_SNAPSHOT_INPUT '+json.dumps(dict(inventory_sha256=sha(json_bytes(req['artifacts'])),
        attempt2_compact_inventory_sha256=sha(receipt_bytes(req['artifacts'])), engine_id=engine.engine_id)), flush=True)
    return req, sha((run/'request.json').read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate', action='store_true')
    parser.add_argument('--test-only', action='store_true')
    parser.add_argument('--sourcegen-only', action='store_true')
    args = parser.parse_args()
    run_repair(args, fragment_names=('empty_snapshot.patch',),
        installed_marker='pkg/gttcompact/empty_snapshot_test.go',
        original_provider=exact_request, label='EMPTY_SNAPSHOT')


if __name__ == '__main__':
    main()
