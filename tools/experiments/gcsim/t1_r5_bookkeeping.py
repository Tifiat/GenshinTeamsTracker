"""One diagnostic-record variant over the retained timed R5 application."""
from contextlib import contextmanager
import difflib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.experiments.gcsim import t1_r5_phases as phases
from tools.experiments.gcsim.theory_phases.bookkeeping import change

ROOT=Path(__file__).resolve().parents[3]
WORKER=phases.WORKER
PACKAGE=phases.PACKAGE
OUT=WORKER/'docs/optimizer-evidence/2026-10-28-theory-phases/r5-bookkeeping-v1'
VARIANT=PACKAGE/'private/variants/r5-bookkeeping-v1'
HERE='tools/experiments/gcsim/t1_r5_bookkeeping.py'
BINARY=PACKAGE/'native/gcsim_optimizer/gtt-optimizer.exe'
TIMED='b0b5d32de00b3ddac20065badd26e5f649dba4b51a15f6739bf2bf63bcddca88'
CONSUMER='506cd4b75a4f751786ae5321e6e4e1a99df9007069dcf0e2c302a4e70eb6e202'
sha,read,write=phases.sha,phases.read,phases.write

def prepare():
 if ROOT!=WORKER or OUT.exists() or VARIANT.exists():raise ValueError('fresh owned variant required')
 baseline=(PACKAGE/'control.json').read_bytes()
 state=read(PACKAGE/'control.json')
 if sha(BINARY.read_bytes())!=CONSUMER or state['consumer']!=CONSUMER:raise ValueError('timed baseline changed')
 for name,digest in state['files'].items():
  if sha((PACKAGE/name).read_bytes())!=digest:raise ValueError('baseline file changed: '+name)
 sys.path.insert(0,str(phases.MAIN))
 from tools.experiments.gcsim.mvp_polish.r5_redundant import native_images
 from tools.experiments.gcsim.mvp_polish.r3_recovery import map_sha,mapping
 from tools.experiments.gcsim.mvp_polish import whole_chasca_target as target
 from tools.experiments.gcsim.mvp_polish.r5_python import install_image
 install_image()
 from tools.managed_optimizer_experiment import managed_scratch
 helpers={p.name:p.read_bytes() for p in (WORKER/phases.HELPERS).glob('*.go.txt')}
 base=phases.overlay(native_images(),helpers)
 if map_sha(base)!=TIMED:raise ValueError('timed source differs')
 name='internal/seteffects/r1_frozen_neutral.go'
 candidate=dict(base);candidate[name],oracle=change(base[name])
 OUT.mkdir(parents=True);VARIANT.mkdir(parents=True)
 (OUT/'.gitattributes').write_text('native-bookkeeping.patch -text\n',encoding='utf-8')
 (VARIANT/'baseline-control.json').write_bytes(baseline)
 shutil.copyfile(BINARY,VARIANT/'baseline.exe')
 go=Path('C:/Program Files/Go/bin/go.exe')
 snapshot=read(phases.MAIN/'docs/optimizer-evidence/2026-10-26-response-pilot/whole-search-chasca-v3-target-snapshot.json')
 with managed_scratch(root=PACKAGE/'.codex_tmp/managed-optimizer') as job:
  module=job/'native';module.mkdir()
  for path,raw in candidate.items():
   dest=module/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
  subprocess.run([str(go),'fmt',str(module/name)],check=True,capture_output=True)
  candidate[name]=(module/name).read_bytes()
  tests={'internal/seteffects/r1_bookkeeping_baseline_test.go':oracle,
         'internal/seteffects/r1_bookkeeping_test.go':helpers['bookkeeping_test.go.txt'],
         'internal/seteffects/r1_causal_diagnosis_test.go':helpers['diagnosis_test.go.txt']}
  for path,raw in tests.items():(module/path).write_bytes(raw)
  spy=job/'r1_frozen_spy.go'
  spy.write_bytes(candidate[name].replace(b'packageKey = ruleChoicesKey(choices)',b'packageKey = countedRecordPackageKey(choices)',1))
  if spy.read_bytes()==candidate[name]:raise ValueError('record spy seam missing')
  write(job/'test-overlay.json',{'Replace':{str(module/name):str(spy)}})
  temp=job/'temp';temp.mkdir()
  env=target.pin_target(dict(os.environ,GOTOOLCHAIN='local',GOMAXPROCS='2',GOMEMLIMIT='2GiB',
   GOFLAGS='-p=2 -mod=readonly',GOCACHE=str(job/'go-cache'),GOTMPDIR=str(temp),TMP=str(temp),TEMP=str(temp)),snapshot)
  commands=[('focused-tests',[str(go),'-C',str(module),'test','-count=1','-v','-overlay',str(job/'test-overlay.json'),
    '-run','^(TestR1FrozenCausalGuardAndCounterSemantics|TestFrozenBookkeepingParityAndLazyRecordKey)$','./internal/seteffects']),
   ('build',[str(go),'-C',str(module),'build','-trimpath','-buildvcs=false','-o',str(VARIANT/'candidate.exe'),'./cmd/gtt-optimizer'])]
  for label,command in commands:
   with (OUT/(label+'.log')).open('w',encoding='utf-8') as log:
    subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
  binary_target=target.assert_binary_target(snapshot,target.inspect_binary(go,VARIANT/'candidate.exe',env,PACKAGE))
 delta=''.join(difflib.unified_diff(base[name].decode().splitlines(True),candidate[name].decode().splitlines(True),fromfile='a/'+name,tofile='b/'+name))
 (OUT/'native-bookkeeping.patch').write_bytes(delta.encode())
 source={'base_map':TIMED,'candidate_map':map_sha(candidate),'changed_files':[name],
  'base_files':mapping(base),'candidate_files':mapping(candidate),'test_files':mapping(tests),
  'delta_sha256':sha(delta.encode()),'consumer':sha((VARIANT/'candidate.exe').read_bytes()),
  'baseline_consumer':CONSUMER,'target':binary_target,'build_job_removed':not job.exists(),
  'production_delta':'r1FreezeConcrete diagnostic record construction and lazy record package key only',
  'test_spy':'Go test source overlay replaces only the retained-record package key call; absent in built binary'}
 write(OUT/'source.json',source)
 for path in (HERE,phases.HELPERS+'/bookkeeping.py'):
  dest=PACKAGE/path;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(WORKER/path,dest)
 variant=dict(state);variant.update(status='prepared',attempt='r5-bookkeeping-v1',evidence=str(OUT),
  consumer=source['consumer'],source_native_timed=TIMED,source_native_bookkeeping=source['candidate_map'],
  created=time.time(),expires=time.time()+7*86400)
 variant['files']=dict(state['files']);variant['files']['native/gcsim_optimizer/gtt-optimizer.exe']=source['consumer']
 for path in (HERE,phases.HELPERS+'/bookkeeping.py'):variant['files'][path]=sha((PACKAGE/path).read_bytes())
 write(VARIANT/'control.json',variant);write(OUT/'registry.json',variant)
 if (PACKAGE/'control.json').read_bytes()!=baseline or sha(BINARY.read_bytes())!=CONSUMER:raise ValueError('baseline modified in prepare')
 print('PREPARED: focused tests/build complete; zero engine calls',flush=True)

