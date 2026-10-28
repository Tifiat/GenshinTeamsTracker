"""Read-only inventory/extraction; no product import or numerical execution."""
import hashlib
import json
from pathlib import Path

DESKTOP=Path('C:/Users/user/Desktop')
MAIN=DESKTOP/'GenshinTeamsTracker'
WORKER=DESKTOP/'worker3 GTT'
OUT=WORKER/'docs/optimizer-evidence/2026-10-28-theory-phases/theory-preexperiment'
OLD=MAIN/'docs/optimizer-evidence/2026-10-25-cache-team-matrix/corpus-main14-v2/chasca_600_fixture-theory'
CONTROL=DESKTOP/'worker2 GTT/docs/optimizer-evidence/2026-10-28-theory-control/control-v2'
CURRENT=WORKER/'docs/optimizer-evidence/2026-10-28-theory-phases/r5-bookkeeping-v1'

def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def fragment_rows():
 data=load(OLD/'off-details/native-causes.json');rows={};fragments=[]
 for failure in data['failures']:
  text=failure.get('message','');fragments.append({'characters':len(text),'sha256':hashlib.sha256(text.encode()).hexdigest()})
  cursor=0
  while True:
   pos=text.find('{"tuple_key":',cursor)
   if pos<0:break
   cursor=pos+1
   try:row,_=json.JSONDecoder().raw_decode(text[pos:])
   except json.JSONDecodeError:continue
   if set(row)>={'tuple_key','packages','reasons'}:rows[row['tuple_key']]=row
 return [rows[k] for k in sorted(rows)],fragments

def inventory():
 OUT.mkdir(parents=True,exist_ok=True)
 rows,fragments=fragment_rows()
 old=load(OLD/'off.json');control=load(CONTROL/'off.json');new=load(CURRENT/'off.json')
 old_native=load(CONTROL/'native.json');new_native=load(CURRENT/'native.json')
 aliases=[old_native['co_leaders'][0]['aliases'][0]['uncertainty'],new_native['co_leaders'][0]['aliases'][0]['uncertainty']]
 assert aliases[0]==aliases[1] and len(aliases[0])==41
 arch=load(MAIN/'docs/optimizer-evidence/2026-10-27-engineering-efficiency/architecture-inputs-v1.json')
 report={'schema':'theory_preexperiment_saved_v1','engine_calls':0,'search_calls':0,
  'inputs':{str(p):digest(p) for p in [OLD/'off.json',OLD/'off-details/native-causes.json',CONTROL/'off.json',CONTROL/'native.json',CURRENT/'off.json',CURRENT/'native.json',CURRENT/'phases.json']},
  'historical_unavailable_count':old['case']['result_summary']['theory_snapshot']['unavailable_count'],
  'control_unavailable_count':old_native['unavailable_count'],'current_unavailable_count':new_native['unavailable_count'],
  'old_reason_groups':old['mechanics']['reason_codes']['groups'],
  'control_reason_groups':control['mechanics']['reason_codes']['groups'],
  'current_reason_groups':new['mechanics']['reason_codes']['groups'],
  'old_bound_boundary_source_available':old['mechanics']['bound_boundaries']['source_available'],
  'bounded_fragment':fragments,'complete_recovered_old_rows':rows,
  'recovered_rows_are_complete_unavailable_corpus':False,
  'full_old_to_new_tuple_join_available':False,
  'finalist_uncertainty_identical_41':aliases[0],
  'finalist_packages_identical':old_native['co_leaders'][0]['measurement']['build_identity']['packages']==new_native['co_leaders'][0]['measurement']['build_identity']['packages'],
  'no_r1_code_in_retained_leader_aliases':not any(x.startswith('r1_') for x in aliases[1]),
  'legacy_capture_representativeness':arch['representativeness'],
  'legacy_capture_has_mechanic_invocations':[x['has_mechanic_invocations'] for x in arch['saved_payloads']],
  'legacy_capture_config_sha256':arch['saved_payloads'][0]['config_sha256'],
  'current_prepared_config_sha256':new['case']['config_join']['prepared_config_sha256'],
  'missing':['complete old476 unavailable keys/reasons','current per-tuple resolution/fallback events','per-rule/member symbolic/concrete replay cost','full fallback cause/choice frequency','source event linkage for frozen ports','search start/incumbent lineage','matching current neutral capture pair after raw cleanup'],
  'interpretation_limit':'Reason groups count diagnostic observations, not unique tuples, rules, or share of313s. A fragment cannot establish complete distribution. Equal41 uncertainty is inherited model coverage, not newly introduced41 R1 failures.'}
 (OUT/'saved_inventory.json').write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'recovered_complete_old_rows':len(rows),'old_full_count':476,'leader_uncertainty_same':len(aliases[0]),'engine_calls':0}))

def source_inventory():
 private=WORKER/'.codex_tmp/t1-control-v1/app/private/variants/theory-preexperiment-v1'
 bundle=load(private/'set-sources.json');request=load(private/'request.json')
 engine=WORKER/'.codex_tmp/t1-control-v1/app/data/gcsim/engines/engines/gcsim-v2.45.0-mechanic-compiler-20261025'
 assert bundle['engine_sha256']==request['engine']['artifact_sha256']
 selected=['internal/artifacts/berserker/berserker.go','internal/artifacts/oceanhuedclam/oceanhuedclam.go','pkg/core/gtt_neutral_resources.go','pkg/gtttrace/neutral_world.go']
 rows=[]
 for name in selected:
  row=bundle['rule_repository']['files'][name]
  assert hashlib.sha256(row['text'].encode('utf-8')).hexdigest()==row['sha256']==digest(engine/name)
  if name.startswith('internal/artifacts/'):
   item=next(x for x in bundle['items'] if x['key']==name.split('/')[2]);assert item['sources'][name]==row
  rows.append({'path':name,'sha256':row['sha256'],'runtime_file_equals_catalog_and_repository':True})
 report={'schema':'theory_preexperiment_source_proof_v1','engine_sha256':bundle['engine_sha256'],'source_manifest_sha256':bundle['source_manifest_sha256'],'catalog_sha256':bundle['catalog_sha256'],'set_sources_sha256':digest(private/'set-sources.json'),'selected_sources':rows,'CurrentHPRatio_operation_descriptors':[x for x in bundle['mechanic_operations']['operations'] if x.get('method')=='CurrentHPRatio' or 'CurrentHPRatio' in x.get('symbol','')],'limit':'Source-only path proof; actual world order1/Facts presence requires current capture. No exporter loss is inferred solely from fact(nil).'}
 (OUT/'source_proof.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':inventory()
