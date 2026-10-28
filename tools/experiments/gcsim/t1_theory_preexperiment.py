"""Prepare/collect one bounded rule-preparation diagnosis; never a search run."""
from contextlib import ExitStack
import difflib
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tools.experiments.gcsim import t1_r5_phases as phases
from tools.experiments.gcsim.theory_phases.bookkeeping import change
from tools.experiments.gcsim.theory_phases import preexperiment_saved as saved
WORKER,MAIN,PACKAGE,OUT=phases.WORKER,phases.MAIN,phases.PACKAGE,saved.OUT
VARIANT=PACKAGE/'private/variants/theory-preexperiment-v1'
HERE='tools/experiments/gcsim/t1_theory_preexperiment.py'
sha,read,write=phases.sha,phases.read,phases.write
BASE='8848afb8ed0a44600d1d5d3b80a7b29d2a1996569ce06240ec77afcf4682d3dd'

def overlay(base,helpers):
 out=dict(base)
 def edit(name,old,new):out[name]=phases.once(out[name].decode('utf-8'),old,new).encode('utf-8')
 edit('internal/seteffects/neutral_binding.go','type NeutralBinding struct {','type NeutralBinding struct {\n preparationDiagnostic *PreparationDiagnostic')
 edit('internal/seteffects/neutral_binding.go','"strconv"','"strconv"\n "time"')
 edit('internal/seteffects/r1_frozen_neutral.go','concrete NeutralEffectVector) NeutralExpressions {',
  'concrete NeutralEffectVector) NeutralExpressions {\n freezeConcreteDone:=b.preparationFreezeStarted(choices);defer freezeConcreteDone()')
 edit('internal/seteffects/r1_frozen_neutral.go','b.r1Stats.AnchorPorts++','b.r1Stats.AnchorPorts++\n b.preparationFrozenPort(member.seed,port.query,true)')
 edit('internal/seteffects/r1_frozen_neutral.go','b.r1Stats.ReferencePorts++','b.r1Stats.ReferencePorts++\n b.preparationFrozenPort(member.seed,port.query,false)')
 edit('internal/seteffects/neutral_binding.go','r := b.catalog.replayNeutralRulesBound(member.neutral, choices, queries, false, order, member.worldCache)',
  'replayStarted:=time.Now()\n r := b.catalog.replayNeutralRulesBound(member.neutral, choices, queries, false, order, member.worldCache)\n b.preparationReplayObserved(choices,member,false,r,time.Since(replayStarted).Seconds())')
 edit('internal/seteffects/neutral_expressions.go','started := time.Now()','observeJoint:=b.preparationJointStarted(choices)\n started := time.Now()')
 edit('internal/seteffects/neutral_expressions.go','replay := b.catalog.replayNeutralRulesBound(member.neutral, choices, queries, true, order, member.worldCache)',
  'replayStarted:=time.Now()\n replay := b.catalog.replayNeutralRulesBound(member.neutral, choices, queries, true, order, member.worldCache)\n b.preparationReplayObserved(choices,member,true,replay,time.Since(replayStarted).Seconds())')
 edit('internal/seteffects/neutral_expressions.go','return b.r1Freeze(choices,out)','freezeObserve:=0.0;if b.preparationDiagnostic!=nil{freezeObserve=b.preparationDiagnostic.ObserverSeconds}\n freezeStarted:=time.Now()\n after:=b.r1Freeze(choices,out)\n freezeSeconds:=time.Since(freezeStarted).Seconds()\n if b.preparationDiagnostic!=nil{freezeObserve=b.preparationDiagnostic.ObserverSeconds-freezeObserve}\n observeJoint(out,after,freezeSeconds,freezeObserve)\n return after')
 edit('internal/seteffects/rule_replay.go','"strings"','"strings"\n "time"')
 edit('internal/seteffects/rule_replay.go','type RuleReplay struct {','type RuleReplay struct {\n preparationInitSeconds,preparationEventSeconds float64\n preparationStage string')
 edit('internal/seteffects/rule_replay.go','out = RuleReplay{Values: make([]RuleValue, len(queries)), Uncertainty: []string{}}','out = RuleReplay{preparationStage:"pre_initialization",Values: make([]RuleValue, len(queries)), Uncertainty: []string{}}')
 edit('internal/seteffects/rule_replay.go','vms := []*ruleVM{}','initStarted:=time.Now()\n out.preparationStage="initialization"\n vms := []*ruleVM{}')
 edit('internal/seteffects/rule_replay.go','if err != nil {\n\t\tout.Boundary = err.Error()',
  'out.preparationInitSeconds=time.Since(initStarted).Seconds()\n if err != nil {\n\t\tout.Boundary = err.Error()')
 edit('internal/seteffects/rule_replay.go','indices := preparedOrder',
  'out.preparationStage="event_query_or_task"\n eventStarted:=time.Now();defer func(){out.preparationEventSeconds=time.Since(eventStarted).Seconds()}()\n indices := preparedOrder')
 edit('internal/seteffects/neutral_composition.go','if !component.usable {\n\t\t\treturn fallback()',
  'if !component.usable {\n b.preparationRejected([]RuleChoice{choice},component,false)\n\t\t\treturn fallback()')
 edit('internal/seteffects/neutral_composition.go','if !component.usable {\n\t\t\t\t\treturn fallback()',
  'if !component.usable {\n b.preparationRejected(choices,component,true)\n\t\t\t\t\treturn fallback()')
 edit('cmd/gtt-optimizer/theory_session.go','stopWorld := coarse.begin("config_world","")',
  'if os.Getenv("GTT_THEORY_PREPARATION_CASES")!="" {return preparationDiagnostic(model,requestSHA,sourceSHA,captured.GraphSHA256(),runRoot)}\n stopWorld := coarse.begin("config_world","")')
 for source,dest in [('preexperiment_diag.go.txt','internal/seteffects/preparation_diagnostic.go'),('preexperiment_command.go.txt','cmd/gtt-optimizer/preparation_diagnostic.go'),('preexperiment_test.go.txt','internal/seteffects/preparation_diagnostic_test.go')]:out[dest]=helpers[source]
 out['internal/setcontext/preparation_diagnostic.go']=b'''package setcontext
import("encoding/hex";"time";"genshinteamstracker/native/gcsim_optimizer/internal/seteffects";"genshinteamstracker/native/gcsim_optimizer/internal/formula")
func(m *NeutralModel) DiagnosePreparation(cases []seteffects.PreparationCase)(*seteffects.PreparationDiagnostic,error){
 return m.binding.DiagnosePreparation(cases,func(out seteffects.NeutralExpressions)seteffects.PreparationBindingEvidence{
  result:=seteffects.PreparationBindingEvidence{};if !out.Complete(){result.Error="unavailable_before_binding";return result}
  started:=time.Now();var program *formula.ParametricProgram;var err error
  if out.SparseEffects!=nil{program,err=m.bindMixed(out.Constants,out.SparseEffects)}else if out.Constants!=nil{program,err=m.bindConstants(out.Constants)}else{program,err=m.bindProgram(out.Effects)}
  result.Seconds=time.Since(started).Seconds();if err!=nil{result.Error=err.Error();return result};if key,ok:=m.r3ProgramKey(program);ok{result.ProgramIdentity=hex.EncodeToString(key[:])};return result
 })
}
'''
 return out

