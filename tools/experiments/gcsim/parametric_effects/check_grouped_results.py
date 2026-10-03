"""Bounded saved-input grouped/fast result gate through the product adapter.

Run only inside managed_optimizer_experiment.py. All expanded captures, source
envelopes and build products stay in its owned job; only stdout summaries are
retained in the dated handoff receipt. No account/settings writes. Keep this
reproducer through grouped-result UI acceptance, then retire with its research
helpers. It never silently installs a candidate.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.managed_optimizer_experiment import owned_job
from run_workspace.gcsim.optimizer_go_contracts import canonical_sha256


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_result(result, options):
    assert result['status'] == 'success'
    assert result['ranking_basis'] == ('formula' if options['fast_mode'] else 'gcsim')
    rows = result['candidates']
    assert 0 < len(rows) <= options['set_group_limit'] * options['builds_per_group']
    groups = {}
    identities = set()
    for row in rows:
        key = row['set_group_key']
        groups.setdefault(key, []).append(row)
        ids = tuple((x['wearer_key'], x['slot'], x['artifact_id']) for x in row['artifacts'])
        assert len(ids) == 20 and len({x[2] for x in ids}) == 20 and ids not in identities
        identities.add(ids)
        if options['fast_mode']:
            assert 'measured' not in row and not row.get('formula_residual')
        else:
            assert row['measured']['iterations'] == 500
    assert len(groups) <= options['set_group_limit']
    assert all(len(rows) <= options['builds_per_group'] for rows in groups.values())
    for group in groups.values():
        anchor = {(x['wearer_key'], x['slot']): x['artifact_id'] for x in group[0]['artifacts']}
        for row in group[1:]:
            assert sum(anchor[(x['wearer_key'], x['slot'])] != x['artifact_id'] for x in row['artifacts']) == 1
    if options['fast_mode']:
        assert 'measured' not in result and not result.get('formula_residual')
        assert 'formula_only_unverified' in result['warnings']


@contextmanager
def checked_install(candidate, expected_sha, job):
    """Promote only a previously tested byte-identical consumer; rollback on failure."""
    if not expected_sha:
        yield
        return
    from run_workspace.gcsim.optimizer_go_selected import DEFAULT_OPTIMIZER_BINARY
    installed = Path(DEFAULT_OPTIMIZER_BINARY).resolve(strict=True)
    assert file_sha(candidate) == expected_sha, 'Candidate differs from passed source gate'
    backup = job / 'previous-consumer.exe'
    shutil.copy2(installed, backup)
    old_sha = file_sha(backup)
    shutil.copy2(candidate, installed)
    try:
        yield
    except BaseException:
        shutil.copy2(backup, installed)
        assert file_sha(installed) == old_sha
        print('GROUP_INSTALL_ROLLBACK ' + old_sha, flush=True)
        raise
    else:
        print('GROUP_INSTALL_PASS ' + json.dumps(dict(previous_sha256=old_sha,
            installed_sha256=file_sha(installed))), flush=True)


def main():
    job = owned_job()
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--saved-run', type=Path, required=True)
    parser.add_argument('--mode', choices=['all_sets', 'selected'], required=True)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--build-candidate', action='store_true')
    parser.add_argument('--native-tests', action='store_true', help='Run native regressions in this same managed build cache first')
    parser.add_argument('--cache-benchmark', action='store_true', help='Measure parsing versus persistent decoding, outside replay timing')
    parser.add_argument('--schedule-capture-test', action='store_true', help='Opt-in two-seed neutral/changed-schedule engine regression before replay')
    parser.add_argument('--prepare-shipped-cache', action='store_true', help='Prepare source-only distribution cache before replay; no engine simulation')
    parser.add_argument('--install-tested-sha', help='Require matching passed candidate, install, use default button path; rollback if gate fails')
    parser.add_argument('--groups', type=int, default=3)
    parser.add_argument('--alternatives', type=int, default=2)
    parser.add_argument('--fast', action='store_true')
    parser.add_argument('--expanded', action='store_true')
    parser.add_argument('--compare-saved', action='store_true', help='Report exact ID/formula parity with saved fast output')
    parser.add_argument('--profile', action='store_true', help='Managed CPU profile; diagnostic timing is not a product benchmark')
    parser.add_argument('--warm-rule-cache', action='store_true', help='Prepare all source ASTs before the timed gate')
    parser.add_argument('--compact-output', action='store_true', help='Keep IDs in the scratch receipt; print their digest instead')
    args = parser.parse_args()
    if args.build_candidate:
        if args.binary is not None:
            parser.error('--binary and --build-candidate are mutually exclusive')
        args.binary = job / 'gtt-optimizer.exe'
        go = shutil.which('go') or str(Path('C:/Program Files/Go/bin/go.exe'))
        if args.native_tests:
            env = dict(os.environ, GTT_RULE_SOURCE_BUNDLE=str(args.saved_run.resolve(strict=True) / 'set-sources.json'))
            subprocess.run([go, '-C', str(ROOT / 'native/gcsim_optimizer'), 'test', './...',
                            '-count=1', '-timeout=180s'], env=env, check=True)
        if args.cache_benchmark:
            subprocess.run([go, '-C', str(ROOT / 'native/gcsim_optimizer'), 'test', './internal/seteffects',
                            '-run=^$', '-bench=BenchmarkRuleParseCacheFreshParseVsDiskWarmDecode',
                            '-benchmem', '-benchtime=200ms', '-count=2'], check=True)
        if args.schedule_capture_test:
            from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
            source_request = json.loads((args.saved_run / 'request.json').read_text(encoding='utf-8'))
            active = load_active_gcsim_optimizer_engine_context()
            assert active.artifact_sha256 == source_request['engine']['artifact_sha256']
            assert Path(active.artifact_path).resolve() == Path(source_request['engine']['binary_path']).resolve()
            env = dict(os.environ, GTT_SCHEDULE_CAPTURE_SAVED_RUN=str(args.saved_run.resolve(strict=True)))
            subprocess.run([go, '-C', str(ROOT / 'native/gcsim_optimizer'), 'test', './internal/allsets',
                            '-run=TestScheduleRouterActiveEngine', '-count=1', '-v', '-timeout=180s'], env=env, check=True)
        subprocess.run([go, '-C', str(ROOT / 'native/gcsim_optimizer'), 'build',
                        '-o', str(args.binary), './cmd/gtt-optimizer'], check=True)
    if args.prepare_shipped_cache:
        if args.binary is None:
            parser.error('Preparing the shipped cache requires an explicit tested/build candidate')
        subprocess.run([sys.executable, str(ROOT / 'tools/prepare_optimizer_set_cache.py'),
                        '--request', str(args.saved_run / 'request.json'), '--binary', str(args.binary)], check=True)
    if args.install_tested_sha:
        if args.binary is None:
            parser.error('Install requires --build-candidate or --binary')
        args.binary.resolve(strict=True).relative_to(job)
    with checked_install(args.binary, args.install_tested_sha, job):
        if args.install_tested_sha:
            args.binary = None
        return run_gate(job, args)


def run_gate(job, args):
    from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
    from run_workspace.gcsim.optimizer_go_selected import GcsimOptimizerGoSelectedRequest, GcsimOptimizerGoSelectedSession
    from run_workspace.gcsim.optimizer_go_all import GcsimOptimizerGoAllSetsRequest, GcsimOptimizerGoAllSetsSession
    source = args.saved_run.resolve(strict=True)
    source.relative_to((ROOT / 'data/gcsim/optimizer-go-runs').resolve())
    source_path = source / 'request.json'
    source_sha = file_sha(source_path)
    req = json.loads(source_path.read_text(encoding='utf-8'))
    engine = load_active_gcsim_optimizer_engine_context()
    assert engine.artifact_sha256 == req['engine']['artifact_sha256']
    assert Path(engine.artifact_path).resolve() == Path(req['engine']['binary_path']).resolve()
    options = dict(set_group_limit=args.groups, builds_per_group=args.alternatives, fast_mode=args.fast)
    if args.expanded:
        options['expanded_limits'] = True
    req['result_options'] = options
    # Product now has no wall-clock budget; never replay obsolete saved timers.
    for key in ('product_timeout_ms', 'development_timeout_ms'):
        if key in req.get('budgets', {}):
            req['budgets'][key] = 0
    request_type, session_type = ((GcsimOptimizerGoAllSetsRequest, GcsimOptimizerGoAllSetsSession)
                                  if args.mode == 'all_sets' else
                                  (GcsimOptimizerGoSelectedRequest, GcsimOptimizerGoSelectedSession))
    kwargs = {} if args.binary is None else {'optimizer_binary_path': str(args.binary.resolve(strict=True))}
    request = request_type(db_path=str(ROOT / 'data/artifacts.db'), selected_team={}, team_index=0,
                           rotation_shell_text=req['context']['rotation']['text'], infinite_energy_enabled=True,
                           run_root=str(job / 'unused'), **options, **kwargs)
    binary = Path(request.optimizer_binary_path).resolve(strict=True)
    if args.binary is not None:
        binary.relative_to(job)
    binary_sha = file_sha(binary)
    work = job / f'grouped-{args.mode}-{args.groups}-{args.alternatives}-{int(args.fast)}'
    work.mkdir()
    raw = json.dumps(req, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    (work / 'request.json').write_bytes(raw)
    prepared = dict(request=req, request_sha256=canonical_sha256(req))
    started = time.monotonic()
    session = session_type(request, progress_callback=lambda row: print(
        f"GROUP_GATE {row.get('stage')} {row.get('elapsed_ms')}ms", flush=True))
    session._validate_optimizer_request(run_dir=work, started=started)
    compact = session._prepare_formula_inputs(prepared=prepared, run_dir=work, started=started)
    if args.warm_rule_cache:
        # The warm preparation is explicitly outside reported adapter timing.
        subprocess.run([str(binary), 'warm-set-cache', str(work / 'request.json'),
                        str(work / 'set-sources.json'), str(job / 'set-rule-cache')], check=True)
        started = time.monotonic()
    if args.profile:
        os.environ['GTT_OPTIMIZER_PROFILE'] = '1'
    result = session._run_go_optimizer(prepared=prepared, compact=compact, run_dir=work, started=started)
    elapsed_seconds = time.monotonic() - started
    if args.profile:
        os.environ.pop('GTT_OPTIMIZER_PROFILE', None)
        go = shutil.which('go') or str(Path('C:/Program Files/Go/bin/go.exe'))
        subprocess.run([go, 'tool', 'pprof', '-top', '-nodecount=25', str(binary), str(job / 'optimizer-cpu.pprof')], check=True)
    check_result(result, options)
    wrapper = json.loads((work / 'optimizer-output.json').read_text(encoding='utf-8'))
    if args.fast:
        assert not wrapper.get('verification')
        assert not (work / 'verification/final-n500').exists()
    assert file_sha(source_path) == source_sha and file_sha(binary) == binary_sha
    current_engine = load_active_gcsim_optimizer_engine_context()
    assert current_engine.engine_id == engine.engine_id and current_engine.artifact_sha256 == engine.artifact_sha256
    rows = [{key: row.get(key) for key in ('rank','set_group_key','set_group_rank','alternative_rank','formula_dps','measured','artifacts')}
            for row in result['candidates']]
    if args.compare_saved:
        saved_wrapper = json.loads((source / 'optimizer-output.json').read_text(encoding='utf-8'))
        saved_product = saved_wrapper.get('product_result', saved_wrapper.get('result', {}))
        if not saved_product.get('candidates'):
            raise ValueError('Saved wrapper has no recognizable product candidates')
        def signature(row):
            return tuple(sorted((x['wearer_key'], x['slot'], x['artifact_id']) for x in row['artifacts']))
        saved_scores = {signature(row): float(row['formula_dps']) for row in saved_product['candidates']}
        scores = {signature(row): float(row['formula_dps']) for row in rows}
        shared = saved_scores.keys() & scores.keys()
        print('GROUP_PARITY ' + json.dumps(dict(saved=len(saved_scores), current=len(scores), shared=len(shared),
            missing_saved=len(saved_scores.keys()-scores.keys()),
            max_shared_formula_delta=max((abs(saved_scores[key]-scores[key]) for key in shared), default=None),
            saved_best=max(saved_scores.values()), current_best=max(scores.values()))), flush=True)
    print('GROUP_RESULT ' + json.dumps(dict(success=True, mode=args.mode, options=options,
        default_button_binary=args.binary is None, binary_sha256=binary_sha, engine_id=engine.engine_id,
        engine_sha256=engine.artifact_sha256, source_request_sha256=source_sha,
        request_sha256=prepared['request_sha256'], elapsed_seconds=elapsed_seconds,
        search_seconds=wrapper.get('search_seconds'), search_stop=wrapper.get('search_stop_reason'),
        ranking_basis=result['ranking_basis'], warnings=result['warnings'],
        candidates=rows if not args.compact_output else len(rows),
        candidates_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),
        ordinary_count=len((wrapper.get('verification') or {}).get('candidates', [])),
        ordinary_seconds=(wrapper.get('verification') or {}).get('total_elapsed_ms',0)/1000,
        search_expansions=wrapper.get('search_expansions'),
        neutral_cycles=wrapper.get('neutral_cycles'),
        neutral_model=wrapper.get('neutral_model'),
        rule_parse_cache=wrapper.get('rule_parse_cache'),
        source_preparation_seconds=wrapper.get('source_preparation_seconds'),
        capture_members=wrapper.get('capture_members'),
        effect_boundaries=wrapper.get('effect_boundaries'),
        neutral_package_joint=wrapper.get('neutral_package_joint'),
        provider_timings=wrapper.get('provider_timings'),
        search_work_seconds_by_stage={stage:sum(row.get('SearchSeconds',0) for row in wrapper.get('search_work',[]) if row.get('lane','').split(':')[0]==stage)
            for stage in sorted({row.get('lane','').split(':')[0] for row in wrapper.get('search_work',[])})},
        neutral_unavailable=(wrapper.get('neutral_model') or {}).get('Unavailable')), ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
