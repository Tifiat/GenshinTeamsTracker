"""Narrow derived image of the existing real AppShell button backend runner."""
from __future__ import annotations

import argparse
import ast
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import time
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
PARENT=HERE/'health_unified_button_backend.py'
PARENT_SHA='ef37c0bf06b75fc3f11bca0d4f8c88a55754216f40d6fc74802b3d24bcd9b80c'


def source_image(result_options=None):
    raw=PARENT.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PARENT_SHA:raise ValueError('frozen real button helper drift')
    source=raw.decode()
    def once(old,new):
        nonlocal source
        if source.count(old)!=1:raise ValueError('button image seam changed')
        source=source.replace(old,new)
    options=result_options or {'builds_per_group':2,'fast_mode':False,'set_group_limit':3}
    if options not in ({'builds_per_group':2,'fast_mode':False,'set_group_limit':3},{'builds_per_group':3,'fast_mode':False,'set_group_limit':3}):raise ValueError('frozen result options invalid')
    if options['builds_per_group']==2:
        once('"builds_per_group": 3, "fast_mode": False, "set_group_limit": 3,','"builds_per_group": 2, "fast_mode": False, "set_group_limit": 3,')
        once('"builds_per_group": 3,\n                "fast_mode": False, "expanded_limits": False','"builds_per_group": 2,\n                "fast_mode": False, "expanded_limits": False')
    # The simulator's internal finalist budget is independent of display K.
    once('or len(cohort) != 9','or not 1 <= len(cohort) <= payload["result_options"]["set_group_limit"] * payload["result_options"]["builds_per_group"]')
    once('"schema": "health_unified_button_backend_v1"','"schema": "whole_chasca_button_backend_v1"')
    once('super().__init__(replace(request, product_timeout_ms=0))','super().__init__(_whole_prepare_worker_request(request))\n            _whole_observe_actual_worker(self)')
    begin=source.index('    engine_binary = Path(payload["engine"]["binary_path"])')
    end=source.index('    case_root = scratch / "button-fixture"',begin)
    source=source[:begin]+'    engine_binary = _whole_resolve_engine(payload, scratch)\n'+source[end:]
    return source.encode()


def resolve_bound_engine(payload,scratch,owned_job_root,producer_root,expected_binding):
    """Only the admitted producer in this particular managed job is allowed."""
    from tools import managed_optimizer_experiment as managed
    from run_workspace.gcsim.optimizer_go_contracts import canonical_sha256
    from run_workspace.gcsim.source_manifest_build import canonical_json, SOURCE_MANIFEST_BODY_RELATIVE_PATH
    for path in (scratch,owned_job_root,producer_root):managed.assert_unlinked(Path(path).absolute())
    root=managed.MANAGED_ROOT.resolve(strict=True)
    job=Path(owned_job_root).resolve(strict=True)
    scope=Path(scratch).resolve(strict=True)
    producer=Path(producer_root).resolve(strict=True)
    if job.parent!=root or not job.name.startswith('job-') or not scope.is_relative_to(job) or scope==job or scope.name not in ('control','candidate') or not producer.is_relative_to(job) or producer==job:
        raise ValueError('button_producer_outside_asserted_managed_job')
    binding=payload.get('engine')
    if not isinstance(expected_binding,dict) or binding!=expected_binding:
        raise ValueError('button_admitted_engine_binding_changed')
    binary=Path(binding['binary_path'])
    if not binary.is_absolute() or '..' in binary.parts:raise ValueError('button_engine_path_not_absolute')
    managed.assert_unlinked(binary)
    binary=binary.resolve(strict=True)
    if not binary.is_relative_to(producer) or binary==producer or not binary.is_file():raise ValueError('button_engine_outside_explicit_producer')
    def file_sha(path):
        with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
    if file_sha(binary)!=binding['artifact_sha256']:raise ValueError('button_engine_artifact_changed')
    manifest=producer/SOURCE_MANIFEST_BODY_RELATIVE_PATH
    managed.assert_unlinked(manifest)
    # The builder stores canonical JSON plus a newline, but its identity hashes
    # only canonical_json(body). Reuse that definition, not the file-byte hash.
    if not manifest.is_file() or hashlib.sha256(canonical_json(json.loads(manifest.read_bytes())).encode('utf-8')).hexdigest()!=binding['source_manifest_sha256']:raise ValueError('button_engine_source_manifest_changed')
    expected=canonical_sha256({'kind':'gtt.standalone_engine_binding.v1',**{key:binding[key] for key in ('artifact_sha256','source_manifest_sha256','patch_manifest_sha256')}})
    if binding.get('binding_sha256')!=expected:raise ValueError('button_engine_binding_digest_changed')
    return binary