def cases():
 inv=read(OUT/'saved_inventory.json');leader=read(saved.CURRENT/'native.json')['co_leaders'][0]['measurement']['build_identity']['packages']
 def packages(rows):return [{'wearer':x['wearer_key'],'sets':[{'key':y['set_uid'],'pieces':y['count']} for y in x['sets']]} for x in rows]
 result=[{'id':'empty','packages':[]},{'id':'retained-leader-packages','packages':packages(leader)}]
 for i,row in enumerate(inv['complete_recovered_old_rows']):result.append({'id':'old-fragment-'+str(i),'packages':packages(row['packages'])})
 first=inv['complete_recovered_old_rows'][0]['packages'][0]
 derived=packages(leader)
 for row in derived:
  if row['wearer']==first['wearer_key']:row['sets']=packages([first])[0]['sets']
 result.append({'id':'leader-three-plus-first-old-pair','packages':derived})
 for i,setrow in enumerate(first['sets']):result.append({'id':'first-old-component-'+str(i),'packages':packages([{'wearer_key':first['wearer_key'],'sets':[setrow]}])})
 for cause in inv['control_reason_groups']:
  if cause['reason_code']=='unknown_operation':
   for row in leader:result.append({'id':'reason-operation-'+row['wearer_key'],'packages':[{'wearer':row['wearer_key'],'sets':[{'key':cause['mechanic_uid'],'pieces':4}]}]})
 if len(result)>16:raise ValueError('explicit diagnostic case cap')
 return result

