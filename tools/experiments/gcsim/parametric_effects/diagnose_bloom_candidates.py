"""Managed two-winner control for lunar bloom regression; never a matrix rerun.

Prepare the exact current product request, capture two neutral seeds once, score
two retained winners, then ordinary n500 for the old winner only. No engine or
DB writes. All generated output belongs to managed scratch; compact stdout is
retained in the Go design. Retire with the matrix regression diagnosis.
"""
from __future__ import annotations
import argparse
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
from tools.experiments.gcsim.mode_matrix.compare_flins_cross_assignment import (
    SLOTS, ARTIFACT_LINE, _build_config, _ordinary_budget,
    _bound_artifact_registry_source, normalize_optimizer_rotation_shell,
    load_active_gcsim_optimizer_engine_context, run_active_gcsim_artifact,
)
from run_workspace.gcsim.optimizer_go_selected import _prepare_inputs
from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsSession


def non_artifact_identity(config):
    # Different set counts leave a different number of empty lines after
    # removing declarations. Ignore only those empty lines, retaining all
    # remaining source text and declaration/action order exactly.
    lines = (line for line in ARTIFACT_LINE.sub('', config).splitlines() if line.strip())
    return sha('\n'.join(lines).encode())


def main():
    job = owned_job()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ordinary-only',action='store_true')
    args = parser.parse_args()
    after = json.loads((ROOT/'docs/optimizer-evidence/all-sets-inventory-20260919/after.json').read_bytes())
    rows = [r for r in after['runs'] if r['id']=='lunar_bloom_all_sets']
    if [r['attempt'] for r in rows] != [1,2]:
        raise ValueError('Expected retained attempts1/2; do not silently use another winner')
    old,current = rows
    engine = load_active_gcsim_optimizer_engine_context()
    if engine.engine_id != current['engine_identity']['id'] or engine.artifact_sha256 != current['engine_identity']['artifact_sha256']:
        raise ValueError('Not the same active matrix engine')
    manifest = json.loads((ROOT/'tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json').read_bytes())
    entry = current['input_entry']
    db = ROOT/manifest['db_path']
    run = job/'diagnosis'; run.mkdir()
    with _scratch_environment(job):
        request = _request(entry,db_path=db,run_root=job/'unused')
        session = GcsimOptimizerGoAllSetsSession(request)
        prepared = _prepare_inputs(request,run,virtual_artifact_policy=session.virtual_artifact_policy)
        req = prepared['request']
        if sha(json_bytes(req['artifacts'])) != current['inventory_search']['inventory_sha256']:
            raise ValueError('Inventory differs from current matrix row')
        if req['context']['prepared_config']['text'] != current['inventory_search']['prepared_config']:
            raise ValueError('Prepared config differs from current matrix row')
        started = time.monotonic()
        session._validate_optimizer_request(run_dir=run,started=started)
        if not args.ordinary_only:
            session._prepare_formula_inputs(prepared=prepared,run_dir=run,started=started)
        cases = []
        for label,row in [('old_winner',old),('current_winner',current)]:
            top = row['product']['candidates'][0]
            ids = {b['wearer_key']:b['artifact_ids'] for b in top['builds']}
            cases.append(dict(Name=label,Assignment=[[ids[w['wearer_key']][s] for s in SLOTS] for w in req['wearers']],
                Expected=float(top['formula_dps']) if label=='current_winner' else None))
        (run/'cases.json').write_bytes(json_bytes(cases))
        env = dict(os.environ,GTT_MATRIX_CANDIDATE_RUN=str(run))
        go = shutil.which('go') or r'C:\Program Files\Go\bin\go.exe'
        if not args.ordinary_only:
            print(execute([go,'test','-p','1','./internal/allsets','-run','TestMatrixCandidateDiagnosis','-count=1','-v','-timeout=180s'],
                cwd=ROOT/'native/gcsim_optimizer',env=env,timeout=210),flush=True)
        rotation = normalize_optimizer_rotation_shell(request.rotation_shell_text)
        rotation_path = job/'rotation.txt'; rotation_path.write_text(rotation.optimizer_text,encoding='utf-8')
        ids = {b['wearer_key']:b['artifact_ids'] for b in old['product']['candidates'][0]['builds']}
        config = _build_config(db_path=db,profiles=entry['virtual_profiles'],selected_team=request.selected_team,
            rotation_path=rotation_path,registry_path=_bound_artifact_registry_source(Path(engine.engine_root)),
            ids_by_wearer=ids,case_root=job/'old-winner',iterations=500)
        expected = non_artifact_identity(_ordinary_budget(req['context']['prepared_config']['text'],iterations=500,workers=4))
        if non_artifact_identity(config) != expected: raise ValueError('Non-artifact input changed')
        result = run_active_gcsim_artifact(config,run_dir=job/'ordinary',timeout_seconds=90,expected_engine_id=engine.engine_id)
        if not result.success or result.summary.iterations != 500: raise ValueError(f'Ordinary control failed: {result.error}')
        print('MATRIX_OLD_ORDINARY '+json.dumps(dict(dps=result.summary.dps_mean,standard_error=result.summary.dps_se,
            iterations=result.summary.iterations,config_sha256=sha(config.encode()),non_artifact_sha256=expected,
            engine_id=engine.engine_id,engine_sha256=engine.artifact_sha256,failed_actions=list(result.summary.failed_actions))),flush=True)
    active = load_active_gcsim_optimizer_engine_context()
    if active.engine_id!=engine.engine_id or active.artifact_sha256!=engine.artifact_sha256: raise ValueError('Active engine changed')


if __name__=='__main__': main()