def validate_counters(counters,expected_mode):
    if expected_mode not in ('counts_only','wall_and_counts') or counters.get('Mode')!=expected_mode:
        raise ValueError('whole_counter_mode_changed')
    if counters.get('CPUAvailable') is not False or type(counters.get('SnapshotWallNS')) is not int or counters.get('SnapshotWallNS')!=0 or counters.get('ProjectionValueWitness')!='':
        raise ValueError('whole_counter_heavy_snapshot_or_witness')
    counts=counters.get('Counts');phases=counters.get('Phases')
    if not isinstance(counts,dict) or len(counts)>512 or any(not isinstance(k,str) or type(v)!=int or not 0<=v<2**64 for k,v in counts.items()):raise ValueError('whole_counter_counts_invalid')
    if not isinstance(phases,dict) or len(phases)>64 or expected_mode=='counts_only' and phases:raise ValueError('whole_counter_phase_budget_changed')
    fields={'Calls','WallNS','CPUNS','AllocBytes','Allocations','GCs'}
    for name,phase in phases.items():
        if not isinstance(name,str) or not name or len(name)>128 or not isinstance(phase,dict) or set(phase)!=fields or any(type(v)!=int or not 0<=v<2**64 for v in phase.values()) or any(phase[k] for k in ('CPUNS','AllocBytes','Allocations','GCs')):
            raise ValueError('whole_counter_phase_invalid')


def measured_rows(payload,result,*,allowed_iterations=(500,)):
    artifacts={a['artifact_id']:a for a in payload['artifacts']}
    rows=result.get('verification',{}).get('candidates')
    cap=payload['result_options']['set_group_limit']*payload['result_options']['builds_per_group']
    if not isinstance(rows,list) or not 1<=len(rows)<=cap:raise ValueError('whole verification cohort outside preserved budget')
    seen=set();out=[]
    slots=('flower','plume','sands','goblet','circlet')
    for row in rows:
        if not isinstance(row,dict):raise ValueError('whole finalist measurement shape invalid')
        assignment=row.get('assignment')
        if not isinstance(assignment,list) or len(assignment)!=4 or any(not isinstance(actor,list) or len(actor)!=5 for actor in assignment):raise ValueError('whole finalist physical shape invalid')
        flat=tuple(i for actor in assignment for i in actor)
        if any(type(i)!=int for i in flat) or len(set(flat))!=20 or flat in seen or any(i not in artifacts for i in flat):raise ValueError('whole finalist physical identity invalid')
        seen.add(flat)
        if row.get('iterations') not in allowed_iterations or not all(type(row.get(k)) in (int,float) and math.isfinite(row[k]) and row[k]>=0 for k in ('measured_dps','standard_error')):raise ValueError('whole ordinary fidelity/uncertainty unavailable')
        gear=[]
        for owner,actor in enumerate(assignment):
            items=[artifacts[i] for i in actor]
            if any(a['slot']!=slots[j] for j,a in enumerate(items)):raise ValueError('whole finalist slot order changed')
            counts={}
            for artifact in items:counts[artifact['set_uid']]=counts.get(artifact['set_uid'],0)+1
            gear.append({'owner':payload['wearers'][owner]['wearer_key'],'artifacts':items,'set_bonuses':[{'set_uid':key,'pieces':4 if count>=4 else 2} for key,count in sorted(counts.items()) if count>=2]})
        out.append({'measurement':row,'gear':gear})
    return out