def prepare():
 if ROOT!=WORKER or VARIANT.exists():raise ValueError('fresh owned diagnostic variant required')
 saved.inventory();baseline=(PACKAGE/'control.json').read_bytes();state=read(PACKAGE/'control.json')
 for name,digest in state['files'].items():
  if sha((PACKAGE/name).read_bytes())!=digest:raise ValueError('baseline changed: '+name)
 sys.path.insert(0,str(MAIN))
 from tools.experiments.gcsim.mvp_polish.r5_redundant import native_images
 from tools.experiments.gcsim.mvp_polish.r3_recovery import map_sha,mapping
 from tools.experiments.gcsim.mvp_polish import whole_chasca_target as target
 from tools.experiments.gcsim.mvp_polish.r5_python import install_image
 install_image()
 from tools.managed_optimizer_experiment import managed_scratch
 helpers={p.name:p.read_bytes() for p in (WORKER/phases.HELPERS).glob('*.go.txt')}
 base=phases.overlay(native_images(),helpers);base['internal/seteffects/r1_frozen_neutral.go'],_=change(base['internal/seteffects/r1_frozen_neutral.go'])
 VARIANT.mkdir(parents=True);write(VARIANT/'cases.json',cases())
 for path in [HERE,phases.HELPERS+'/preexperiment_saved.py']:
  dest=PACKAGE/path;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(WORKER/path,dest)
 subprocess.run([sys.executable,'-B',str(PACKAGE/HERE),'--action','materialize'],cwd=PACKAGE,check=True,timeout=120)
 go=Path('C:/Program Files/Go/bin/go.exe');snapshot=read(MAIN/'docs/optimizer-evidence/2026-10-26-response-pilot/whole-search-chasca-v3-target-snapshot.json')
 with managed_scratch(root=PACKAGE/'.codex_tmp/managed-optimizer') as job:
  module=job/'native';module.mkdir()
  name='internal/seteffects/r1_frozen_neutral.go';(module/name).parent.mkdir(parents=True);(module/name).write_bytes(base[name])
  subprocess.run([str(go),'fmt',str(module/name)],check=True,capture_output=True);base[name]=(module/name).read_bytes()
  if map_sha(base)!=BASE:raise ValueError('not exact bookkeeping source')
  candidate=overlay(base,helpers)
  for name,raw in candidate.items():
   path=module/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
  changed=[name for name in candidate if base.get(name)!=candidate[name]]
  for name in changed:
   subprocess.run([str(go),'fmt',str(module/name)],check=True,capture_output=True);candidate[name]=(module/name).read_bytes()
  temp=job/'temp';temp.mkdir()
  env=target.pin_target(dict(os.environ,GOTOOLCHAIN='local',GOMAXPROCS='2',GOMEMLIMIT='2GiB',GOFLAGS='-p=2 -mod=readonly',GOCACHE=str(job/'go-cache'),GOTMPDIR=str(temp),TMP=str(temp),TEMP=str(temp)),snapshot)
  env.update(phases.FLAGS);env.update(GTT_SCRATCH_DIR=str(job),GTT_FROZEN_MECHANICS_DIR=str(job/'frozen'),GTT_RULE_CACHE_DIR=str(job/'rules'));env['GTT_RULE_SOURCE_BUNDLE']=str(VARIANT/'set-sources.json');env['GTT_RULE_REQUEST']=str(VARIANT/'request.json')
  for label,command in [('collector-unit',[str(go),'-C',str(module),'test','-count=1','-v','-run','^TestPreparationDiagnostic(BoundedObservations|ObserverParity)$','./internal/seteffects']),('build',[str(go),'-C',str(module),'build','-trimpath','-buildvcs=false','-o',str(VARIANT/'diagnostic.exe'),'./cmd/gtt-optimizer'])]:
   with (OUT/(label+'.log')).open('w',encoding='utf-8') as log:subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
  binary_target=target.assert_binary_target(snapshot,target.inspect_binary(go,VARIANT/'diagnostic.exe',env,PACKAGE))
 delta=''.join(''.join(difflib.unified_diff(base.get(n,b'').decode('utf-8').splitlines(True),candidate[n].decode('utf-8').splitlines(True),fromfile='a/'+n,tofile='b/'+n)) for n in changed)
 (OUT/'instrumentation.patch').write_bytes(delta.encode('utf-8'));(OUT/'.gitattributes').write_text('instrumentation.patch -text\n',encoding='utf-8')
 for path in [HERE,phases.HELPERS+'/preexperiment_saved.py']:
  dest=PACKAGE/path;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(WORKER/path,dest)
 source={'base_map':BASE,'candidate_map':map_sha(candidate),'changed_files':changed,'candidate_files':mapping(candidate),'delta_sha256':sha(delta.encode('utf-8')),'consumer':sha((VARIANT/'diagnostic.exe').read_bytes()),'target':binary_target,'build_job_removed':not job.exists()}
 write(OUT/'source.json',source)
 pins={str(p.relative_to(PACKAGE)).replace('\\','/'):sha(p.read_bytes()) for p in [VARIANT/'diagnostic.exe',VARIANT/'request.json',VARIANT/'set-sources.json',VARIANT/'cases.json',PACKAGE/HERE,PACKAGE/phases.HELPERS/'preexperiment_saved.py']}
 write(OUT/'registry.json',{'status':'prepared','owner':'MAIN01a1824a / ROOT01a16b30; one preparation-only Luna diagnosis after review','created':time.time(),'expires':time.time()+7*86400,'files':pins,'baseline_control_sha256':sha(baseline),'baseline_consumer':state['consumer'],'engine_calls_prepare':0,'cases':len(cases()),'passes':2,'new_capture_needed':2,'search_calls':0,'ordinary_calls':0,'cleanup':'per-run managed scratch; --action release removes exact owned private variant; evidence retained'})
 assert (PACKAGE/'control.json').read_bytes()==baseline
 print('READY: preparation-only command; no numeric collection executed',flush=True)

