"""Burgeon failed-capture identity gate; managed-only, no artifact search.

Retire with the matrix observer probes. Expanded source/captures/cache belong to
the existing managed job. Only stdout facts are retained in the Go design.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.experiments.gcsim.parametric_effects.repair_health_identity import run_repair
from tools.experiments.gcsim.parametric_effects.repair_hit_identity import capture, CONTROL
from tools.experiments.gcsim.all_sets_inventory_regression.run import json_bytes, sha
from tools.experiments.gcsim.mode_matrix.run_product_matrix import _request
from run_workspace.gcsim.optimizer_go_selected import _prepare_inputs
from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsSession
from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context


def exact_request(job):
    after = json.loads((ROOT/'docs/optimizer-evidence/all-sets-inventory-20260919/after.json').read_bytes())
    rows = [r for r in after['runs'] if r['id'] == 'burgeon_all_sets']
    if len(rows) != 1 or rows[0]['success'] or 'unstable hit identity' not in rows[0]['error']:
        raise ValueError('Only failed Burgeon attempt1 is in scope')
    row = rows[0]
    engine = load_active_gcsim_optimizer_engine_context()
    if engine.engine_id != row['engine_identity']['id'] or engine.artifact_sha256 != row['engine_identity']['artifact_sha256']:
        raise ValueError('Active engine differs from failed row')
    manifest = json.loads((ROOT/'tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json').read_bytes())
    run = job/'original-request'
    run.mkdir()
    request = _request(row['input_entry'], db_path=ROOT/manifest['db_path'], run_root=job/'unused')
    session = GcsimOptimizerGoAllSetsSession(request)
    req = _prepare_inputs(request, run, virtual_artifact_policy=session.virtual_artifact_policy)['request']
    if sha(json_bytes(req['artifacts'])) != row['inventory_search']['inventory_sha256']:
        raise ValueError('Inventory differs from failed row')
    if req['context']['prepared_config']['text'] != row['inventory_search']['prepared_config']:
        raise ValueError('Prepared config differs from failed row')
    print('NESTED_HIT_INPUT '+json.dumps(dict(inventory_sha256=sha(json_bytes(req['artifacts'])),
        engine_id=engine.engine_id)), flush=True)
    return req, sha((run/'request.json').read_bytes())


def inspect_nested_hits(engine, job, gate):
    reference = next((gate/'verification/contexts').glob('context-*/seed-742031889'))
    raw = capture(engine/'build/gtt-gcsim.exe', job, 'nested-hit-raw',
        (reference/'config.txt').read_text(encoding='utf-8'), raw=True)
    hits = raw['hits']
    ids = [h['hit_id'] for h in hits]
    if len(set(ids)) != len(ids) or any(i <= 0 for i in ids):
        raise ValueError('Nonunique/nonpositive nested identities')
    reordered = [i for i, value in enumerate(ids) if value != i+1]
    if not reordered:
        raise ValueError('Expected concrete failing old sequential-identity assumption')
    first = reordered[0]
    # Only a bounded identity witness, not a retained raw trace.
    print('NESTED_HIT_WITNESS '+json.dumps(dict(hits=len(hits), reordered=len(reordered),
        first_observation=first, ids=ids[max(0,first-2):first+4])), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--activate', action='store_true')
    parser.add_argument('--test-only', action='store_true')
    parser.add_argument('--sourcegen-only', action='store_true')
    args = parser.parse_args()
    run_repair(args, fragment_names=('nested_hit_identity.patch',),
        installed_marker='pkg/optimization/gtt_hit_identity.go', original_provider=exact_request,
        label='NESTED_HIT', control_config_override=CONTROL, capture_inspector=inspect_nested_hits,
        use_installed_consumer=True)


if __name__ == '__main__':
    main()
