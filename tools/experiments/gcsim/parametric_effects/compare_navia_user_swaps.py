"""Bounded 2026-09-26 user-requested Navia counterfactuals, not a search.

Owner: optimizer Go design's Navia evidence. Replaced by the final ranking gate;
remove with the parametric research helpers at that gate. All generated data
uses the tested managed scratch lifecycle; only compact stdout is exported.
Account DB is read-only; no engine, equipment or optimizer changes.
"""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from tools.experiments.gcsim.mode_matrix.compare_flins_cross_assignment import (
    SLOTS, ARTIFACT_LINE, _build_config, _ordinary_budget,
    _virtual_selected_team, _scratch_environment, _bound_artifact_registry_source,
    normalize_optimizer_rotation_shell, load_active_gcsim_optimizer_engine_context,
    run_active_gcsim_artifact,
)
from tools.experiments.gcsim.parametric_effects.verify_candidates import owned_job


def variants(baseline):
    specs = [
        ('baseline', None, {}),
        ('navia_plume1535_cv38.9', 'navia', {'plume': 1535}),
        ('navia_plume2_cv35.8', 'navia', {'plume': 2}),
        ('navia_plume1534_cv34.1', 'navia', {'plume': 1534}),
        ('navia_goblet64_atk_em63', 'navia', {'goblet': 64}),
        ('navia_goblet88_atk_cv36.6', 'navia', {'goblet': 88}),
        ('navia_goblet103_atk_cv38.8', 'navia', {'goblet': 103}),
        ('columbina_millelith_free_em_sands', 'columbina', {'flower': 1395, 'circlet': 1614}),
        ('columbina_millelith_em_sands', 'columbina', {'flower': 1395, 'sands': 173}),
        ('columbina_millelith_hp_sands', 'columbina', {'flower': 1395, 'sands': 48}),
        ('ineffa_flower71_cr17.9', 'ineffa', {'flower': 71}),
        ('xilonen_def_circlet_scroll_em_goblet', 'xilonen', {'circlet': 1547, 'goblet': 34}),
        ('xilonen_def_circlet_scroll_geo_goblet', 'xilonen', {'circlet': 1547, 'goblet': 1285}),
        ('columbina_millelith_saved_navia', 'columbina', {'flower': 1395, 'sands': 173, 'circlet': 203}),
        ('columbina_millelith_saved_flins', 'columbina', {'flower': 1395, 'sands': 173, 'circlet': 1436}),
        ('columbina_millelith_free_hp_sands', 'columbina', {'flower': 1395, 'sands': 8, 'circlet': 1614}),
    ]
    result = []
    for name, actor, replacements in specs:
        assignment = deepcopy(baseline)
        if actor:
            assignment[actor].update(replacements)
        flat = [v for b in assignment.values() for v in b.values()]
        if len(flat) != 20 or len(set(flat)) != 20:
            raise ValueError(f'Physical artifact conflict in {name}')
        changed = {k for k in baseline if baseline[k] != assignment[k]}
        if changed != ({actor} if actor else set()):
            raise ValueError(f'Non-isolated counterfactual: {name}')
        result.append((name, assignment))
    return result