def materialize():
 if ROOT!=PACKAGE:raise ValueError('pinned application required')
 from tools.experiments.gcsim import t1_control as common
 from tools.experiments.gcsim.mvp_polish import mechanic_button_gate as gate
 from run_workspace.gcsim import optimizer_go_session as session
 reached=[]
 def boundary(command,*args,**kwargs):
  if command[1]!='optimize-theory':raise AssertionError('unexpected materialization boundary')
  for src,dest in [(command[2],VARIANT/'request.json'),(command[3],VARIANT/'set-sources.json')]:shutil.copyfile(src,dest)
  reached.append(command[1]);raise RuntimeError('expected zero-engine input materialization boundary')
 def child(command,**kwargs):
  result=unittest.TestResult()
  with patch.dict(os.environ,kwargs['env']):common.CommonTheoryButtonTest('test_one').run(result)
  return SimpleNamespace(wait=lambda timeout:1,poll=lambda:1)
 with ExitStack() as stack:
  phases.configured(stack)
  with tempfile.TemporaryDirectory(prefix='materialize-',dir=OUT) as directory:
   temporary=Path(directory);state=read(PACKAGE/'control.json');state['status']='prepared';write(temporary/'registry.json',state)
   with patch.object(common,'OUT',temporary),patch.object(gate.run_case,'start_optimizer_process',child),patch.object(session,'start_optimizer_process',boundary),patch.object(session.GcsimOptimizerGoSession,'_validate_optimizer_request',lambda *a,**k:None),patch('subprocess.Popen',side_effect=AssertionError('zero-engine materialization')) as popen:
    try:common.run()
    except SystemExit as stop:
     if stop.code!=2:raise
    popen.assert_not_called();summary=read(temporary/'off.json');joined=summary['case']['process_guard']['worker_thread_joined'];removed=read(temporary/'registry.json')['job_removed']
   if reached!=['optimize-theory'] or not joined or not removed:raise ValueError('materialization did not reach clean joined boundary')
 write(OUT/'materialization.json',{'engine_calls':0,'actual_Popen_calls':0,'native_boundary':reached,'worker_joined':joined,'scratch_removed':removed,'preflight':'skipped only for zero-engine serialization; collect must run actual native validation before capture'})

