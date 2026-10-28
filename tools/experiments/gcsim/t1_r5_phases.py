"""Coarse-only Theory timing overlay over exact R5; one ROOT-dispatched run."""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
WORKER=Path('C:/Users/user/Desktop/worker3 GTT')
MAIN=Path('C:/Users/user/Desktop/GenshinTeamsTracker')
CONTROL=Path('C:/Users/user/Desktop/worker2 GTT/.codex_tmp/t1-control-v1/app')
PACKAGE=WORKER/'.codex_tmp/t1-control-v1/app'
OUT=WORKER/'docs/optimizer-evidence/2026-10-28-theory-phases/r5-v1'
HERE='tools/experiments/gcsim/t1_r5_phases.py'
HELPERS='tools/experiments/gcsim/theory_phases'
CHILD='tools.experiments.gcsim.t1_r5_phases.TimedTheoryButtonTest.test_one'
BASE='48f643c2e4c7f353806513c8e00f9f5efd31d5bfe615cdb93a038d9f84b9ae09'
FLAGS={k:'1' for k in ('GTT_R1_SINGLE_NEUTRAL','GTT_R3_PARALLEL_CAPTURE','GTT_R3_TYPED_CANONICAL',
 'GTT_R3_ADJOINT_REUSE','GTT_R3_PROGRAM_IDENTITY','GTT_R3_OPERATION_SWITCH',
 'GTT_R4_FAST_COUNTERS','GTT_R4_OWNED_DIGEST','GTT_R4_TYPED_PANEL')}
