"""One unchanged R5 Chasca Theory button observation, then human discussion."""
from __future__ import annotations

from .r5_python import install_image, ProductImageFinder, mapping, map_sha, sha
import sys
if not any(isinstance(item, ProductImageFinder) for item in sys.meta_path):
    install_image()

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from . import r5_button as r5
from .mechanic_packet_evidence import write_json

base, ROOT, OUT = r5.base, r5.ROOT, r5.OUT
CHILD = 'tools.experiments.gcsim.mvp_polish.t1_theory_button.T1TheoryButtonTest.test_one_case'
FLAGS = r5.FLAGS
HISTORY = OUT.parent / '2026-10-25-cache-team-matrix/corpus-main14-v2/chasca_600_fixture-theory/off.json'


def verify_sources(packet):
    # The sole new executable harness file is owned by the T1 source milestone.
    # All existing R5 imported helper bytes still use their exact reconstruction.
    original = r5.verify_harness_reconstruction
    def existing(files):
        return original({name:digest for name,digest in files.items()
                         if Path(name).name not in ('t1_theory_button.py','test_t1_theory_button.py')})
    with patch.object(r5,'verify_harness_reconstruction',existing):
        r5.verify_packet_sources(packet)


def preflight():
    original = r5.verify_harness_reconstruction
    def existing(files):
        return original({name:digest for name,digest in files.items()
                         if Path(name).name not in ('t1_theory_button.py','test_t1_theory_button.py')})
    with patch.object(r5,'verify_harness_reconstruction',existing):
        images,row,packet = r5.preflight()
    if map_sha(images)!='48f643c2e4c7f353806513c8e00f9f5efd31d5bfe615cdb93a038d9f84b9ae09':
        raise ValueError('T1 must use unchanged R5 native')
    if packet['r5_product_python_map_sha256']!='e3d71c217355830ca8e5cf21211a0d28fb8a924a4e53f955dfabd3bbec654569':
        raise ValueError('T1 must use unchanged R5 Python')
    packet.update(experiment='T1_Chasca_Theory_First_verified_then_Finish',mode='theory',
        result_options={},history_receipt=HISTORY.relative_to(ROOT).as_posix(),
        history_sha256=sha(HISTORY.read_bytes()),
        theory_contract={'product_timeout_ms':0,'theory_options':{},'energy':'infinite; finite unsupported',
          'owned_wire_artifacts':0,'source_inventory':[604,597,39],
          'budget':'full45 roll units per wearer, quarter grid, legal four substat lines per slot',
          'mains':'native standard legal domains; canonical neutral anchor HP/ATK/ATK%/ATK%/CR',
          'sets':'native bound complete source catalog; none/2p/4p/2+2, no supplied allowed_packages override',
          'ordinary':'existing Theory lifetime limit7,500iterations each,response reserve2; no R2 staged policy',
          'support_response':'existing separate max66 ordinary n1 calls, two-seed panel,180s lane allowance; not extra witness or R5 AllSets77 policy',
          'completion':'actual first verified first_light -> UI Finish -> terminal finished_early and worker joined',
          'captures':'one two-seed neutral universe; continuations do not recapture; count actual saved requests',
          'next':'human discussion and STOP even on success; no repair/repeat/next mode'},
        timing_scope='Existing click/adapter/progress/ordinary receipt boundaries; raw capture/model split unavailable unless saved telemetry provides it. No fabricated phase split.',
        resource_metrics='No ready process-RSS/background-CPU sampler in reused button gate; unknown. Docker untouched.')
    return images,row,packet


