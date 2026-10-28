"""Prune one observed health scalar graph, preserving independent engine values.

This is a diagnostic scalar channel, NOT a damage channel/product IR fixture.
No gameplay coefficient is evaluated here.
"""
from pathlib import Path
import argparse,hashlib,json
from export_samples import slice_member

p=argparse.ArgumentParser(__doc__)
p.add_argument('--matrix',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
args=p.parse_args()
load=lambda n:json.loads((args.matrix/n).read_text())
base=load('chasca.txt.observed.json')
fresh=load('chasca-bennett-hp_percent-0.466.txt.observed.json')
events={e['event_id']:e for e in fresh['state_events']}
channels={c['channel_id']:i for i,c in enumerate(base['support_graph']['channels'])}
for e in base['state_events']:
 if e['kind']!='numeric_eval' or e['operation']!='identity' or 'health_input_branch_schedule_frozen' not in e['uncertainty_codes']:continue
 f=events.get(e['event_id'])
 if f is None or any(e[k]!=f[k] for k in ['kind','frame','source_id','provider','operation']):continue
 if e['value']==f['value']:continue
 member=slice_member(base['support_graph'],channels[e['event_id']])
 coords={n.get('coordinate') for n in member['nodes']}
 if 'bennett.hp_percent' not in coords:continue
 # The scorer's validator accepts damage channels only. This explicitly
 # artificial test wrapper feeds a health scalar through the same arithmetic;
 # it never ships as a real compact damage channel.
 member['topology_sha256']=hashlib.sha256(json.dumps(member['nodes'],sort_keys=True).encode()).hexdigest()
 member['channels'][0].update(actor_key='furina',kind='direct',attack_tag='diagnostic-health-scalar',damage_type='diagnostic',hit_count=1,baseline_damage=str(e['value']),response_coordinates=sorted(c for c in coords if c))
 payload=dict(schema_version=1,scope='Observed health-input scalar, not damage; same original typed getter evaluated once.',
  frame=e['frame'],executing_provider=e['provider'],baseline_value=e['value'],member=member,
  deltas={'bennett.hp_percent':.466},fresh_engine_value=f['value'])
 args.out.write_text(json.dumps(payload,indent=2))
 print(json.dumps(dict(frame=e['frame'],nodes=len(member['nodes']),baseline=e['value'],fresh=f['value'])))
 break
else:raise AssertionError('No demonstrated foreign HP health-input response')
