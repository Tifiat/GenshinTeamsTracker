"""Saved event reduction and read-only custody checks; no engine/search calls."""
from collections import Counter,defaultdict
import gzip
import hashlib
import json
from pathlib import Path

WORKER=Path('C:/Users/user/Desktop/worker3 GTT')
PACKAGE=WORKER/'.codex_tmp/t1-control-v1/app'
OUT=WORKER/'docs/optimizer-evidence/2026-10-28-theory-phases/theory-preexperiment'
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def rows_for(rows,case,passno):return [x for x in rows if x['Case']==case and x['Pass']==passno]
def total(rows,key):return sum(x[key] for x in rows)

def main():
 event=read(OUT/'events.json');e=event['Evidence'];registry=read(OUT/'registry.json')
 specs=read(PACKAGE/'private/variants/theory-preexperiment-v1/cases.json')
 baseline=read(PACKAGE/'control.json');source=read(OUT/'source.json')
 assert registry['status']=='complete' and registry['capture_count']==2
 assert len(specs)==15 and len(e['Cases'])==30
 assert Counter((x['ID'],x['Pass']) for x in e['Cases'])==Counter((x['id'],p) for x in specs for p in [1,2])
 assert registry['search_calls']==registry['ordinary_calls']==e['Dropped']==0
 assert e['Schema']=='theory_preparation_events_v1'
 assert all(sha(PACKAGE/name)==digest for name,digest in registry['files'].items())
 assert all(sha(PACKAGE/name)==digest for name,digest in baseline['files'].items())
 assert sha(PACKAGE/'control.json')==registry['baseline_control_sha256']
 assert all(sha(Path(name))==digest for name,digest in baseline['main_protected_before']['files'].items())
 assert sha(OUT/'instrumentation.patch')==source['delta_sha256']
 assert source['consumer']==registry['files']['private/variants/theory-preexperiment-v1/diagnostic.exe']
 oldoff=read(WORKER/'docs/optimizer-evidence/2026-10-28-theory-phases/r5-bookkeeping-v1/off.json')
 assert event['RequestSHA']==oldoff['case']['config_join']['request_sha256']
 assert event['SourceSHA']==registry['files']['private/variants/theory-preexperiment-v1/set-sources.json']
 assert not list((PACKAGE/'.codex_tmp/managed-optimizer').glob('job-*'))
 assert all(registry[x] for x in ['job_removed','baseline_unchanged','main_protected_after_match'])
 retained=read(OUT/'retained-panel.json');assert len(retained['files'])==8
 for pin in retained['files']:
  path=PACKAGE/pin['path'];assert sha(path)==pin['stored_sha256'] and path.stat().st_size==pin['stored_bytes']
  raw=gzip.decompress(path.read_bytes());assert len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256']
 assert len(read(OUT/'capture-structure.json'))==2
 replay=e['Replays'];unknown_overflow=0
 for x in replay:
  assert sum(y['Known']+y['Unknown'] for y in x['Coverage'])==x['Ports']
  assert sum(y['Unknown'] for y in x['Coverage'])==x['UnknownPorts']
  missing=x['UnknownPorts']-sum(y['port_observations'] for y in (x['Unknown'] or []))
  assert 0<=missing<=x['Overflow'];unknown_overflow+=missing
 overflow=total(replay,'Overflow');assert overflow==registry['diagnostic_group_overflow']==337372
 assert unknown_overflow==overflow
 cases=[]
 for x in e['Cases']:
  rr=rows_for(replay,x['ID'],x['Pass']);jj=rows_for(e['Joint'],x['ID'],x['Pass']);ff=rows_for(e['FreezeConcrete'],x['ID'],x['Pass'])
  cases.append({'id':x['ID'],'pass':x['Pass'],'preparation_seconds':x['Seconds'],'binding_seconds':x['Binding']['Seconds'],
   'joint_calls':len(jj),'replay_calls':len(rr),'freeze_calls':len(ff),'symbolic_seconds':sum(y['Seconds'] for y in rr if y['Symbolic']),
   'concrete_seconds':sum(y['Seconds'] for y in rr if not y['Symbolic']),'direct_freeze_concrete_seconds':total(ff,'Seconds'),
   'full_fallback_rows':len(rows_for(e['Fallbacks'],x['ID'],x['Pass'])),'frozen':x['Frozen'],'complete':x['Complete'],
   'output_digest':x['DiagnosticOutputSHA256'],'binding_program':x['Binding']['ProgramIdentity'],'binding_error':x['Binding']['Error']})
 assert all(x['complete'] and not x['binding_error'] for x in cases)
 pairs=[]
 for test in specs:
  a,b=[x for x in cases if x['id']==test['id']]
  pairs.append({'id':test['id'],'same_diagnostic_output':a['output_digest']==b['output_digest'],'same_binding_program':a['binding_program']==b['binding_program'],'pass1_joint_calls':a['joint_calls'],'pass2_joint_calls':b['joint_calls']})
 assert all(x['same_diagnostic_output'] and x['same_binding_program'] for x in pairs)
 assert len(e['Fallbacks'])==20 and all(not x['Group'] and x['Tracked'] for x in e['Fallbacks'])
 for rejected in e['Fallbacks']:
  assert any(x['Choices']==rejected['RejectedChoices'] and x['AfterComplete'] and x['Frozen'] and x['Tracked'] for x in e['Joint'])
 control='leader-three-plus-first-old-pair';selected=next(x for x in e['Cases'] if x['ID']==control and x['Pass']==1)
 coverage=defaultdict(lambda:Counter())
 for row in selected['FrozenPortObservations']:coverage[(row['Seed'],row['Owner'])].update(anchor=row['Anchor'],reference=row['Reference'])
 control_coverage=[{'seed':s,'owner':o,**dict(counts)} for (s,o),counts in sorted(coverage.items())]
 assert sum(x['reference'] for x in control_coverage)==9853 and sum(x['anchor'] for x in control_coverage)==0
 berserker=[]
 for x in replay:
  if x['Pass']==1 and x['Case'].startswith('reason-operation-'):
   owner=int(x['Choices'].split(':',1)[0]);cause=(x['Causes'] or [])[0]['first_event']
   assert cause['operation']=='CurrentHPRatio' and cause['kind']=='unknown_operation'
   assert all(y['Unknown']==0 for y in x['Coverage'] if y['Owner']!=owner)
   berserker.append({'case':x['Case'],'owner':owner,'seed':x['Seed'],'symbolic':x['Symbolic'],'seconds':x['Seconds'],
    'initialization_seconds':x['InitSeconds'],'event_query_seconds':x['EventQuerySeconds'],'known_ports':x['Ports']-x['UnknownPorts'],
    'unknown_ports':x['UnknownPorts'],'first_frame':cause['frame'],'first_order':cause['order']})
 for case in e['Cases']:
  if case['ID'].startswith('reason-operation-'):
   owner=int(case['Choices'].split(':',1)[0]);ports=case['FrozenPortObservations']
   assert ports and all(x['Owner']==owner and x['Kind']=='attack' and x['Anchor']==0 for x in ports)
   rr=rows_for(replay,case['ID'],case['Pass'])
   assert sum(x['Reference'] for x in ports)==sum(x['UnknownPorts'] for x in rr if x['Symbolic'])
 timing={'case_preparation_inclusive_seconds':total(e['Cases'],'Seconds'),'joint_inclusive_seconds':total(e['Joint'],'Seconds'),
  'symbolic_member_replay_seconds':sum(x['Seconds'] for x in replay if x['Symbolic']),
  'concrete_member_replay_seconds':sum(x['Seconds'] for x in replay if not x['Symbolic']),
  'replay_initialization_nested_seconds':total(replay,'InitSeconds'),'replay_event_query_nested_seconds':total(replay,'EventQuerySeconds'),
  'outer_freeze_inclusive_seconds':total(e['Joint'],'FreezeSeconds'),'direct_freeze_concrete_nested_seconds':total(e['FreezeConcrete'],'Seconds'),
  'freeze_observer_nested_seconds':total(e['Joint'],'FreezeObserverSeconds'),'freeze_residual_not_pure_bookkeeping_seconds':total(e['Joint'],'FreezeResidualSeconds'),
  'binding_separate_seconds':sum(x['Binding']['Seconds'] for x in e['Cases']),'observer_mixed_scope_seconds':e['ObserverSeconds']}
 report={'schema':'theory_preexperiment_result_summary_v1','status':'complete_report_stop','source_commit':'ff6c233',
  'events_sha256':sha(OUT/'events.json'),'event_binding':{k:v for k,v in event.items() if k!='Evidence'},'inputs':e['Inputs'],
  'calls':{'captures':2,'search':0,'ordinary':0,'case_rows':30,'distinct_case_choices':len(set(x['Choices'] for x in e['Cases'])),
   'joint':len(e['Joint']),'member_replay':len(replay),'freeze_concrete':len(e['FreezeConcrete']),'rejections':len(e['Fallbacks'])},
  'timing':timing,'case_summary':cases,'pass_identity_checks':pairs,
  'distinct_diagnostic_output_digests':len(set(x['output_digest'] for x in cases)),
  'distinct_binding_program_ids':len(set(x['binding_program'] for x in cases)),
  'control_frozen_coverage':control_coverage,'control_program_equals_empty':selected['Binding']['ProgramIdentity']==e['Cases'][0]['Binding']['ProgramIdentity'],
  'berserker_first_pass':berserker,
  'observed_rejections_all_complete_frozen_tracked_components':True,
  'berserker_frozen_coverage_only_own_unknown_attack_ports':True,
  'overflow':{'row_dropped':e['Dropped'],'combined_group_observations_omitted':overflow,'unknown_port_detail_observations_omitted':unknown_overflow,'mechanic_cause_observations_omitted':overflow-unknown_overflow,'meaning':'Cap8 unknown-detail keys per replay; repeated unretained keys count on each observation. Not unique omitted groups, capture loss, missing cases or unknown port count loss. Full Coverage counts and retained first causes remain.'},
  'custody':{'all_six_private_runner_pins_match':True,'all_baseline_file_pins_match':True,'baseline_manifest_exact':True,'main_four_protected_files_match':True,
   'retained_archives':8,'retained_compressed_bytes':sum(x['stored_bytes'] for x in retained['files']),'retained_raw_bytes':sum(x['bytes'] for x in retained['files']),
   'retained_archive_raw_and_stored_hashes_match':True,'managed_jobs_remaining':0,'job_removed':True,'baseline_unchanged':True},
  'limits':['Small selected panel; no production frequency or attribution of313.493s','Direct preparation bypasses NeutralModel dispatch','No new ordinary DPS/quality/physical sensitivity or search-start/incumbent lineage','Only6 recovered old tuple rows, no full476 join','Timer scopes overlap and include collector work; zero durations are clock resolution','Output digests are not arithmetic-family IDs; binding IDs are local to this captured model']}
 (OUT/'summary.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':report['status'],'case_rows':30,'row_dropped':e['Dropped'],'overflow_unknown_details':unknown_overflow,'cause_overflow':0,'custody':report['custody'],'timing':timing},indent=2))

if __name__=='__main__':main()
