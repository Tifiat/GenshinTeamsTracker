"""One exact saved Chasca request through the installed All Sets process adapter.

Managed scratch owns expanded output; at most three immutable <=2 MiB receipts
preserve original inputs, failures and final candidates. No equipment/DB writes,
no budget expansion. Engine binding changes are explicit; UI clicking is a
separate gate. Retire this helper after Chasca startup acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[4]
MAX_RECEIPT_BYTES=2*1024*1024
VALID_ATTEMPTS=(1,2,3)
sys.path.insert(0,str(ROOT))
from tools.experiments.gcsim.parametric_effects.verify_candidates import owned_job
from tools.experiments.gcsim.parametric_effects.repair_health_identity import SAVED,rebind_request,write_json
from run_workspace.gcsim.optimizer_go_contracts import canonical_sha256
from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsRequest,GcsimOptimizerGoAllSetsSession


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt_path_for_attempt(attempt, root=None):
    if isinstance(attempt,bool) or not isinstance(attempt,int) or attempt not in VALID_ATTEMPTS:
        raise ValueError('Attempt must be 1, 2, or 3')
    base=ROOT if root is None else Path(root)
    return base/f'docs/optimizer-evidence/all-sets-inventory-20260919/chasca-user-startup-attempt{attempt}-20260926.json'


def save_receipt(attempt, receipt, root=None):
    path=receipt_path_for_attempt(attempt,root=root)
    data=(json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
    if len(data)>MAX_RECEIPT_BYTES:raise ValueError('Receipt exceeds 2 MiB finite retention limit')
    with path.open('xb') as out:out.write(data)
    return path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt',type=int,choices=VALID_ATTEMPTS,required=True)
    args=parser.parse_args()
    job=owned_job()
    receipt_path=receipt_path_for_attempt(args.attempt)
    if receipt_path.exists():raise ValueError('Immutable evidence slot already used')
    original=json.loads((SAVED/'request.json').read_bytes())
    before=json.loads((SAVED/'selected-result.json').read_bytes())
    engine=load_active_gcsim_optimizer_engine_context()
    if not (Path(engine.engine_root)/'pkg/gttsourcegen/health_field_capture.go').is_file():raise ValueError('Health repair not installed')
    req=rebind_request(original,Path(engine.engine_root))
    for key in original:
        if key not in ('engine','context') and req[key]!=original[key]:raise ValueError('Saved gameplay inputs changed')
    for key in ('prepared_config','rotation','target','context_sha256'):
        if req['context'][key]!=original['context'][key]:raise ValueError('Saved context changed')
    work=job/'replay'
    work.mkdir()
    write_json(work/'request.json',req)
    request_sha=canonical_sha256(req)
    request=GcsimOptimizerGoAllSetsRequest(db_path=str(ROOT/'data/artifacts.db'),selected_team={},team_index=0,
        rotation_shell_text='',infinite_energy_enabled=True,run_root=str(job/'unused-runs'),
        product_timeout_ms=original['budgets']['product_timeout_ms'])
    binary=Path(request.optimizer_binary_path)
    binary_sha=sha(binary)
    prepared=dict(request=req,request_sha256=request_sha)
    stage=''
    def progress(row):
        nonlocal stage
        if row.get('stage')!=stage:
            stage=row.get('stage')
            print(f'CHASCA_REPLAY {stage} at {float(row.get("elapsed_ms") or 0)/1000:.3f}s',flush=True)
    session=GcsimOptimizerGoAllSetsSession(request,progress_callback=progress)
    receipt=dict(schema_version=1,scope='exact_saved_inputs_rebound_to_active_engine_button_process_adapter',
        source_run=SAVED.name,original_request_sha256=sha(SAVED/'request.json'),original_request=original,
        rebound_request_sha256=request_sha,engine_id=engine.engine_id,engine_sha256=engine.artifact_sha256,
        optimizer_sha256=binary_sha,before=before,physical_button_verified=False,success=False)
    started=time.monotonic()
    try:
        session._validate_optimizer_request(run_dir=work,started=started)
        session._prepare_formula_inputs(prepared=prepared,run_dir=work,started=started)
        session._run_go_optimizer(prepared=prepared,compact={},run_dir=work,started=started)
        wrapper=json.loads((work/'optimizer-output.json').read_bytes())
        receipt.update(success=True,replay_wall_seconds=time.monotonic()-started,
            after={k:wrapper.get(k) for k in ('total_elapsed_ms','search_seconds','proposal_seconds','neutral_model',
                'neutral_cycles','neutral_joint_seconds','neutral_stabilization','search_expansions','search_stop_reason',
                'search_config','capture_members','effect_boundaries','verification','product_result','search_work')})
        current=load_active_gcsim_optimizer_engine_context()
        if current.engine_id!=engine.engine_id or current.artifact_sha256!=engine.artifact_sha256 or sha(binary)!=binary_sha:
            raise ValueError('Active executable identity changed during replay')
    except BaseException as exc:
        receipt.update(success=False,error=str(exc),replay_wall_seconds=time.monotonic()-started)
        raise
    finally:
        receipt_path=save_receipt(args.attempt,receipt)
        print('CHASCA_RESULT '+json.dumps(dict(success=receipt['success'],receipt=str(receipt_path),
            seconds=receipt['replay_wall_seconds'],error=receipt.get('error'),
            winner=receipt.get('after',{}).get('verification',{}).get('winner')),ensure_ascii=False),flush=True)


if __name__=='__main__':main()
