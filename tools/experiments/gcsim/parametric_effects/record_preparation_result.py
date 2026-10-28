"""Bounded receipt closeout; no simulation, account access or code mutation.

Owner: Go design 2026-09-27 preparation receipt. Retire with its managed probes.
Only existing successor metadata/report change; every run and baseline survives.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.experiments.gcsim.parametric_effects.verify_candidates import owned_job
from tools.experiments.gcsim.all_sets_inventory_regression.run import BASELINE, OUTPUT, sha, store_after
from tools.experiments.gcsim.all_sets_inventory_regression.report import write_report


def main():
    job = owned_job()
    data = json.loads((OUTPUT/'after.json').read_bytes())
    original_runs = json.dumps(data['runs'], sort_keys=True)
    rows = [r for r in data['runs'] if r['id'] == 'bountiful_core_all_sets']
    if [r['attempt'] for r in rows] != [1, 2, 3] or rows[1]['success'] or not rows[2]['success']:
        raise ValueError('Expected retained failed attempt2 and successful attempt3')
    row = rows[2]
    engine = row['engine_identity']
    if engine['id'] != 'gcsim-v2.45.0-20260926234622' or row['optimizer_sha256'] != 'bd9d7758ed3d492d2765bb8437cacdb932f74123bcff5ea37c689d060a714aab':
        raise ValueError('Wrong reviewed installation')
    if row['input_entry'] != rows[1]['input_entry'] or row['rotation_sha256'] != rows[1]['rotation_sha256'] or row['inventory_search']['prepared_config'] != rows[1]['inventory_search']['prepared_config']:
        raise ValueError('Inputs differ from diagnosed startup failure')
    if BASELINE.read_bytes() != (OUTPUT/'before.json').read_bytes() or sha(BASELINE.read_bytes()) != data['before_sha256']:
        raise ValueError('Immutable original matrix differs')
    work = row['inventory_search']
    if work['neutral_model']['Unavailable'] or any(c['NotPrepared'] or c['NotProcessed'] for c in work['neutral_cycles']):
        raise ValueError('Reviewed complete preparation gate changed')
    data['matrix_status'] = 'stepwise_bountiful_neutral_pass_preparation_reduced'
    data['stop_reason'] = (
        'Parent-reviewed Bountiful attempt3 completes on the installed engine: 59811.818 DPS/SE16.969, '
        'n500, wall122.859s; original matrix55640.014/167.25s, historical attempt1 57467.168/469.578s. '
        'Old engine/inventory differ: these historical comparisons do not isolate preparation speed. '
        'Preparation32.736s, search84.775s, final verification23.234s; nested counters overlap. '
        'Two2096/2096 cycles, zero unavailable,2932 heuristic deferrals; stop neutral_cycle_budget, '
        'not timeout/exhaustive optimum. Both bounded joint lanes finish in10.231s total. '
        'Startup failure attempt2 is preserved; generic no-snapshot observer fix passes exact-input '
        'initial gates and ordinary-damage invariance. Baseline and every attempt survive. '
        'Next: parent-reviewed next team only; no Gaming, fifth Lunar, extra Bountiful retry, budget increase or batch.')
    data['preparation_reduction_review'] = {
        'date': '2026-09-27', 'receipt': 'docs/handoff/GCSIM_OPTIMIZER_GO_BACKEND_DESIGN.md',
        'dense_map_parity': 'exact_unit_graph_gradient_and_initial_boundary_parity',
        'whole_session_isolated_speedup_proven': False,
        'bountiful_attempt2_inventory_digest_encoding': {
            'recorded_compact': rows[1]['inventory_search']['inventory_sha256'],
            'verified_historical_codec': row['inventory_search']['inventory_sha256'],
            'proof': 'same_inventory_verified_during_initial_diagnosis_and_observer_install; original row is not rewritten',
        },
        'bountiful_attempt3': {'engine': engine, 'optimizer_sha256': row['optimizer_sha256'],
            'same_prepared_config_rotation_input_entry_as_attempt2': True,
            'cleanup_removed_bytes': 86561669, 'expanded_job_absent': True,
            'physical_ui_checked': False},
    }
    if json.dumps(data['runs'], sort_keys=True) != original_runs:
        raise ValueError('Closeout mutated a retained run')
    store_after(OUTPUT/'after.json', data, job)
    write_report(OUTPUT)
    print('Preparation closeout: original baseline and all '+str(len(data['runs']))+' attempts preserved; no captures/searches.')


if __name__ == '__main__':
    main()
