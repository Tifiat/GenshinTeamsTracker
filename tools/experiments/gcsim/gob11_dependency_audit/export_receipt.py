"""Export only bounded, non-secret audit summaries; no live account writes."""
from pathlib import Path
import hashlib,json
from collections import Counter
root=Path(__file__).resolve().parents[4]
work=root/'.codex_tmp/gob11-dependency-repair-20260916'
load=lambda p:json.loads(p.read_text(encoding='utf-8'))
matrix=work/'audit-all5'
responses=load(matrix/'response.json')+load(work/'audit-hp5/response.json')
winner=load(work/'audit5/comparison.json')
assert winner['reports'][0]['aligned_channels'] and not winner['reports'][0]['mismatched_hits']
selected=load(work/'selected-audit5/result.json')
assert selected['success']
r=selected['result']
run=Path(selected['run_dir'])
backend=load(run/'verification/gob7-result.json')
request=load(run/'request.json')
initial_ids=[value for row in backend['search']['initial']['assignment'] for value in row]
incumbents=[c for c in r['candidates'] if [a['artifact_id'] for a in c['artifacts']]==initial_ids]
assert len(incumbents)==1
assert incumbents[0]['artifacts']==[a for w in request['wearers'] for a in w['current_artifacts']]
timing=dict(compile_ms=backend['compile_elapsed_ms'],offline_search_ms=backend['search_elapsed_ms'],screen_n128_ms=backend['screening']['total_elapsed_ms'],final_adaptive_verification_ms=backend['verification']['total_elapsed_ms'],backend_total_ms=backend['total_elapsed_ms'])
sources=dict(gaming_melt='gtNnJTkcfcDg',lunar_crystallize='wNHmwLJH6RKJ',spread='qGdPFjmGbnGm',aggravate='LCHPRD6m7TtT',vaporize='hrwTfHDRG9z8',burgeon='cWBjFFQPJfFf',burning='pm7j7grtQ6tc',physical='mCzhk7WnqcrG')
pending=root/'tools/experiments/gcsim/gob11_dependency_audit/engine_delta.patch'
boundaries=[]
for folder in ('audit-health5','audit-hp5'):
 directory=work/folder
 base=load(directory/'chasca.txt.observed.json')
 counts=lambda o:Counter(e['frame'] for e in o['state_events'] if e['kind']=='health_context_enter')
 a=counts(base)
 for point in load(directory/'support-aligned-diagnosis.json'):
  if not point['differences']:continue
  fresh=load(directory/(point['point']+'.txt.observed.json'));b=counts(fresh)
  frame=min(f for f in a.keys()|b.keys() if a[f]!=b[f])
  first=point['first'][0]
  assert first['base_event']['frame']>=frame,(point['point'],'numerical loss precedes changed health schedule')
  response=next(r for r in responses if r['changed']==point['point']+'.json')
  first_hit=base['hits'][response['first_mismatches'][0]['index']]
  assert first_hit['frame']>=frame
  boundaries.append(dict(point=point['point'],first_changed_health_frame=frame,base_health_events_at_frame=a[frame],fresh_health_events_at_frame=b[frame],first_matched_state_difference_frame=first['base_event']['frame'],first_hit_difference_frame=first_hit['frame'],relative_team_error=response['relative_error'],mismatched_hits=response['mismatched_hits'],unmatched_state_events=point['unaligned_events']))
receipt=dict(schema_version=1,date='2026-09-16',status='isolated_repair_validated_partial_boundaries_not_promoted',
 engine_id='gcsim-v2.45.0-dependency-audit5-20260916',binary_sha256='2e910ca6ba8adf90d23ca41345ae85326855bb0677778703b749219d1dd582b5',
 candidate_build_patch_sha256=hashlib.sha256((work/'patch_stack/0001-gtt-engine-adapter-v245.patch').read_bytes()).hexdigest(),pending_delta_sha256=hashlib.sha256(pending.read_bytes()).hexdigest(),
 production_changed=False,visible_ui_tested=False,
 ui_blocker='Windows native computer-use tools absent from callable tool inventory; CUA native APIs disabled. No replacement click-handler claim.',
 controls=dict(seed=742031889,iterations=1,energy_ignored=True,stat_mutation='append add-stats without changing original character declaration order',baseline_cases=12,stat_points=len(responses),exact_per_hit_points=sum(x.get('aligned',False) and x.get('mismatched_hits')==0 for x in responses)),
 public_sources={k:'https://gcsim.app/db/'+v for k,v in sources.items()},
 public_fixture_scope='Account-owned characters; public gear/constellations retained for formula coverage only, not account Selected DPS acceptance.',
 responses=responses,
 same_old_bloom_winner=winner,
 ordinary_trace_parity=load(matrix/'ordinary-parity-coverage.json'),
 health_owner_parity=load(work/'audit-health5/ordinary-parity-coverage-chasca.json'),
 additional_health_parity=load(work/'audit-hp5/ordinary-parity-coverage-chasca.json'),
 selected=dict(elapsed_ms=selected['elapsed_ms'],formula_dps=r['formula_dps'],measured=r['measured'],formula_residual=r['formula_residual'],warnings=r['warnings'],winner=r['winner'],candidates=r['candidates'],preservation=load(work/'selected-audit5/preservation.json'),timing_scope='One real default-budget backend run, concurrent regression work; not a clean speed benchmark.'),
 selected_execution=dict(timing=timing,stop_reason=backend['search']['stop_reason'],completed_cycles=backend['search']['completed_cycles'],accepted_steps=backend['search']['accepted_steps'],initial_candidate=incumbents[0],initial_identity_scope='Exact ordered twenty wearer/slot/artifact rows match request.current_artifacts and search.initial.assignment in the same run.'),
 health_owner_repair=dict(scope='Built and tested audit5: typed receiver ownership and original-position single-evaluation health-input ancestry; source and binary match.',scalar_regression=dict(frame=93,baseline=497.7933635413888,fresh_and_predicted=590.228404695008,delta={'bennett.hp_percent':.466}),schedule_boundary_evidence=boundaries),
 known_limits=['Five HP/healing response controls differ after changed health-operation schedules; max absolute tested team residual0.42465%. Fixed-schedule reconstruction does not create previously absent health events or re-evaluate pet participant branches.',
 'No universal arbitrary-Go dependency completeness; unsupported paths stay locally frozen.',
 'Older prepended-stat matrices changed party declaration order and are superseded for response acceptance; do not treat their apparent topology/Flins HP failures as product failures.'],
 tests=['audit5 source-generator full tree, runtime/compact/info/character/combat tests','native go test ./...','14 refreshed portable fresh-engine response slices plus one foreign health scalar through reference, dense and one-wearer evaluators','pending delta git apply --check against installed GP-3 source'])
target=root/'tests/fixtures/gcsim_optimizer_go_v1/gob11_dependency_audit_receipt_v1.json'
target.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(dict(exact_points=receipt['controls']['exact_per_hit_points'],candidate_count=len(r['candidates']),winner_dps=r['measured']['dps'],bytes=target.stat().st_size)))