@contextmanager
def activated():
 if ROOT!=PACKAGE:raise ValueError('use retained app runner')
 baseline=(VARIANT/'baseline-control.json').read_bytes()
 if (PACKAGE/'control.json').read_bytes()!=baseline or sha(BINARY.read_bytes())!=CONSUMER:raise ValueError('baseline activation precondition differs')
 variant=read(VARIANT/'control.json')
 if sha((VARIANT/'candidate.exe').read_bytes())!=variant['consumer']:raise ValueError('variant binary changed')
 if sha((VARIANT/'baseline.exe').read_bytes())!=CONSUMER:raise ValueError('rollback binary changed')
 try:
  shutil.copyfile(VARIANT/'candidate.exe',BINARY);write(PACKAGE/'control.json',variant)
  yield
 finally:
  shutil.copyfile(VARIANT/'baseline.exe',BINARY);(PACKAGE/'control.json').write_bytes(baseline)
  restored=sha(BINARY.read_bytes())==CONSUMER and (PACKAGE/'control.json').read_bytes()==baseline
  write(OUT/'activation.json',{'baseline_restored':restored,'baseline_consumer':CONSUMER,'variant_consumer':variant['consumer']})
  if not restored:raise ValueError('baseline restoration failed')

def main():
 if sys.argv[1:]==['--action','prepare']:prepare();return
 if sys.argv[1:]==['--action','release']:
  if ROOT!=PACKAGE or VARIANT.resolve()!=(WORKER/'.codex_tmp/t1-control-v1/app/private/variants/r5-bookkeeping-v1').resolve():raise ValueError('unowned release')
  if sha(BINARY.read_bytes())!=CONSUMER:raise ValueError('restore timed baseline before releasing variant')
  from tools.managed_optimizer_experiment import assert_unlinked
  assert_unlinked(VARIANT)
  for path in VARIANT.rglob('*'):assert_unlinked(path)
  shutil.rmtree(VARIANT)
  state=read(OUT/'registry.json');state.update(status='released',variant_removed=True,baseline_retained=True)
  write(OUT/'registry.json',state);return
 if sys.argv[1:] not in (['--action','bootstrap'],['--action','run']):raise ValueError('only prepare/bootstrap/one run')
 with activated(),patch.object(phases,'OUT',OUT):phases.main()

if __name__=='__main__':main()