class T1TheoryButtonTest(unittest.TestCase):
    def test_one_case(self):
        from tests.tools import test_optimizer_archetype_button_cases as button
        from run_workspace.gcsim import optimizer_go_session as session
        from run_workspace.gcsim.optimizer_go_theory import GcsimOptimizerGoTheoryRequest
        from run_workspace.gcsim.optimizer_go_theory_session import GcsimOptimizerGoTheorySession
        packet=json.loads(Path(os.environ['GTT_T1_OWNER']).read_bytes())['packet']
        if os.environ.get('GTT_R5_IMAGE_BOOTSTRAPPED')!=packet['r5_product_python_map_sha256']:
            raise ValueError('T1 child did not load frozen R5 Python before imports')
        r5.preload_button_sources();verify_sources(packet)
        observations={'schema':'t1_theory_actual_path_v1','native_launches':[],'progress':[]}
        real_launcher=session.start_optimizer_process
        def launch(command,*args,**kwargs):
            stage=str(command[1]);env=kwargs.get('env') or {}
            if stage not in ('validate-theory-request','optimize-theory'):
                raise ValueError('T1 unexpected native stage: '+stage)
            wire=json.loads(Path(command[2]).read_bytes())
            reference=json.loads(HISTORY.read_bytes())['case']['config_join']
            if (wire['context']['prepared_config']['sha256']!=reference['prepared_config_sha256']
                or wire['context']['rotation']['sha256']!=reference['rotation_prepared_sha256']
                or wire['context']['target']['sha256']!=reference['target_sha256']
                or wire['stochastic']['seeds']!=reference['request_seed_schedule']
                or wire['artifacts']!=[] or wire.get('theory_options')!={}
                or wire['budgets']['product_timeout_ms']!=0 or wire.get('finalists') is not None):
                raise ValueError('T1 actual Theory config/settings differ from reviewed historical reference')
            if any(env.get(key)!=value for key,value in FLAGS.items()) or env.get('GTT_MECHANIC_CACHE_ENABLED')!='0':
                raise ValueError('T1 native flags/cache changed')
            observations['native_launches'].append({'stage':stage,'flags':{key:env[key] for key in FLAGS},'cache':'off'})
            return real_launcher(command,*args,**kwargs)
        with base.gate.install_child_adapter(button),ExitStack() as stack:
            real_worker=button.GcsimBrowserSelectedOptimizerWorker
            class ObservedWorker(real_worker):
                def __init__(self,request):
                    if (not isinstance(request,GcsimOptimizerGoTheoryRequest) or request.product_timeout_ms!=0
                        or request.theory_options not in (None,{}) or not request.infinite_energy_enabled):
                        raise ValueError('T1 actual Theory settings differ')
                    super().__init__(base.transport.prepare_worker_request(request,False,observations))
                    if not isinstance(self._session,GcsimOptimizerGoTheorySession):
                        raise ValueError('T1 actual worker did not use live Theory session')
                    observations['worker']={'mode':self._session.run_mode,'product_timeout_ms':request.product_timeout_ms,
                        'theory_options':request.theory_options,'infinite_energy':request.infinite_energy_enabled,
                        'seeds':list(request.seeds),'cache_enabled':self._session.request.mechanic_cache_enabled}
                    previous_callback=self._session._progress_callback
                    event_start=time.monotonic()
                    def progress(event):
                        if len(observations['progress'])<512:
                            snapshot=event.get('theory_snapshot') or {}
                            observations['progress'].append({'observed_ms':(time.monotonic()-event_start)*1000,
                                'stage':event.get('stage'),'native_elapsed_ms':event.get('elapsed_ms'),
                                'phase':snapshot.get('phase'),'verification':snapshot.get('verification'),
                                'work':snapshot.get('active_branch_work')})
                        if previous_callback is not None:previous_callback(event)
                    self._session._progress_callback=progress
            stack.enter_context(patch.object(button,'GcsimBrowserSelectedOptimizerWorker',ObservedWorker))
            stack.enter_context(patch.object(session,'start_optimizer_process',launch))
            try:
                result=unittest.TestResult()
                button.ArchetypeRealButtonExecutionTest('test_one_real_button_case').run(result)
                if not result.wasSuccessful() or result.testsRun!=1:
                    observations['test_errors']=[str(row[1])[-6000:] for row in result.errors+result.failures]
                    raise AssertionError('T1 Theory button failed; retained evidence owns diagnosis, no retry')
                if [row['stage'] for row in observations['native_launches']]!=['validate-theory-request','optimize-theory']:
                    raise ValueError('T1 native launch sequence incomplete')
            finally:
                observations.update(product_imports=r5.IMAGE.verify(),source_unchanged=True)
                verify_sources(packet)
                write_json(Path(os.environ['GTT_T1_OBSERVATIONS']),observations)


def summarize(job,arm,result,output):
    raw=job/'raw'/arm
    rows=list(raw.rglob('theory-result.json'))
    evidence={'schema':'t1_theory_result_v1','status':result.get('status'),'error_code':result.get('error_code'),
              'arm':arm,'raw_root':str(raw),'button_ms':result.get('case',{}).get('timings_ms',{}).get('button_click_to_terminal_ms'),
              'completion_label':result.get('theory_measurement_label'),'native_result_count':len(rows)}
    if len(rows)==1:
        path=rows[0];request_path=path.parent/'request.json'
        request=json.loads(request_path.read_bytes())
        product=json.loads(path.read_bytes())
        if request.get('artifacts')!=[] or request.get('theory_options')!={} or request['budgets']['product_timeout_ms']!=0:
            raise ValueError('T1 actual Theory wire/settings differ')
        evidence.update(request_sha256=base.canonical_sha256(request),result_sha256=base.gate._sha(path),
                        product=product,actual_constraints={'theory_options':request.get('theory_options'),
                        'budgets':request.get('budgets'),'legality':request.get('legality'),
                        'finalists':request.get('finalists'),'stochastic':request.get('stochastic')})
    evidence['capture_requests']=[{'path':str(path.relative_to(raw)),'request':json.loads(path.read_bytes())}
                                  for path in sorted(raw.rglob('capture-request.json'))]
    evidence['ordinary_result_files']=[str(path.relative_to(raw)) for path in sorted(raw.rglob('result.json'))]
    evidence['progress_logs']=[{'path':str(path.relative_to(raw)),'sha256':base.gate._sha(path),'bytes':path.stat().st_size}
                               for path in raw.rglob('optimizer-progress.jsonl')]
    write_json(output/(arm+'-details.json'),evidence)
    return {key:value for key,value in evidence.items() if key not in ('product','capture_requests','ordinary_result_files','progress_logs')}


