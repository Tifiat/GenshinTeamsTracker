"""Zero-engine tests of the actual button wrapper and owned directory walk."""
from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
import json
import itertools
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools import managed_optimizer_experiment as managed
from run_workspace.gcsim.optimizer_go_contracts import canonical_sha256
from run_workspace.gcsim.source_manifest_build import canonical_json
from . import whole_chasca_button as backend
from . import health_whole_chasca_v4_owner as owner


def link_directory(target,alias):
    try:os.symlink(target,alias,target_is_directory=True)
    except OSError:
        if os.name!='nt':raise
        import _winapi
        _winapi.CreateJunction(str(target),str(alias))


def unlink_directory(alias):
    if os.name=='nt':os.rmdir(alias)
    else:alias.unlink()


class WholeOwnedPaths(unittest.TestCase):
    def exercise(self,*,sibling=False,mutation=None,expected_error=None,r1=False):
        from run_workspace.gcsim import optimizer_go_session
        from tools.experiments.gcsim.mvp_polish import case_data
        from tests.tools import test_optimizer_archetype_button_cases as button
        from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsRequest
        import ui.app_shell as shell
        with managed.managed_scratch() as job:
            current=job/'job-current';scratch=current/'candidate';scratch.mkdir(parents=True)
            producer=(job/'job-previous' if sibling else current)/'engine-candidate'
            build=producer/'build';build.mkdir(parents=True)
            binary=build/'gtt-gcsim.exe';binary.write_bytes(b'identified non-executable producer fixture')
            manifest=build/'gtt-source-manifest-body.json';manifest.write_bytes(b'{\n  "fixture": true\n}\n')
            binding={'binary_path':str(binary),'artifact_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'source_manifest_sha256':hashlib.sha256(canonical_json(json.loads(manifest.read_bytes())).encode()).hexdigest(),'patch_manifest_sha256':'a'*64,'capabilities':['gtt_engine_marker']}
            binding['binding_sha256']=canonical_sha256({'kind':'gtt.standalone_engine_binding.v1',**{k:binding[k] for k in ('artifact_sha256','source_manifest_sha256','patch_manifest_sha256')}})
            consumer=scratch/'gtt-optimizer.exe';consumer.write_bytes(b'never execute consumer')
            slots=['flower','plume','sands','goblet','circlet'];actors=['alpha','beta','delta','gamma']
            artifacts=[{'artifact_id':i+1,'slot':slots[i%5],'set_uid':'fixture_'+str(i//5),'rarity':5,'level':20,'main_stat':{'key':'hp','value':'1'},'substats':[]} for i in range(20)]
            assignment=[list(range(i*5+1,i*5+6)) for i in range(4)]
            payload={'schema_kind':'gtt_gcsim_optimizer_request_v1','stochastic':{'seeds':[742031889,742031890]},'result_options':{'builds_per_group':2,'fast_mode':False,'set_group_limit':3},'engine':copy.deepcopy(binding),'artifacts':artifacts,'wearers':[{'wearer_key':x} for x in actors],'context':{'rotation':{'text':'synthetic','sha256':hashlib.sha256(b'synthetic').hexdigest()}}}
            row={'assignment':assignment,'iterations':500,'measured_dps':12345.,'standard_error':4.}
            rows=[row]
            if r1:
                payload['result_options']['builds_per_group']=3
                rows=[{**row,'assignment':[assignment[i] for i in order]}
                      for order in itertools.islice(itertools.permutations(range(4)),9)]
                row=rows[0]
            counters={'Mode':'wall_and_counts','CPUAvailable':False,'SnapshotWallNS':0,'ProjectionValueWitness':'','Counts':{'search.selected_finalists':1},'Phases':{'calibration.first_graph':{'Calls':1,'WallNS':5,'CPUNS':0,'AllocBytes':0,'Allocations':0,'GCs':0}},'Contract':'Synthetic wall-only transport; no performance claim'}
            state={'producer':producer,'binding':binding,'payload':payload,'row':row,'counters':counters,'wrong_cache':False,'alias':None}
            if mutation:mutation(state,binary,manifest,job)
            request=scratch/'request.json';request.write_text(json.dumps(payload),encoding='utf-8')
            store=job/'unused-store';store.mkdir()
            primitive=[]
            class FakeHarness:
                def __init__(self,db,team,paths):self.paths=paths
                def click_one_mode(self,mode,rotation,watchdog_ms):
                    run=Path(self.paths['run_root'])/'all_sets-synthetic';run.mkdir()
                    req=GcsimOptimizerGoAllSetsRequest(db_path='',selected_team={},team_index=0,rotation_shell_text=rotation,optimizer_binary_path=str(consumer),mechanic_cache_enabled=True)
                    worker=shell.GcsimBrowserSelectedOptimizerWorker(req)
                    prepared=optimizer_go_session.prepare_optimizer_inputs(req,run,mode='all_sets')
                    env=worker._session._optimizer_environment()
                    if state['wrong_cache']:env['GTT_MECHANIC_CACHE_ENABLED']='1'
                    for stage in ('validate-request','optimize-all-sets'):optimizer_go_session.start_optimizer_process([str(consumer),stage],env=env)
                    (run/'set-sources.json').write_text('{}',encoding='utf-8')
                    verification=run/'verification';verification.mkdir()
                    self_options=button.button_mode_policy('all_sets')
                    if r1:
                        assert self_options=={'set_group_limit':3,'builds_per_group':3,'fast_mode':False,'expanded_limits':False}
                    native={'mode':'all_sets','verification':{'candidates':rows},'product_result':{'candidates':[{'rank':i+1} for i in range(len(rows))]},'search_seconds':0.,'source_preparation_seconds':0.}
                    (verification/'all-sets-result.json').write_text(json.dumps(native),encoding='utf-8')
                    (verification/'whole-search-counters.json').write_text(json.dumps(counters),encoding='utf-8')
                    return {'success':True,'status':'success','run_dir':str(run),'request_sha256':prepared['request_sha256']}
                def shutdown_for_test(self):return True
            try:
                with patch.dict(os.environ,{'GTT_SCRATCH_DIR':str(scratch),'GTT_C4_SEARCH_PROFILE_PLAN':'synthetic-owned-plan'}),patch.object(button,'ArchetypeButtonHarness',FakeHarness),patch.object(case_data,'create_archetype_fixture',return_value=(None,{},'',{'fixture_sha256':'f'*64})) as fixture,patch.object(optimizer_go_session,'start_optimizer_process',side_effect=lambda *a,**k:primitive.append(a[0]) or SimpleNamespace()),patch('subprocess.Popen',side_effect=AssertionError('real process forbidden')):
                    call=lambda:backend.run_once(mechanic_cache_enabled=False,owned_job_root=job,producer_root=state['producer'],expected_engine_binding=binding,result_options=payload['result_options'],scratch=scratch,staged_request=request,consumer=consumer,engine_store=store,output=scratch/'result.json',watchdog_seconds=60,process_cap=70)
                    if expected_error:
                        with self.assertRaises((ValueError,FileNotFoundError)):call()
                    else:
                        result=call();self.assertTrue(result['complete']);self.assertIs(result['actual_worker_request_cache_enabled'],False);self.assertEqual(result['native_counter_mode'],'wall_and_counts');self.assertEqual(len(result['measured_builds']),len(rows));self.assertEqual(len(primitive),2)
                        self.assertEqual(result['preserved_result_options'],payload['result_options'])
                    if expected_error=='preamble':self.assertEqual(fixture.call_count,0);self.assertEqual(primitive,[])
            finally:
                if state['alias'] is not None:unlink_directory(state['alias'])

    def test_current_and_old_sibling_entire_wrapper(self):
        for sibling in (False,True):
            with self.subTest(sibling=sibling):self.exercise(sibling=sibling)

    def test_r1_three_by_three_entire_wrapper(self):
        self.exercise(sibling=True,r1=True)

    def test_preamble_rejects_artifact_source_binding_and_foreign_scope(self):
        def artifact(s,b,m,j):b.write_bytes(b'tampered')
        def source(s,b,m,j):m.write_bytes(b'tampered')
        def binding(s,b,m,j):s['payload']['engine']['binding_sha256']='0'*64
        def wrong_root(s,b,m,j):s['producer']=j/'unadmitted-producer';s['producer'].mkdir()
        def foreign_job(s,b,m,j):s['producer']=j.parent
        def alias(s,b,m,j):
            link=j/'producer-alias';link_directory(s['producer'],link);s['alias']=link;s['producer']=link
        for mutation in (artifact,source,binding,wrong_root,foreign_job,alias):
            with self.subTest(case=mutation.__name__):self.exercise(sibling=True,mutation=mutation,expected_error='preamble')

    def test_wrapper_rejects_cache_counter_and_result_corruption(self):
        def cache(s,b,m,j):s['wrong_cache']=True
        def mode(s,b,m,j):s['counters']['Mode']='counts_only'
        def cpu(s,b,m,j):s['counters']['Phases']['calibration.first_graph']['CPUNS']=1
        def count(s,b,m,j):s['counters']['Counts']['search.selected_finalists']=True
        def snapshot_type(s,b,m,j):s['counters']['SnapshotWallNS']=0.0
        def finite(s,b,m,j):s['counters']['Phases']['calibration.first_graph']['WallNS']=float('nan')
        def iterations(s,b,m,j):s['row']['iterations']=10
        def duplicate(s,b,m,j):s['row']['assignment'][3][4]=1
        for mutation in (cache,mode,cpu,count,snapshot_type,finite,iterations,duplicate):
            with self.subTest(case=mutation.__name__):self.exercise(mutation=mutation,expected_error='consumer')

    def test_linear_snapshot_totals_and_root_guard_once(self):
        with managed.managed_scratch() as job:
            path=job
            for depth in range(8):path=path/('d'+str(depth));path.mkdir();(path/'a').write_bytes(b'abc');(path/'b').write_bytes(b'12345')
            original=managed.assert_unlinked
            with patch.object(managed,'assert_unlinked',wraps=original) as guard:self.assertEqual(owner.managed_snapshot_bytes(job),64);self.assertEqual(guard.call_count,1)
            link=job/'alias'
            try:
                link_directory(path,link)
                with self.assertRaises(ValueError):owner.managed_snapshot_bytes(job)
            finally:
                if link.exists() or link.is_symlink():unlink_directory(link)

    def test_snapshot_rejects_nonregular_entry(self):
        with managed.managed_scratch() as job:
            entry=SimpleNamespace(path=str(job/'nonregular'),stat=lambda **k:SimpleNamespace(st_mode=stat.S_IFIFO,st_size=1,st_file_attributes=0))
            @contextmanager
            def scan(_):yield iter([entry])
            with patch.object(owner.os,'scandir',scan):
                with self.assertRaises(ValueError):owner.managed_snapshot_bytes(job)


if __name__=='__main__':unittest.main()