def non_artifact_hash(config):
    # 2+2 adds one set declaration: discard blank rows left by removing it,
    # but preserve order and exact contents of every non-artifact declaration.
    text = '\n'.join(line for line in ARTIFACT_LINE.sub('', config).splitlines() if line.strip())
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    job = owned_job()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', action='append', default=[])
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--iterations', type=int, default=2000, choices=(1, 10, 2000))
    args = parser.parse_args()
    source = ROOT / 'docs/optimizer-evidence/all-sets-inventory-20260919/after.json'
    row = [r for r in json.loads(source.read_bytes())['runs']
           if r['id'] == 'lunar_crystallize_all_sets'][-1]
    if row['attempt'] != 3 or not row['success']:
        raise ValueError('Expected retained Navia attempt3')
    engine = load_active_gcsim_optimizer_engine_context()
    if engine.artifact_sha256 != row['engine_identity']['artifact_sha256']:
        raise ValueError('Saved Navia run differs from the active button engine')
    baseline = {b['wearer_key']: b['artifact_ids'] for b in row['product']['candidates'][0]['builds']}
    cases = variants(baseline)
    if args.only:
        if not set(args.only) <= {name for name, _ in cases}:
            raise ValueError('Unknown counterfactual')
        cases = [(name, assignment) for name, assignment in cases if name in args.only]
    db = ROOT / 'data/artifacts.db'
    # Read and print every used item's current source data, without initializers.
    with closing(sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        for aid in sorted({i for _, a in cases for b in a.values() for i in b.values()}):
            item = dict(conn.execute('SELECT id,set_uid,pos,level,main_property_type,main_property_value FROM artifacts WHERE id=?', (aid,)).fetchone())
            item['substats'] = [dict(x) for x in conn.execute('SELECT property_type,value FROM artifact_substats WHERE artifact_id=? ORDER BY slot_index', (aid,))]
            for _, assignment in cases:
                for build in assignment.values():
                    for slot, item_id in build.items():
                        if aid == item_id and item['pos'] != SLOTS.index(slot) + 1:
                            raise ValueError('Wrong artifact slot')
            print('ITEM ' + json.dumps(item), flush=True)
    profiles = row['input_entry']['virtual_profiles']
    team = _virtual_selected_team(profiles)
    rotation_source = ROOT / row['rotation_file']
    if hashlib.sha256(rotation_source.read_bytes()).hexdigest() != row['rotation_sha256']:
        raise ValueError('Saved rotation changed')
    rotation = normalize_optimizer_rotation_shell(rotation_source.read_text(encoding='utf-8'))
    iterations = args.iterations
    expected = non_artifact_hash(_ordinary_budget(row['inventory_search']['prepared_config'], iterations=iterations, workers=4))
    print('IDENTITY ' + json.dumps(dict(engine_id=engine.engine_id, binary=engine.artifact_path,
        engine_sha256=engine.artifact_sha256, baseline_assignment=baseline,
        non_artifact_sha256=expected, iterations=iterations, cases=len(cases))), flush=True)
    with _scratch_environment(job):
        rotation_path = job / 'rotation.txt'
        rotation_path.write_text(rotation.optimizer_text, encoding='utf-8')
        prepared = []
        for name, assignment in cases:
            config = _build_config(db_path=db, profiles=profiles, selected_team=team,
                rotation_path=rotation_path, registry_path=_bound_artifact_registry_source(Path(engine.engine_root)),
                ids_by_wearer=assignment, case_root=job / name, iterations=iterations)
            if non_artifact_hash(config) != expected:
                raise ValueError(f'Non-artifact input drift in {name}')
            prepared.append((name, assignment, config))
        if args.prepare_only:
            print('PREPARATION_PASS ' + str(len(prepared)), flush=True)
            return
        for name, assignment, config in prepared:
            start = time.perf_counter()
            outcome = run_active_gcsim_artifact(config, run_dir=job / name / 'ordinary',
                timeout_seconds=240, expected_engine_id=engine.engine_id)
            if not outcome.success or outcome.summary.iterations != iterations:
                raise RuntimeError(f'{name}: {outcome.status}: {outcome.error}')
            if Path(outcome.artifact_path).resolve() != Path(engine.artifact_path).resolve():
                raise ValueError('Runner did not use active binary')
            raw = json.loads(Path(outcome.result_path).read_bytes())
            stats = raw['statistics']
            detail = {'character_dps': stats['character_dps'],
                'source_dps_means': [{k: v['mean'] for k, v in row['sources'].items()} for row in stats['source_dps']]}
            receipt = dict(name=name, assignment=assignment, **outcome.summary.to_dict(),
                seconds=time.perf_counter()-start, config_sha256=hashlib.sha256(config.encode()).hexdigest(),
                result_sha256=hashlib.sha256(Path(outcome.result_path).read_bytes()).hexdigest(),
                detail=detail)
            print('SIM ' + json.dumps(receipt), flush=True)
            if name == 'baseline':
                print('RESULT_KEYS ' + json.dumps({k: (list(v) if isinstance(v, dict) else type(v).__name__) for k,v in raw.items()}), flush=True)
                print('BASELINE_ARTIFACT_ROWS ' + json.dumps([s for s in config.splitlines() if ' add stats ' in s or ' add set=' in s]), flush=True)
    after = load_active_gcsim_optimizer_engine_context()
    if (engine.engine_id, engine.artifact_sha256) != (after.engine_id, after.artifact_sha256):
        raise ValueError('Engine changed during comparison')


if __name__ == '__main__':
    main()