def run_arm(job,output,arm,frozen,row,store,consumer,watchdog):
    owner=json.loads((output/'owner.json').read_bytes())
    if arm!='off' or owner.get('arms'):raise ValueError('T1 exactly one OFF')
    verify_sources(owner['packet'])
    bootstrap=job/'t1-python-bootstrap';bootstrap.mkdir()
    (bootstrap/'sitecustomize.py').write_bytes(r5.BOOTSTRAP.encode())
    original_env=base.gate.run_case._child_environment
    scratch=base.gate.run_case.managed_scratch
    def environment(*args,**kwargs):
        env=original_env(*args,**kwargs);env.update(FLAGS)
        env.update(GTT_R1_SINGLE_NEUTRAL='1',GTT_T1_OWNER=str(output/'owner.json'),
                   GTT_T1_OBSERVATIONS=str(output/(arm+'-observations.json')))
        env['PYTHONPATH']=os.pathsep.join(filter(None,(str(bootstrap),str(ROOT),env.get('PYTHONPATH',''))))
        for key in tuple(env):
            if key.startswith('GTT_C4_') or key in ('GTT_R5_IMAGE_BOOTSTRAPPED','GTT_WHOLE_CHASCA_COUNTERS'):
                env.pop(key,None)
        return env
    def same_snapshot(*,job,**kwargs):
        import shutil
        origin=Path(frozen['path'])
        if base.gate._sha(origin)!=frozen['sha256']:raise ValueError('T1 frozen full inventory changed')
        copied=job/'account-inventory-snapshot.db';shutil.copyfile(origin,copied)
        if base.gate._sha(copied)!=frozen['sha256']:raise ValueError('T1 inventory copy differs')
        return {**frozen,'path':copied}
    with base.retain_child_runs(job,arm,scratch) as retention,ExitStack() as stack:
        stack.enter_context(patch.object(base.gate.run_case,'managed_scratch',retention))
        stack.enter_context(patch.object(base.gate.run_case,'_child_environment',environment))
        stack.enter_context(patch.object(base.gate,'snapshot_active_inventory',same_snapshot))
        stack.enter_context(patch.object(base.gate,'CHILD_TEST',CHILD))
        stack.enter_context(patch.dict(os.environ,{base.inputs.ENV_KEY:str(job/'case.json')}))
        result=base.gate.run_one(suite_root=job,project_root=ROOT,consumer=consumer,engine_store=store,
            source_config=ROOT/row['source_config_file'],case_id=row['case_id'],mode='theory',
            cache_flag='off',cache_enabled=False,receipt_output=output/(arm+'.json'),
            lease_id=output.name+'-'+arm,test_watchdog_seconds=watchdog)
    verify_sources(owner['packet'])
    return summarize(job,arm,result,output)


def prepare(output):
    snapshot=base.gate.snapshot_active_inventory
    reference=json.loads((OUT/'r5-run-v1/owner.json').read_bytes())['inventory']
    def inventory(**kwargs):
        current=snapshot(**kwargs)
        for key in ('artifact_input_sha256','artifact_count','eligible_count','set_domain_count','profile_id_sha256'):
            if current[key]!=reference[key]:raise ValueError('T1 input differs from R5: '+key)
        return current
    with ExitStack() as stack:
        for name,value in [('preflight',preflight),('CHILD',CHILD),('run_arm',run_arm),('summarize',summarize)]:
            stack.enter_context(patch.object(base,name,value))
        stack.enter_context(patch.object(base.gate,'snapshot_active_inventory',inventory))
        base.prepare_and_wait(output)


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--action',choices=('prepare','off','release'),required=True)
    args=parser.parse_args()
    if args.action=='prepare':prepare(args.output)
    else:
        if args.action=='off':
            owner=json.loads((args.output/'owner.json').read_bytes())
            if owner.get('arms'):raise ValueError('T1 OFF already completed')
            verify_sources(owner['packet'])
        with patch.object(sys,'argv',[__file__,'--output',str(args.output),'--action',args.action]):base.main()


if __name__=='__main__':main()
