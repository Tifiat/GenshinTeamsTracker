"""One 415d Theory button control using a relocated, pinned common adapter."""
from __future__ import annotations
import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
MAIN = Path('C:/Users/user/Desktop/GenshinTeamsTracker')
WORKER = Path('C:/Users/user/Desktop/worker2 GTT')
PACKAGE = WORKER / '.codex_tmp/t1-control-v1/app'
OUT = WORKER / 'docs/optimizer-evidence/2026-10-28-theory-control/control-v2'
HERE = 'tools/experiments/gcsim/t1_control.py'
CHILD = 'tools.experiments.gcsim.t1_control.CommonTheoryButtonTest.test_one'
OLD = '415d995c20897d13faf70217fedd37831528e6570b249b472d154b36a61f069d'
PRODUCER = 'f1e076b7fa9d292d0bab83aed9d3db0ec917437b288dcc6798cd69f4718f9b93'
PYTHON = 'e3d71c217355830ca8e5cf21211a0d28fb8a924a4e53f955dfabd3bbec654569'
sys.path.insert(0, str(ROOT))

def sha(raw): return hashlib.sha256(raw).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())
def write(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n',encoding='utf-8')

def remove_package():
    # Exact owned destination only; no parent/sibling/foreign checkout removal.
    target=PACKAGE.resolve();expected=(WORKER/'.codex_tmp/t1-control-v1/app').resolve()
    if target!=expected or PACKAGE.is_symlink():raise ValueError('unowned cleanup target')
    if PACKAGE.exists():
        from tools.managed_optimizer_experiment import assert_unlinked
        # This package is not a managed job; apply the same reparse guard before removal.
        assert_unlinked(PACKAGE)
        for item in PACKAGE.rglob('*'):assert_unlinked(item)
        shutil.rmtree(PACKAGE)

def ambient():
    return {'python':sys.version,'executable':sys.executable,'cpu_budget':os.cpu_count(),
            'pyside6':importlib.metadata.version('PySide6'),
            'environment':{k:os.environ.get(k) for k in ('GOMAXPROCS','GOMEMLIMIT','GOGC','GODEBUG','GOFLAGS')},
            'qt_platform':os.environ.get('QT_QPA_PLATFORM')}

def verify():
    if ROOT.resolve()!=PACKAGE.resolve():raise ValueError('use the prepared application runner')
    state=read(ROOT/'control.json')
    if time.time()>state['expires']:raise ValueError('prepared copy expired; release it')
    for name,digest in state['files'].items():
        if sha((ROOT/name).read_bytes())!=digest:raise ValueError('prepared file changed: '+name)
    return state

@contextmanager
def installed_identity_constant():
    # The existing gate imports this module solely for ENGINE_ID. Do not import
    # its unrelated historical build/uptake graph in a relocated ready runtime.
    name='tools.experiments.gcsim.mvp_polish.mechanic_candidate_store'
    shim=ModuleType(name)
    shim.ENGINE_ID='gcsim-v2.45.0-mechanic-compiler-20261025'
    with patch.dict(sys.modules,{name:shim}):yield

def prepare():
    if ROOT!=WORKER or PACKAGE.exists() or OUT.exists():raise ValueError('fresh owned package/output required')
    sys.path.insert(0,str(MAIN))
    from tools.experiments.gcsim.mvp_polish.r5_python import python_images, harness_baseline_images, install_image, map_sha
    images=python_images()
    if map_sha(images)!=PYTHON:raise ValueError('common product image changed')
    install_image(images)
    from tools.experiments.gcsim.mvp_polish import r1_button as old_owner
    from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context as context
    before=old_owner.preserved_state()
    PACKAGE.mkdir(parents=True);OUT.mkdir(parents=True)
    try:
        files={**images,**harness_baseline_images(),HERE:Path(__file__).read_bytes()}
        resources=['tools/experiments/gcsim/mvp_polish/case_manifest_v1.json',
                   'tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json']
        resources += [p.relative_to(MAIN).as_posix() for p in (MAIN/'localization/locales').glob('*.json')]
        resources += [p.relative_to(MAIN).as_posix() for p in (MAIN/'tools/experiments/gcsim/mode_matrix/rotations').glob('*.txt')]
        for name in resources:files[name]=(MAIN/name).read_bytes()
        historical=MAIN/'docs/optimizer-evidence/2026-10-25-cache-team-matrix'
        document=read(historical/'resolved-v2/resolved-inputs.json')
        row=next(r for r in document['rows'] if r['case_id']=='chasca_600_fixture')
        for name in [row['rotation_file'],row['source_config_file'],*[p['path'] for p in row['source_pins']]]:
            files[name]=(MAIN/name).read_bytes()
        history=read(historical/'corpus-main14-v2/chasca_600_fixture-theory/off.json')
        files['docs/optimizer-evidence/control-history.json']=json.dumps(history,sort_keys=True).encode()
        for name,raw in files.items():
            path=PACKAGE/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        binary=MAIN/'docs/optimizer-evidence/2026-10-25-mechanic-compiler/stage22-final-v1-gtt-optimizer.exe'
        if sha(binary.read_bytes())!=OLD:raise ValueError('saved 415d binary changed')
        dest=PACKAGE/'native/gcsim_optimizer/gtt-optimizer.exe';dest.parent.mkdir(parents=True);shutil.copyfile(binary,dest)
        live=old_owner.uptake._store(MAIN).root_dir;source=context(store_dir=live)
        if not source.trusted or source.artifact_sha256!=PRODUCER:raise ValueError('producer binding changed')
        store=PACKAGE/'data/gcsim/engines';engine=store/'engines'/source.engine_id
        shutil.copytree(Path(source.engine_root),engine)
        old_owner.uptake._prepare_candidate(engine)  # Existing relocation/reseal, no build.
        shutil.copyfile(live/'active_engine.json',store/'active_engine.json')
        target=context(store_dir=store)
        if not target.trusted or target.artifact_sha256!=PRODUCER:raise ValueError('relocated producer differs')
        private=PACKAGE/'private';private.mkdir()
        inventory=old_owner.gate.snapshot_active_inventory(job=private,project_root=MAIN,engine_store=live)
        reference=read(MAIN/'docs/optimizer-evidence/2026-10-27-engineering-efficiency/t1-run-v2/owner.json')['inventory']
        for key in ('artifact_input_sha256','artifact_count','eligible_count','set_domain_count','profile_id_sha256'):
            if inventory[key]!=reference[key]:raise ValueError('control input changed: '+key)
        frozen={k:str(v) if isinstance(v,Path) else v for k,v in inventory.items()}
        pins={k:sha(v) for k,v in sorted(files.items())};pins['native/gcsim_optimizer/gtt-optimizer.exe']=OLD
        state={'schema':'theory_control_prepared_v1','status':'prepared','created':time.time(),'expires':time.time()+7*86400,
               'owner':'MAIN01a1824a / ROOT01a16b30; one sidebar Luna control',
               'source_python_map':PYTHON,'source_harness_map':map_sha(harness_baseline_images()),'files':pins,
               'consumer':OLD,'producer':PRODUCER,'producer_binding':target.binding_sha256,
               'row':row,'inventory':frozen,'ambient_prepare':ambient(),'historical_python_identity':'unknown',
               'main_protected_before':before,'evidence':str(OUT),
               'cleanup':'per-run managed scratch auto-cleanup; retained baseline --action release, expires7days'}
        if old_owner.preserved_state()!=before:raise ValueError('MAIN protected state changed during prepare')
        write(PACKAGE/'control.json',state);write(OUT/'registry.json',state)
        print(json.dumps({'status':'prepared','package':str(PACKAGE),'engine_calls':0}),flush=True)
    except BaseException:
        remove_package();raise

@contextmanager
def callback_errors(button):
    original=button.ArchetypeButtonHarness.click_one_mode
    def click(harness,*args,**kwargs):
        failures=[];events=button._APP.processEvents
        def capture(kind,error,tb):
            if not failures:failures.append((error,tb))
        def pump(*args,**kwargs):
            events(*args,**kwargs)
            if failures:
                error,tb=failures[0];raise error.with_traceback(tb)
        try:
            with patch.object(sys,'excepthook',capture),patch.object(button._APP,'processEvents',pump):
                return original(harness,*args,**kwargs)
        finally:failures.clear()
    with patch.object(button.ArchetypeButtonHarness,'click_one_mode',click):yield

class CommonTheoryButtonTest(unittest.TestCase):
    def test_one(self):
        state=verify()
        from tools.experiments.gcsim.mvp_polish import mechanic_button_gate as gate
        from tests.tools import test_optimizer_archetype_button_cases as button
        from run_workspace.gcsim import optimizer_go_session as session
        reference=read(ROOT/'docs/optimizer-evidence/control-history.json')['case']['config_join']
        observed={'ambient':ambient(),'launches':[]};launcher=session.start_optimizer_process
        def launch(command,*args,**kwargs):
            stage=str(command[1]);wire=read(command[2]);env=kwargs['env']
            if stage not in ('validate-theory-request','optimize-theory'):raise ValueError('unexpected native command')
            if any(wire['context'][part]['sha256']!=reference[key] for part,key in
                   [('prepared_config','prepared_config_sha256'),('rotation','rotation_prepared_sha256'),('target','target_sha256')]):
                raise ValueError('historical config/rotation/target drift')
            if (wire['artifacts']!=[] or wire.get('theory_options')!={} or wire['budgets']['product_timeout_ms']!=0
                or wire['stochastic']['seeds']!=[742031889,742031890] or env['GTT_MECHANIC_CACHE_ENABLED']!='0'):
                raise ValueError('Theory settings drift')
            observed['launches'].append({'stage':stage,'environment':{k:env.get(k) for k in
                ('GOMAXPROCS','GOMEMLIMIT','GOGC','GODEBUG','GTT_MECHANIC_CACHE_ENABLED','GTT_R1_SINGLE_NEUTRAL')},
                'experiment_flags':{k:v for k,v in env.items() if k.startswith(('GTT_R3_','GTT_R4_','GTT_C4_'))}})
            return launcher(command,*args,**kwargs)
        with gate.install_child_adapter(button),callback_errors(button),patch.object(session,'start_optimizer_process',launch):
            result=unittest.TestResult()
            finalize=button._finalize_test_harness
            def export_before_cleanup(**kwargs):
                joined=finalize(**kwargs)
                runs=Path(os.environ['GTT_MVP_POLISH_RUN_ROOT'])
                paths=list(runs.rglob('theory-result.json'))
                if len(paths)==1:
                    native=read(paths[0]);native['unavailable_count']=len(native.pop('unavailable',[]))
                    observed['native']=native
                observed['counts']={'captures':len(list(runs.rglob('capture-request.json'))),
                    'stat_response_results':sum('stat-response-' in str(p) for p in runs.rglob('result.json')),
                    'ordinary_results':sum('ordinary-' in str(p) for p in runs.rglob('result.json'))}
                return joined
            try:
                with patch.object(button,'_finalize_test_harness',export_before_cleanup):
                    button.ArchetypeRealButtonExecutionTest('test_one_real_button_case').run(result)
                if not result.wasSuccessful() or result.testsRun!=1:raise AssertionError('one control button failed; no retry')
            finally:write(Path(os.environ['GTT_THEORY_CONTROL_OBSERVATIONS']),observed)

def check():
    state=verify()
    from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context as context
    from tools.experiments.gcsim.mvp_polish import mechanic_button_gate as gate
    from tests.tools import test_optimizer_archetype_button_cases as button
    from run_workspace.gcsim.optimizer_go_theory import GcsimOptimizerGoTheoryRequest
    store=ROOT/'data/gcsim/engines'
    target=context(store_dir=store)
    if not target.trusted or target.artifact_sha256!=PRODUCER:raise ValueError('producer preflight failed')
    from tools.managed_optimizer_experiment import managed_scratch
    with managed_scratch() as job:
        write(job/'case.json',state['row'])
        env={'GTT_MECHANIC_CORPUS_INPUT':str(job/'case.json'),'GTT_REAL_INVENTORY_SNAPSHOT':state['inventory']['path'],
             'GTT_MECHANIC_SNAPSHOT_SHA256':state['inventory']['sha256'],
             'GTT_MECHANIC_EXPECTED_TOTAL':'604','GTT_MECHANIC_EXPECTED_ELIGIBLE':'597','GTT_MECHANIC_EXPECTED_SETS':'39',
             'GTT_REAL_TEAM_SOURCE_CONFIG':str(ROOT/state['row']['source_config_file']),
             'GTT_MECHANIC_NATIVE_LOG_DIR':str(job/'native'),'GTT_MECHANIC_TEST_CACHE_ENABLED':'0'}
        with patch.dict(os.environ,env),gate.install_child_adapter(button), \
             patch('subprocess.Popen',side_effect=AssertionError('fixture check cannot launch an engine')):
            case=gate.run_case.load_case('chasca_600_fixture')
            db,team,rotation,metadata,admission=button._create_admitted_fixture(job/'fixture',case,store_dir=store)
            if metadata['artifact_domain_count']!=604 or metadata['set_domain_count']!=39:
                raise ValueError('full snapshot fixture mismatch')
            sentinel=button.GcsimBrowserSelectedOptimizerWorker(GcsimOptimizerGoTheoryRequest('unused',{},1,''))
            if sentinel._session.request.product_timeout_ms!=0:raise ValueError('sentinel was not normalized')
    with patch('subprocess.Popen',side_effect=AssertionError('checks cannot launch an engine')):
        worker=button.GcsimBrowserSelectedOptimizerWorker(GcsimOptimizerGoTheoryRequest('unused',{},0,''))
        if worker._session.request.product_timeout_ms!=0 or worker._session.run_mode!='theory':raise ValueError('worker mismatch')
        button.ArchetypeCaseDataTests('test_theory_first_verified_snapshot_uses_reader_thread_and_actual_finish_route').debug()
    write(OUT/'checks.json',{'status':'passed','engine_calls':0,'checks':['package source hashes','producer trusted f1e',
          'actual Chasca full604/597/39 admitted fixture','actual adapter sentinel1 -> timeout0',
          'Theory worker timeout0','synthetic reader-thread verified publication -> Finish/join'],
          'rotation_sha256':case.rotation_sha256,'ambient':ambient(),'check_job_removed':not job.exists(),
          'retained_baseline_present':PACKAGE.exists()})
    print('PASS: package, producer, saved case, worker and synthetic Finish; zero engine calls')

def run():
    state=verify()
    if read(OUT/'registry.json')['status']!='prepared':raise ValueError('one control attempt only')
    state['status']='running';state['ambient_run']=ambient();write(OUT/'registry.json',state)
    from tools.experiments.gcsim.mvp_polish import mechanic_button_gate as gate
    from tools.managed_optimizer_experiment import managed_scratch
    def snapshot(*,job,**kwargs):
        original=Path(state['inventory']['path'])
        if sha(original.read_bytes())!=state['inventory']['sha256']:raise ValueError('owned inventory changed')
        copied=job/'account-inventory-snapshot.db';shutil.copyfile(original,copied)
        return {**state['inventory'],'path':copied}
    original_env=gate.run_case._child_environment
    def environment(*args,**kwargs):
        env=original_env(*args,**kwargs)
        for key in tuple(env):
            if key.startswith(('GTT_R1_','GTT_R3_','GTT_R4_','GTT_C4_','GTT_WHOLE_')):env.pop(key,None)
        # Observe ambient Go/GC settings rather than silently replacing them.
        env['GTT_THEORY_CONTROL_OBSERVATIONS']=str(ROOT/'docs/optimizer-evidence/control-child.json')
        return env
    receipt=ROOT/'docs/optimizer-evidence/control-off.json'
    try:
        with managed_scratch() as job,ExitStack() as stack,installed_identity_constant():
            write(job/'case.json',state['row'])
            stack.enter_context(patch.dict(os.environ,{'GTT_MECHANIC_CORPUS_INPUT':str(job/'case.json')}))
            stack.enter_context(patch.object(gate,'snapshot_active_inventory',snapshot))
            stack.enter_context(patch.object(gate,'CHILD_TEST',CHILD))
            stack.enter_context(patch.object(gate.run_case,'PROJECT_PYTHON',Path(sys.executable)))
            stack.enter_context(patch.object(gate.run_case,'_child_environment',environment))
            result=gate.run_one(suite_root=job,project_root=ROOT,
                consumer=ROOT/'native/gcsim_optimizer/gtt-optimizer.exe',engine_store=ROOT/'data/gcsim/engines',
                source_config=ROOT/state['row']['source_config_file'],case_id='chasca_600_fixture',mode='theory',
                cache_flag='off',cache_enabled=False,receipt_output=receipt,lease_id='theory-415d-common-adapter-v2',
                test_watchdog_seconds=1200,installed_runtime=True)
            write(OUT/'off.json',result)
        state.update(status='complete',result_status=result.get('status'),job_removed=not job.exists())
    except BaseException as error:
        state.update(status='failed',error_class=type(error).__name__,job_removed=not job.exists() if 'job' in locals() else None)
        write(OUT/'failure.json',{'status':'failed','phase':'parent/bootstrap or button',
              'error_class':type(error).__name__,'job_removed':state['job_removed']})
        if receipt.exists():shutil.copyfile(receipt,OUT/'off.json')
        raise
    finally:
        child=ROOT/'docs/optimizer-evidence/control-child.json'
        if child.exists():
            observed=read(child)
            if 'native' in observed:write(OUT/'native.json',observed.pop('native'))
            if 'counts' in observed:write(OUT/'counts.json',observed.pop('counts'))
            write(OUT/'observations.json',observed)
        child.unlink(missing_ok=True)
        receipt.unlink(missing_ok=True)
        state['main_protected_after_match']=all((sha(Path(p).read_bytes()) if Path(p).is_file() else None)==digest
            for p,digest in state['main_protected_before']['files'].items())
        state['package_retained']=PACKAGE.exists();write(OUT/'registry.json',state)
    if result.get('status')!='success':raise SystemExit(2)

def bootstrap_check():
    """Same parent + child test path, with every actual Popen forbidden."""
    state=verify()
    from tools.experiments.gcsim.mvp_polish import mechanic_button_gate as gate
    from run_workspace.gcsim import optimizer_go_session as session
    stages=[];children=[]
    def boundary(command,*args,**kwargs):
        stages.append(str(command[1]))
        raise RuntimeError('expected zero-engine bootstrap boundary')
    def child(command,**kwargs):
        if command[-1]!=CHILD:raise AssertionError('unexpected child command')
        result=unittest.TestResult()
        with patch.dict(os.environ,kwargs['env']):CommonTheoryButtonTest('test_one').run(result)
        children.append({'tests':result.testsRun,'errors':len(result.errors),'failures':len(result.failures)})
        return SimpleNamespace(wait=lambda timeout:1,poll=lambda:1)
    with tempfile.TemporaryDirectory(prefix='bootstrap-check-',dir=OUT) as directory:
        temporary=Path(directory);write(temporary/'registry.json',state)
        with patch.dict(globals(),OUT=temporary), \
             patch.object(gate.run_case,'start_optimizer_process',child), \
             patch.object(session,'start_optimizer_process',boundary), \
             patch('subprocess.Popen',side_effect=AssertionError('bootstrap check forbids every real process')) as popen:
            try:run()
            except SystemExit as stop:
                if stop.code!=2:raise
            summary=read(temporary/'off.json')
            joined=summary['case']['process_guard']['worker_thread_joined']
            if stages!=['validate-theory-request'] or not joined:raise AssertionError('bootstrap did not reach joined native boundary: '+str(stages))
            if 'tools.experiments.gcsim.mvp_polish.health_unified_uptake_run' in sys.modules:
                raise AssertionError('legacy build graph was imported')
            popen.assert_not_called()
            receipt={'status':'passed','engine_calls':0,'actual_Popen_calls':0,'native_boundaries':stages,
                     'parent_run_one':True,'actual_child_bootstrap_in_process':True,'worker_joined':joined,
                     'expected_failed_case_code':summary['case']['errors']['code'],'children':children,
                     'scratch_removed':read(temporary/'registry.json')['job_removed'],
                     'baseline_retained':PACKAGE.exists()}
    write(OUT/'bootstrap-check.json',receipt)
    print(json.dumps(receipt),flush=True)

def main():
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--action',choices=('prepare','check','bootstrap','run','release'),required=True)
    action=parser.parse_args().action
    if action=='prepare':prepare()
    elif action=='check':check()
    elif action=='bootstrap':bootstrap_check()
    elif action=='run':run()
    else:
        remove_package()
        if (OUT/'registry.json').exists():
            state=read(OUT/'registry.json');state.update(status='released',package_removed=True);write(OUT/'registry.json',state)

if __name__=='__main__':main()