sys.path.insert(0,str(ROOT))
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def write(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n',encoding='utf-8')
def once(text,old,new):
 if text.count(old)!=1:raise ValueError('R5 timing seam changed: '+old[:80])
 return text.replace(old,new,1)

def overlay(base,helpers):
 out=dict(base);name='cmd/gtt-optimizer/theory_session.go';s=out[name].decode()
 s=once(s,'progress := newProgressEmitter(os.Stderr, requestSHA)','''progress := newProgressEmitter(os.Stderr, requestSHA)
 coarse := &theoryCoarse{started:time.Now(),root:runRoot,Stats:map[string]setcontext.NeutralModelStats{}}
 defer func(){_ = coarse.save()}()
 searchCtx = context.WithValue(searchCtx,theoryCoarseKey{},coarse)
 searchCtx = theorysearch.WithFirstCheckpointTiming(searchCtx,func(d time.Duration){
  if len(coarse.Spans)<32 {coarse.Spans=append(coarse.Spans,theoryCoarseSpan{"checkpoint_fork","first",time.Since(coarse.started).Nanoseconds()-d.Nanoseconds(),d.Nanoseconds()})} else {coarse.Dropped++}
 })
 stopSetup := coarse.begin("context_setup","")''')
 s=once(s,'captured, err := capturedSession.Resolve(searchCtx, base, nil, nil)',
        'stopSetup()\n stopCapture := coarse.begin("capture","")\n captured, err := capturedSession.Resolve(searchCtx, base, nil, nil)\n stopCapture()')
 s=once(s,'model, err := setcontext.NewNeutralModel(captured, sources)',
        'stopModel := coarse.begin("model","")\n model, err := setcontext.NewNeutralModel(captured, sources)\n stopModel()')
 s=once(s,'cfg, err = theorySessionConfig(raw, req, sources, requestSHA, sourceSHA, captured.GraphSHA256(), cfg.SessionID)',
        'stopWorld := coarse.begin("config_world","")\n cfg, err = theorySessionConfig(raw, req, sources, requestSHA, sourceSHA, captured.GraphSHA256(), cfg.SessionID)')
 s=once(s,'// A configured common response producer scores its legal proposals through',
        'stopWorld()\n coarse.snapshot("main_initial",model.Stats())\n // A configured common response producer scores its legal proposals through')
 s=once(s,'fork, err = world.Fork()','stopFork := coarse.begin("response_world_fork","")\n fork, err = world.Fork()\n stopFork()')
 s=once(s,'offerResponses := func() error {','''offerResponses := func() error {
  stopOffer := coarse.begin("offer_response",""); defer stopOffer()
  if proposalWorld!=nil {coarse.snapshot("response_before_offer",proposalWorld.CoarseModelStats());defer func(){coarse.snapshot("response_after_offer",proposalWorld.CoarseModelStats())}()}''')
 s=once(s,'func() error { return verified.OfferSearch(snapshot) }',
        'func() error { stopOffer:=coarse.begin("offer_search","");defer stopOffer();return verified.OfferSearch(snapshot) }')
 s=once(s,'return verified.Verify(searchCtx, raw, snapshot, terminal, renderer, runRoot, runtime.NumCPU(), checkBinding, progress.theorySnapshot, nil)',
        'stopVerify:=coarse.begin("verify","");defer stopVerify()\n return verified.Verify(searchCtx, raw, snapshot, terminal, renderer, runRoot, runtime.NumCPU(), checkBinding, progress.theorySnapshot, nil)')
 s=once(s,'initialMechanic, initialMechanicErr := world.ResolveMechanics(searchCtx, cfg.Original)',
        'stopInitial:=coarse.begin("initial_resolve_binding","")\n initialMechanic, initialMechanicErr := world.ResolveMechanics(searchCtx, cfg.Original)')
 s=once(s,'snapshot, err := session.First(searchCtx, cfg.Binding)',
        'stopInitial()\n stopFirst:=coarse.begin("first","")\n snapshot, err := session.First(searchCtx, cfg.Binding)\n stopFirst()\n coarse.snapshot("main_after_first",model.Stats())')
 out[name]=s.encode()
 name='cmd/gtt-optimizer/theory_support_response.go';s=out[name].decode()
 s=once(s,'check, err := run(ctx, request, coverage, anchor.Config.Text, runRoot,',
        'stopProbe:=theoryCoarseBegin(ctx,"support_probes","offer_response")\n check, err := run(ctx, request, coverage, anchor.Config.Text, runRoot,')
 s=once(s,'out.Status = check.Status','stopProbe()\n out.Status = check.Status');out[name]=s.encode()
 name='internal/theorysearch/session.go';s=out[name].decode()
 s=once(s,'checkpoint, err := s.active.fork()',
        'stopCheckpoint:=firstCheckpointTiming(ctx)\n checkpoint, err := s.active.fork()\n stopCheckpoint()');out[name]=s.encode()
 out['internal/theorysearch/coarse_stats.go']=b'''package theorysearch
import "genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
func(w *FormulaWorld) CoarseModelStats() setcontext.NeutralModelStats{return w.model.Stats()}
'''
 for source,dest in [('coarse.go.txt','cmd/gtt-optimizer/theory_coarse.go'),('coarse_test.go.txt','cmd/gtt-optimizer/theory_coarse_test.go'),
                     ('checkpoint.go.txt','internal/theorysearch/coarse_checkpoint.go'),('checkpoint_test.go.txt','internal/theorysearch/coarse_checkpoint_test.go')]:
  out[dest]=helpers[source]
 return out

def prepare():
 if ROOT!=WORKER or PACKAGE.exists() or OUT.exists():raise ValueError('fresh owned R5 package required')
 control=read(CONTROL/'control.json')
 if control['files']['tools/experiments/gcsim/t1_control.py']!='c9e893a3192068838577a9563abb59d09087fec6d13aaf2fc3ddfceb39cdd244':raise ValueError('common adapter differs from control-v2')
 for name,digest in control['files'].items():
  if sha((CONTROL/name).read_bytes())!=digest:raise ValueError('retained control changed: '+name)
 sys.path.insert(0,str(MAIN))
 from tools.experiments.gcsim.mvp_polish.r5_redundant import native_images
 from tools.experiments.gcsim.mvp_polish.r3_recovery import map_sha,mapping
 from tools.experiments.gcsim.mvp_polish import whole_chasca_target as target
 from tools.experiments.gcsim.mvp_polish.r5_python import install_image
 install_image()
 from tools.managed_optimizer_experiment import managed_scratch
 base=native_images()
 if map_sha(base)!=BASE:raise ValueError('not exact R5 source')
 helpers={p.name:p.read_bytes() for p in (WORKER/HELPERS).glob('*.go.txt')}
 candidate=overlay(base,helpers)
 OUT.mkdir(parents=True);shutil.copytree(CONTROL,PACKAGE,ignore=shutil.ignore_patterns('__pycache__'))
 try:
  from tools.experiments.gcsim.mvp_polish.mechanic_uptake import _prepare_candidate
  from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context as context
  store=PACKAGE/'data/gcsim/engines';engine=store/'engines/gcsim-v2.45.0-mechanic-compiler-20261025'
  _prepare_candidate(engine)
  producer=context(store_dir=store)
  if not producer.trusted or producer.artifact_sha256!=control['producer']:raise ValueError('relocated producer changed')
  delta=[]
  for name,raw in candidate.items():
   if base.get(name)==raw:continue
   delta.extend(difflib.unified_diff(base.get(name,b'').decode().splitlines(True),raw.decode().splitlines(True),fromfile='a/'+name,tofile='b/'+name))
  (OUT/'native-timing.patch').write_text(''.join(delta),encoding='utf-8')
  source={'base_map':BASE,'candidate_map':map_sha(candidate),'base_files':mapping(base),'candidate_files':mapping(candidate),
          'changed_files':[name for name in candidate if base.get(name)!=candidate[name]],'delta_sha256':sha((OUT/'native-timing.patch').read_bytes()),
          'policy':'unchanged R5/T1 flags, search, frozen policy, budgets; coarse spans + existing stats only'}
  write(OUT/'source.json',source)
  go=Path('C:/Program Files/Go/bin/go.exe');snapshot=read(MAIN/'docs/optimizer-evidence/2026-10-26-response-pilot/whole-search-chasca-v3-target-snapshot.json')
  with managed_scratch(root=PACKAGE/'.codex_tmp/managed-optimizer') as job:
   module=job/'native';module.mkdir()
   for name,raw in candidate.items():
    p=module/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
   temp=job/'temp';temp.mkdir()
   env=dict(os.environ,GOTOOLCHAIN='local',GOMAXPROCS='2',GOMEMLIMIT='2GiB',GOFLAGS='-p=2 -mod=readonly',
            GOCACHE=str(job/'go-cache'),GOTMPDIR=str(temp),TMP=str(temp),TEMP=str(temp))
   env=target.pin_target(env,snapshot)
   commands=[('focused-tests',[str(go),'-C',str(module),'test','-count=1','-run','^TestTheoryCoarse','./cmd/gtt-optimizer','./internal/theorysearch']),
             ('build',[str(go),'-C',str(module),'build','-trimpath','-buildvcs=false','-o',str(PACKAGE/'native/gcsim_optimizer/gtt-optimizer.exe'),'./cmd/gtt-optimizer'])]
   for label,command in commands:
    started=time.monotonic()
    with (OUT/(label+'.log')).open('w',encoding='utf-8') as log:
     subprocess.run(command,cwd=PACKAGE,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
    source[label+'_seconds']=time.monotonic()-started
   source['target']=target.assert_binary_target(snapshot,target.inspect_binary(go,PACKAGE/'native/gcsim_optimizer/gtt-optimizer.exe',env,PACKAGE))
  source['build_job_removed']=not job.exists();write(OUT/'source.json',source)
  shutil.copyfile(WORKER/HERE,PACKAGE/HERE)
  state=dict(control);state.update(status='prepared',attempt='r5-phases-v1',evidence=str(OUT),
      consumer=sha((PACKAGE/'native/gcsim_optimizer/gtt-optimizer.exe').read_bytes()),source_native_base=BASE,
      source_native_timed=source['candidate_map'],producer_binding=producer.binding_sha256,flags=FLAGS,
      created=time.time(),expires=time.time()+7*86400,owner='MAIN01a1824a / ROOT01a16b30; one Luna instrumented R5')
  state['inventory']=dict(control['inventory']);state['inventory']['path']=str(PACKAGE/Path(control['inventory']['path']).relative_to(CONTROL))
  state['files']=dict(control['files']);state['files'][HERE]=sha((PACKAGE/HERE).read_bytes());state['files']['native/gcsim_optimizer/gtt-optimizer.exe']=state['consumer']
  write(PACKAGE/'control.json',state);write(OUT/'registry.json',state)
  print(json.dumps({'status':'prepared','consumer':state['consumer'],'source_map':source['candidate_map'],'engine_calls':0}),flush=True)
 except BaseException as error:
  write(OUT/'prepare-failure.json',{'status':'failed','error_class':type(error).__name__})
  from tools.managed_optimizer_experiment import assert_unlinked
  if PACKAGE.resolve()!=(WORKER/'.codex_tmp/t1-control-v1/app').resolve():raise ValueError('unowned preparation cleanup')
  assert_unlinked(PACKAGE)
  for p in PACKAGE.rglob('*'):assert_unlinked(p)
  shutil.rmtree(PACKAGE)
  raise

def configured(stack):
 from tools.experiments.gcsim import t1_control as common
 from tools.experiments.gcsim.mvp_polish import mechanic_button_gate as gate
 state=read(ROOT/'control.json')
 for key,value in [('WORKER',WORKER),('PACKAGE',PACKAGE),('OUT',OUT),('CHILD',CHILD)]:stack.enter_context(patch.object(common,key,value))
 stack.enter_context(patch.object(gate,'INSTALLED_CONSUMER_SHA256',state['consumer']))
 original=gate.run_case.run_managed_case
 def managed(*args,**kwargs):
  environment=gate.run_case._child_environment
  def flags(*args,**kwargs):
   env=environment(*args,**kwargs);env.update(FLAGS);return env
  with patch.object(gate.run_case,'_child_environment',flags):return original(*args,**kwargs)
 stack.enter_context(patch.object(gate.run_case,'run_managed_case',managed))
 return common

class TimedTheoryButtonTest(unittest.TestCase):
 def test_one(self):
  with ExitStack() as stack:
   common=configured(stack)
   from tests.tools import test_optimizer_archetype_button_cases as button
   from run_workspace.gcsim import optimizer_go_session as session
   original=button._finalize_test_harness;launcher=session.start_optimizer_process
   def finalize(**kwargs):
    joined=original(**kwargs);paths=list(Path(os.environ['GTT_MVP_POLISH_RUN_ROOT']).rglob('theory-coarse-timings.json'))
    if len(paths)==1:write(ROOT/'docs/optimizer-evidence/r5-phases.json',read(paths[0]))
    return joined
   def launch(command,*args,**kwargs):
    if any(kwargs['env'].get(k)!=v for k,v in FLAGS.items()):raise ValueError('R5 T1 flags changed')
    return launcher(command,*args,**kwargs)
   stack.enter_context(patch.object(button,'_finalize_test_harness',finalize))
   stack.enter_context(patch.object(session,'start_optimizer_process',launch))
   common.CommonTheoryButtonTest('test_one').debug()

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--action',choices=('prepare','bootstrap','run','release'),required=True);action=p.parse_args().action
 if action=='prepare':prepare();return
 with ExitStack() as stack:
  common=configured(stack)
  if action=='bootstrap':
   saved=common.write;launches=[]
   def observe(path,value):
    if Path(path).name=='observations.json':launches.extend(value.get('launches',[]))
    saved(path,value)
   with patch.object(common,'write',observe):common.bootstrap_check()
   if len(launches)!=1:raise ValueError('bootstrap native boundary count changed')
   actual={**launches[0]['environment'],**launches[0]['experiment_flags']}
   if any(actual.get(k)!=v for k,v in FLAGS.items()):raise ValueError('bootstrap R5 flags differ from T1v2')
   result=read(OUT/'bootstrap-check.json');result['actual_native_environment']=actual
   result['exact_T1v2_flags']=True;write(OUT/'bootstrap-check.json',result)
  elif action=='release':
   state=read(ROOT/'control.json');common.remove_package()
   state.update(status='released',package_removed=True);write(OUT/'registry.json',state)
  else:
   evidence_status='missing'
   try:common.run()
   finally:
    path=ROOT/'docs/optimizer-evidence/r5-phases.json'
    detail={'status':'missing','error_code':'theory_coarse_evidence_missing'}
    if path.exists():
     phases=read(path);write(OUT/'phases.json',phases);path.unlink()
     required={'context_setup','capture','model','config_world','response_world_fork','initial_resolve_binding',
               'first','checkpoint_fork','offer_search','offer_response','support_probes','verify'}
     names={p['name'] for p in phases.get('spans',[])}
     valid=phases.get('schema')=='theory_coarse_phases_v1' and phases.get('dropped')==0 and required<=names
     evidence_status='available' if valid else 'incomplete'
     detail={'status':evidence_status,'path':'phases.json','sha256':sha((OUT/'phases.json').read_bytes()),
             'missing_spans':sorted(required-names),'error_code':None if valid else 'theory_coarse_evidence_incomplete'}
    if (OUT/'off.json').exists():
     receipt=read(OUT/'off.json');receipt['theory_coarse_evidence']=detail;write(OUT/'off.json',receipt)
    if (OUT/'registry.json').exists():
     state=read(OUT/'registry.json');state['diagnostic_evidence']=detail;write(OUT/'registry.json',state)
   if evidence_status!='available':raise SystemExit(2)

if __name__=='__main__':main()