def prepare_worker_request(request,cache_enabled,observed):
    if type(cache_enabled)!=bool:raise ValueError('explicit frozen cache boolean required')
    bounded=replace(request,product_timeout_ms=0,mechanic_cache_enabled=cache_enabled)
    observed['prepared_worker_request_cache_enabled']=bounded.mechanic_cache_enabled
    return bounded


def observe_worker_request(worker,cache_enabled,observed):
    actual=worker._session.request.mechanic_cache_enabled
    if actual is not cache_enabled:raise ValueError('actual worker request cache differs from arm policy')
    observed['worker_request_cache_enabled']=actual


ENV_KEYS=('GOMAXPROCS','GOMEMLIMIT','GOGC','GODEBUG','GOFLAGS','CGO_ENABLED','GOOS','GOARCH','GOAMD64','GOEXPERIMENT','GTT_MECHANIC_CACHE_ENABLED','GTT_C4_LINEAGE_EXPORT','GTT_C4_TRACE_CUSTODY','GTT_NEUTRAL_INTEGRITY','GTT_R1_SINGLE_NEUTRAL','GTT_WHOLE_CHASCA_COUNTERS')


def observe_launcher(original,observed,cache_enabled,parent_env):
    def launch(command,*args,**kwargs):
        values=list(map(str,command));env=kwargs.get('env')
        stage=next((name for name in ('validate-request','optimize-all-sets') if name in values),None)
        if stage is None or not isinstance(env,dict):raise ValueError('unexpected actual native launch boundary')
        actual={key:env.get(key) for key in ENV_KEYS}
        entry={'stage':stage,'environment':actual,'launched':False}
        observed.setdefault('native_launch_environments',[]).append(entry)
        if len(observed['native_launch_environments'])>4:raise ValueError('native environment observation budget exceeded')
        if actual['GTT_MECHANIC_CACHE_ENABLED']!=('1' if cache_enabled else '0') or any(actual[key]!=parent_env.get(key) for key in ENV_KEYS if key!='GTT_MECHANIC_CACHE_ENABLED'):
            raise ValueError('effective native cache/runtime environment differs from frozen arm policy')
        process=original(command,*args,**kwargs)
        entry['launched']=True
        return process
    return launch


def cache_zero_engine_checks():
    from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsRequest
    from ui.gcsim_browser.run_worker import GcsimBrowserSelectedOptimizerWorker
    tree=ast.parse(source_image())
    bounded=next(node for node in ast.walk(tree) if isinstance(node,ast.ClassDef) and node.name=='BoundedWorker')
    request=GcsimOptimizerGoAllSetsRequest(db_path='',selected_team={},team_index=0,rotation_shell_text='',mechanic_cache_enabled=True)
    old_env=os.environ.copy();cases=[]
    for policy in (False,True):
        observed={}
        namespace={'__name__':'gtt_whole_chasca_actual_worker_fixture','worker_type':GcsimBrowserSelectedOptimizerWorker,'_whole_prepare_worker_request':lambda r:prepare_worker_request(r,policy,observed),'_whole_observe_actual_worker':lambda worker:observe_worker_request(worker,policy,observed)}
        exec(compile(ast.Module(body=[bounded],type_ignores=[]),str(PARENT)+'[actual-worker-no-run]','exec'),namespace)
        with patch.dict(os.environ,{'GTT_MECHANIC_CACHE_ENABLED':'0'}):
            worker=namespace['BoundedWorker'](request)
            env=worker._session._optimizer_environment()
            assert worker._session.request.mechanic_cache_enabled is policy
            called=[];launcher=observe_launcher(lambda *a,**k:called.append(True),observed,policy,dict(os.environ))
            launcher(['consumer','validate-request','fixture.json'],env=env)
            assert called==[True] and observed['worker_request_cache_enabled'] is policy
            bad=dict(env,GTT_MECHANIC_CACHE_ENABLED='0' if policy else '1');called.clear()
            try:launcher(['consumer','optimize-all-sets','fixture.json'],env=bad)
            except ValueError:pass
            else:raise ValueError('wrong final cache environment accepted')
            assert not called
            bad_runtime=dict(env,GOMAXPROCS='unexpected-build-cap')
            try:launcher(['consumer','optimize-all-sets','fixture.json'],env=bad_runtime)
            except ValueError:pass
            else:raise ValueError('wrong final Go runtime environment accepted')
            assert not called
        cases.append({'policy':policy,'actual_worker_request':observed['worker_request_cache_enabled'],'actual_session_environment':env['GTT_MECHANIC_CACHE_ENABLED'],'bad_final_launch_rejected':True,'bad_final_go_runtime_rejected':True})
    assert os.environ==old_env
    return {'cases':cases,'native_processes_launched':0,'simulations':0}