def collect():
 if ROOT!=PACKAGE:raise ValueError('pinned application required')
 state=read(OUT/'registry.json')
 if state['status']!='prepared' or time.time()>state['expires']:raise ValueError('single unexpired diagnostic attempt required')
 for name,digest in state['files'].items():
  if sha((PACKAGE/name).read_bytes())!=digest:raise ValueError('diagnostic input changed: '+name)
 if sha((PACKAGE/'control.json').read_bytes())!=state['baseline_control_sha256']:raise ValueError('baseline manifest changed')
 baseline_state=read(PACKAGE/'control.json')
 if any(sha(Path(name).read_bytes())!=digest for name,digest in baseline_state['main_protected_before']['files'].items()):raise ValueError('protected MAIN files differ')
 from tools.managed_optimizer_experiment import managed_scratch
 from run_workspace.gcsim.optimizer_process_lifetime import start_optimizer_process,close_optimizer_process_lifetime
 state['status']='running';write(OUT/'registry.json',state)
 job=None
 try:
  with managed_scratch(root=PACKAGE/'.codex_tmp/managed-optimizer') as job:
   env=dict(os.environ,**phases.FLAGS,GTT_MECHANIC_CACHE_ENABLED='0',GTT_THEORY_PREPARATION_CASES=str(VARIANT/'cases.json'),GTT_SCRATCH_DIR=str(job),GTT_FROZEN_MECHANICS_DIR=str(job/'frozen'),GTT_RULE_CACHE_DIR=str(job/'rules'))
   baseline=read(saved.CURRENT/'observations.json')['ambient']['environment']
   if any(env.get(k)!=v for k,v in baseline.items()):raise ValueError('ambient Go/GC environment differs')
   for name,command in [('validation',[str(VARIANT/'diagnostic.exe'),'validate-theory-request',str(VARIANT/'request.json')]),('preparation',[str(VARIANT/'diagnostic.exe'),'optimize-theory',str(VARIANT/'request.json'),str(VARIANT/'set-sources.json'),str(job/'theory')])]:
    with (job/(name+'.stdout')).open('w',encoding='utf-8') as stdout,(job/(name+'.stderr')).open('w',encoding='utf-8') as stderr:
     process=start_optimizer_process(command,cwd=PACKAGE,env=env,stdout=stdout,stderr=stderr)
     try:
      if process.wait(timeout=450)!=0:raise RuntimeError('diagnostic '+name+' failed')
     finally:close_optimizer_process_lifetime(process)
   evidence=read(job/'theory/preparation-diagnostic.json')
   capture_count=len(list((job/'theory/contexts').rglob('capture-request.json')))
   if capture_count!=2:raise ValueError('expected exactly two neutral capture requests')
   panel=VARIANT/'saved-panel';panel.mkdir();pins=[];structure=[]
   for request in sorted((job/'theory/contexts').rglob('capture-request.json')):
    seed=request.parent.name
    for leaf in ['capture-request.json','config.txt','member.json','member.json.effects.json']:
     original=request.parent/leaf;raw=original.read_bytes();dest=panel/(seed+'-'+leaf+'.gz');dest.write_bytes(gzip.compress(raw,mtime=0))
     pins.append({'path':str(dest.relative_to(PACKAGE)),'sha256':sha(raw),'bytes':len(raw),'stored_sha256':sha(dest.read_bytes()),'stored_bytes':dest.stat().st_size})
     if leaf=='member.json.effects.json':
      sidecar=json.loads(raw.decode('utf-8'));neutral=sidecar['neutral']
      structure.append({'seed':seed,'sidecar_sha256':sha(raw),'characters':[{'key':x['key'],'index':x['index']} for x in neutral['context']['characters']]})
   write(OUT/'retained-panel.json',{'owner':state['owner'],'expires':state['expires'],'cleanup':'same exact private variant --action release','files':pins})
   write(OUT/'capture-structure.json',structure)
   write(OUT/'events.json',evidence);state.update(status='complete',capture_count=capture_count,search_calls=0,ordinary_calls=0,diagnostic_dropped=evidence['Evidence']['Dropped'],diagnostic_group_overflow=sum(row['Overflow'] for row in evidence['Evidence']['Replays']))
  state['job_removed']=not job.exists()
 except BaseException as error:
  state.update(status='failed',error_class=type(error).__name__,job_removed=job is None or not job.exists());raise
 finally:
  state['baseline_unchanged']=sha((PACKAGE/'control.json').read_bytes())==state['baseline_control_sha256'] and sha((PACKAGE/'native/gcsim_optimizer/gtt-optimizer.exe').read_bytes())==state['baseline_consumer']
  state['main_protected_after_match']=all(sha(Path(name).read_bytes())==digest for name,digest in baseline_state['main_protected_before']['files'].items())
  write(OUT/'registry.json',state)

def release():
 if ROOT!=PACKAGE or VARIANT.resolve()!=(WORKER/'.codex_tmp/t1-control-v1/app/private/variants/theory-preexperiment-v1').resolve():raise ValueError('unowned release')
 from tools.managed_optimizer_experiment import assert_unlinked
 if read(OUT/'registry.json')['status']=='running':raise ValueError('cannot release a running diagnostic')
 assert_unlinked(VARIANT)
 for path in VARIANT.rglob('*'):assert_unlinked(path)
 shutil.rmtree(VARIANT);state=read(OUT/'registry.json');state.update(status='released',variant_removed=True);write(OUT/'registry.json',state)

if __name__=='__main__':
 if sys.argv[1:] not in (["--action",x] for x in ['prepare','materialize','collect','release']):raise ValueError('explicit action required')
 globals()[sys.argv[2]]()