def run_once(*,mechanic_cache_enabled,owned_job_root,producer_root,expected_engine_binding,expected_counter_mode='wall_and_counts',result_options=None,**kwargs):
    observed={}
    namespace={'__name__':'gtt_whole_chasca_button_image','__file__':str(PARENT),'_whole_prepare_worker_request':lambda request:prepare_worker_request(request,mechanic_cache_enabled,observed),'_whole_observe_actual_worker':lambda worker:observe_worker_request(worker,mechanic_cache_enabled,observed),'_whole_resolve_engine':lambda payload,scratch:resolve_bound_engine(payload,scratch,owned_job_root,producer_root,expected_engine_binding)}
    options=result_options or {'builds_per_group':2,'fast_mode':False,'set_group_limit':3}
    exec(compile(source_image(options),str(PARENT)+'[whole-chasca-frozen-options]','exec'),namespace)
    button=namespace['button']
    original=button.ArchetypeButtonHarness
    class ObservedHarness(original):
        def click_one_mode(self,*args,**options):
            started=time.monotonic()
            observed['click_started_monotonic']=started
            try:
                result=super().click_one_mode(*args,**options)
                observed['terminal']=result
                return result
            finally:
                observed['actual_click_to_terminal_or_failure_seconds']=time.monotonic()-started
    button.ArchetypeButtonHarness=ObservedHarness
    try:
        from run_workspace.gcsim import optimizer_go_session
        launcher=observe_launcher(optimizer_go_session.start_optimizer_process,observed,mechanic_cache_enabled,dict(os.environ))
        with patch.object(optimizer_go_session,'start_optimizer_process',side_effect=launcher):
            receipt=namespace['run_once'](**kwargs)
        if observed.get('worker_request_cache_enabled') is not mechanic_cache_enabled or [row['stage'] for row in observed.get('native_launch_environments',[])]!=['validate-request','optimize-all-sets']:
            raise ValueError('actual worker and both native launch observations required')
        native=Path(receipt['run_dir'])/'verification/all-sets-result.json'
        metrics=native.parent/'whole-search-counters.json'
        if not metrics.is_file():raise ValueError('whole native work counters missing')
        native_body=json.loads(native.read_bytes())
        counters=json.loads(metrics.read_bytes())
        validate_counters(counters,expected_counter_mode)
        payload=json.loads(kwargs['staged_request'].read_bytes())
        rows=measured_rows(payload,native_body)
        published=native_body.get('product_result',{}).get('candidates')
        cap=payload['result_options']['set_group_limit']*payload['result_options']['builds_per_group']
        if not isinstance(published,list) or not 1<=len(published)<=cap:raise ValueError('whole published cohort outside preserved budget')
        summary={}
        for key in ('search_seconds','source_preparation_seconds','total_elapsed_ms','search_stop_reason','capture_members','search_expansions','search_work','neutral_cycles','neutral_model','provider_timings','neutral_joint_seconds','neutral_package_joint','neutral_stabilization','rule_parse_cache','support_response'):
            value=native_body.get(key)
            summary[key]=value if len(json.dumps(value).encode())<=32<<10 else {'available_in_private_native_result':True,'transport_omitted_bytes':len(json.dumps(value).encode())}
        receipt.update(actual_click_to_terminal_seconds=observed['actual_click_to_terminal_or_failure_seconds'],
            timing_contract='Actual AppShell/worker/native/finalist/publication path. Frozen profile-to-request preparation and engine selection injected; fixture and build setup outside click timing. Parent backend wall includes readback after terminal. No physical UI/account-import timing.',
            native_counters_sha256=namespace['_sha'](metrics),native_counters=str(metrics),
            preserved_result_options=options,
            measured_builds=rows,actual_simulated_finalists=len(rows),actual_published_finalists=len(published),
            actual_selected_finalists=counters.get('Counts',{}).get('search.selected_finalists'),
            native_whole_summary=summary,actual_worker_request_cache_enabled=observed.get('worker_request_cache_enabled'),actual_native_launch_environments=observed.get('native_launch_environments',[]))
        receipt.update(native_counter_mode=counters['Mode'],native_phase_timing_contract=counters.get('Contract'),phase_timing_overhead='Lightweight wall/counter instrumentation included; nested inclusive phases must not be summed.')
        kwargs['output'].write_text(json.dumps(receipt,sort_keys=True),encoding='utf-8')
        return receipt
    except BaseException as error:
        raw={'schema':'whole_chasca_button_failure_v1','complete':False,'error_class':type(error).__name__,'error':str(error)[:4096],
            'elapsed_to_failure_seconds':observed.get('actual_click_to_terminal_or_failure_seconds'),
            'last_terminal':observed.get('terminal'),'preparation_and_engine_selection_injected':True,'actual_worker_request_cache_enabled':observed.get('worker_request_cache_enabled'),'actual_native_launch_environments':observed.get('native_launch_environments',[])}
        encoded=json.dumps(raw,sort_keys=True,default=str)
        if len(encoded.encode())>64<<10:
            raw['last_terminal']={'transport_truncated':True,'excerpt':str(observed.get('terminal'))[:24000]}
            encoded=json.dumps(raw,sort_keys=True,default=str)
        kwargs['output'].write_text(encoded,encoding='utf-8')
        raise
    finally:
        button.ArchetypeButtonHarness=original


def main():
    parser=argparse.ArgumentParser()
    for name in ('scratch','request','consumer','engine-store','output','owned-job-root','producer-root','engine-binding'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--watchdog-seconds',type=int,default=2700)
    parser.add_argument('--process-cap',type=int,default=70)
    parser.add_argument('--mechanic-cache-enabled',choices=('0','1'),required=True)
    parser.add_argument('--counter-mode',choices=('counts_only','wall_and_counts'),default='wall_and_counts')
    parser.add_argument('--builds-per-group',type=int,choices=(2,3),default=2)
    args=parser.parse_args()
    run_once(scratch=args.scratch,staged_request=args.request,consumer=args.consumer,engine_store=args.engine_store,output=args.output,watchdog_seconds=args.watchdog_seconds,process_cap=args.process_cap,mechanic_cache_enabled=args.mechanic_cache_enabled=='1',owned_job_root=args.owned_job_root,producer_root=args.producer_root,expected_engine_binding=json.loads(args.engine_binding.read_bytes()),expected_counter_mode=args.counter_mode,result_options={'set_group_limit':3,'builds_per_group':args.builds_per_group,'fast_mode':False})


if __name__=='__main__':main()
