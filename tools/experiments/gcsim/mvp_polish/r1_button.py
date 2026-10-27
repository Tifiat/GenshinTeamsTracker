"""One R1 consumer and the existing full-account AppShell button gate.

Preparation performs no engine calls. The live managed owner waits for explicit
off/on/release files; it never starts the next numerical arm automatically.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from tools import managed_optimizer_experiment as managed
from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
from run_workspace.gcsim.optimizer_go_contracts import canonical_sha256
from . import mechanic_button_gate as gate
from . import mechanic_corpus_inputs as inputs
from . import mechanic_uptake as uptake
from . import r1_single_trace as source
from . import whole_chasca_button as transport
from . import whole_chasca_target as target
from .mechanic_packet_evidence import write_json
from .mechanic_cache_packet import warm_status

ROOT, OUT = source.ROOT, source.OUT
GO = Path(r'C:\Program Files\Go\bin\go.exe')
OPTIONS = {'set_group_limit': 3, 'builds_per_group': 3, 'fast_mode': False}
SEEDS = [742031889, 742031890]
CHILD = 'tools.experiments.gcsim.mvp_polish.r1_button.R1ButtonExecutionTest.test_one_case'
WATCHDOG = 2700
LIFETIME = 10800


def preflight():
    images = source.native_images()
    mapping = {k: hashlib.sha256(v).hexdigest() for k, v in sorted(images.items())}
    row = next(r for r in inputs.resolve_inputs()['rows'] if r['case_id'] == 'chasca_600_fixture')
    if row['status'] != 'ready' or [p['character_key'] for p in row['profiles']] != ['chasca', 'furina', 'bennett', 'ororon']:
        raise ValueError('saved Chasca material/order unavailable')
    control_path = ROOT / 'docs/optimizer-evidence/2026-10-25-cache-team-matrix/corpus-main14-v2/chasca_600_fixture-all_sets/on.json'
    control = json.loads(control_path.read_bytes())
    old_config = ROOT / 'docs/optimizer-evidence/2026-10-25-cache-team-matrix/resolved-v2/chasca_600_fixture-config.json'
    retained_path = ROOT / 'docs/optimizer-evidence/2026-10-26-response-pilot/calibration-reuse-v1-inputs.json'
    retained = json.loads(retained_path.read_bytes())['request']
    public = control['public_inputs']
    profiles, _, rotation = inputs.archived_profiles(retained)
    by_key = {p['character_key']: p for p in row['profiles']}
    target_texts = [m.group(0).strip() + '\n' for m in re.finditer(r'(?im)^\s*target\b[^;]*;', row['rotation_text'])]
    if (public['source_profiles_sha256'] != inputs.digest(row['profiles'])
            or public['rotation_sha256'] != row['rotation_sha256'] or rotation != row['rotation_text']
            or public['source_config_sha256'] != gate._sha(old_config) or json.loads(old_config.read_bytes()) != row['source_config']
            or len(target_texts) != 1 or target_texts[0] != retained['context']['target']['text']
            or any(any(by_key[p['character_key']][k] != v for k, v in p.items()) for p in profiles)):
        raise ValueError('R1 material/rotation/target differs from saved full-account Chasca controls')
    provenance = {'control_receipt': str(control_path.relative_to(ROOT)), 'control_sha256': gate._sha(control_path),
        'retained_input_sha256': gate._sha(retained_path), 'source_profiles_sha256': public['source_profiles_sha256'],
        'source_config_sha256': public['source_config_sha256'], 'target_sha256': retained['context']['target']['sha256'],
        'profiles_weapons_levels_constellations_rotation_target_match': True,
        'legacy_case_id_scope': 'saved full-account control material; artifacts freshly frozen through production loader'}
    return images, row, {'source_image_sha256': canonical_sha256(mapping),
        'source_images': mapping, 'result_options': OPTIONS, 'seeds': SEEDS,
        'rotation_sha256': row['rotation_sha256'], 'material_sha256': row['material_sha256'],
        'source_pins': row['source_pins'], 'control_provenance': provenance, 'engine_calls': 0}


def stage_producer(job):
    live = uptake._store(ROOT).root_dir
    before = load_active_gcsim_optimizer_engine_context(store_dir=live)
    if not before.trusted or before.artifact_sha256 != source.ENGINE_SHA:
        raise ValueError('R1 requires the accepted compatible f1e producer')
    store = job / 'engine-store'
    engine = store / 'engines' / before.engine_id
    shutil.copytree(Path(before.engine_root), engine)
    # Existing uptake relocates only the generated absolute-path overlay and
    # reseals its manifest; all executable and semantic source bytes are checked.
    uptake._prepare_candidate(engine)
    shutil.copy2(live / 'active_engine.json', store / 'active_engine.json')
    after = load_active_gcsim_optimizer_engine_context(store_dir=store)
    if not after.trusted or after.artifact_sha256 != before.artifact_sha256:
        raise ValueError('owned producer copy differs from accepted source/binary binding')
    return store, after.to_dict()


def preserved_state():
    database, profile, _ = gate._active_source(ROOT)
    files = (database, ROOT / 'data/profiles/registry.json',
        ROOT / 'data/gcsim/engines/active_engine.json', ROOT / 'native/gcsim_optimizer/gtt-optimizer.exe')
    return {'active_profile_sha256': profile,
        'files': {str(p): gate._sha(p) if p.is_file() else None for p in files}}


@contextmanager
def retain_child_runs(job, arm, scratch_factory):
    """Move raw runs once, after the child has joined and receipts were read."""
    def retained(root):
        @contextmanager
        def scope():
            with scratch_factory(root) as child:
                try:
                    yield child
                finally:
                    destination = job / 'raw' / arm
                    destination.mkdir(parents=True, exist_ok=False)
                    for name in ('saved-runs', 'case-summary.json', 'child-bootstrap.log'):
                        path = child / name
                        managed.assert_unlinked(path)
                        if path.exists():
                            shutil.move(str(path), str(destination / name))
        return scope()
    yield retained


class R1ButtonExecutionTest(unittest.TestCase):
    def test_one_case(self):
        from tests.tools import test_optimizer_archetype_button_cases as button
        from run_workspace.gcsim import optimizer_go_session as session
        enabled = os.environ['GTT_MECHANIC_TEST_CACHE_ENABLED'] == '1'
        observed = {}
        with gate.install_child_adapter(button), ExitStack() as stack:
            worker_type = button.GcsimBrowserSelectedOptimizerWorker

            class ObservedWorker(worker_type):
                def __init__(self, request):
                    if {k: getattr(request, k) for k in OPTIONS} != OPTIONS or list(request.seeds) != SEEDS:
                        raise ValueError('actual R1 worker options/seeds differ')
                    super().__init__(transport.prepare_worker_request(request, enabled, observed))
                    transport.observe_worker_request(self, enabled, observed)

            stack.enter_context(patch.object(button, 'GcsimBrowserSelectedOptimizerWorker', ObservedWorker))
            stack.enter_context(patch.object(session, 'start_optimizer_process', side_effect=transport.observe_launcher(
                session.start_optimizer_process, observed, enabled, dict(os.environ))))
            try:
                result = unittest.TestResult()
                button.ArchetypeRealButtonExecutionTest('test_one_real_button_case').run(result)
                if not result.wasSuccessful() or result.testsRun != 1:
                    raise AssertionError('R1 full-account button failed; inspect retained child/native reports')
                if [r['stage'] for r in observed.get('native_launch_environments', [])] != ['validate-request', 'optimize-all-sets']:
                    raise ValueError('R1 actual native launch observations incomplete')
            finally:
                write_json(Path(os.environ['GTT_R1_OBSERVATIONS']), observed)


def summarize(job, arm, result, output):
    raw = job / 'raw' / arm
    paths = list(raw.rglob('all-sets-result.json'))
    evidence = {'arm': arm, 'status': result.get('status'), 'error_code': result.get('error_code'),
        'raw_root': str(raw), 'button_ms': result.get('case', {}).get('timings_ms', {}).get('button_click_to_terminal_ms'),
        'warm': warm_status(result)}
    if len(paths) == 1:
        path = paths[0]
        native = json.loads(path.read_bytes())
        request = json.loads((path.parent.parent / 'request.json').read_bytes())
        if request['result_options'] != OPTIONS or request['stochastic']['seeds'] != SEEDS:
            raise ValueError('actual R1 request options/seeds differ')
        counters = json.loads((path.parent / 'whole-search-counters.json').read_bytes())
        transport.validate_counters(counters, 'wall_and_counts')
        rows = transport.measured_rows(request, native)
        evidence.update(counters=counters, measured_builds=rows, actual_simulated_finalists=len(rows),
            actual_published_finalists=len(native.get('product_result', {}).get('candidates', [])),
            canonical_request_sha256=canonical_sha256(request), result_sha256=gate._sha(path),
            result_options=request['result_options'], seeds=request['stochastic']['seeds'],
            artifact_count=len(request['artifacts']),
            native={k: native.get(k) for k in ('search_seconds', 'source_preparation_seconds', 'total_elapsed_ms',
                'search_stop_reason', 'capture_members', 'search_work', 'neutral_cycles', 'neutral_model',
                'provider_timings', 'neutral_joint_seconds', 'neutral_package_joint', 'neutral_stabilization',
                'rule_parse_cache', 'support_response')})
        if len(rows) != 9 or evidence['actual_published_finalists'] != 9:
            evidence.update(status='anomaly_reduced_output', error_code='r1_expected_nine_measured_and_published')
    elif result.get('status') == 'success':
        raise ValueError('R1 successful button must retain exactly one native result')
    write_json(output / (arm + '-details.json'), evidence)
    return {k: v for k, v in evidence.items() if k not in ('native', 'counters', 'measured_builds')}


def run_arm(job, output, arm, frozen, row, store, consumer, watchdog):
    enabled = arm != 'off'
    original_env, scratch_factory = gate.run_case._child_environment, gate.run_case.managed_scratch

    def environment(*args, **kwargs):
        env = original_env(*args, **kwargs)
        env.update(GTT_R1_SINGLE_NEUTRAL='1', GTT_WHOLE_CHASCA_COUNTERS='1',
            GTT_R1_OBSERVATIONS=str(output / (arm + '-observations.json')))
        for key in tuple(env):
            if key.startswith('GTT_C4_'):
                env.pop(key)
        return env

    def same_snapshot(*, job: Path, **_):
        origin = Path(frozen['path'])
        if gate._sha(origin) != frozen['sha256']:
            raise ValueError('frozen full-account snapshot changed')
        copy = job / 'account-inventory-snapshot.db'
        shutil.copyfile(origin, copy)
        if gate._sha(copy) != frozen['sha256']:
            raise ValueError('arm snapshot copy differs')
        return {**frozen, 'path': copy}

    with retain_child_runs(job, arm, scratch_factory) as retention, ExitStack() as stack:
        stack.enter_context(patch.object(gate.run_case, 'managed_scratch', retention))
        stack.enter_context(patch.object(gate.run_case, '_child_environment', environment))
        stack.enter_context(patch.object(gate, 'snapshot_active_inventory', same_snapshot))
        stack.enter_context(patch.object(gate, 'CHILD_TEST', CHILD))
        stack.enter_context(patch.dict(os.environ, {inputs.ENV_KEY: str(job / 'case.json')}))
        cache = job / 'benchmark-rule-cache'
        result = gate.run_one(suite_root=job, project_root=ROOT, consumer=consumer, engine_store=store,
            source_config=ROOT / row['source_config_file'], case_id=row['case_id'], mode='all_sets',
            cache_flag=('reuse' if cache.exists() and any(cache.iterdir()) else 'cold') if enabled else 'off',
            cache_enabled=enabled, receipt_output=output / (arm + '.json'), lease_id=output.name + '-' + arm,
            test_watchdog_seconds=watchdog)
    return summarize(job, arm, result, output)


def prepare_and_wait(output):
    output = Path(output).absolute()
    output.relative_to(OUT)
    managed.assert_unlinked(output)
    output.mkdir(exist_ok=False)
    images, row, packet = preflight()
    before = preserved_state()
    harness_files = [Path(__file__), Path(transport.__file__), Path(gate.__file__), Path(inputs.__file__)]
    harness = {str(p.relative_to(ROOT)): gate._sha(p) for p in harness_files}
    record = {'schema': 'r1_single_trace_button_v1', 'status': 'preparing', 'arms': [],
        'started': time.time(), 'deadline': time.time() + LIFETIME, 'packet': packet,
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_closure': 'accepted403 reconstruction/helper chain; not standalone checkout',
        'harness_files': harness, 'preservation_sha256': canonical_sha256(before),
        'installations': 0, 'producer_builds': 0, 'consumer_builds': 0}
    def save(): write_json(output / 'owner.json', record)
    save()
    with managed.managed_scratch() as job:
        record['job'] = str(job)
        try:
            store, binding = stage_producer(job)
            record['producer'] = binding
            frozen = gate.snapshot_active_inventory(job=job, project_root=ROOT, engine_store=store)
            record['inventory'] = {k: v for k, v in frozen.items() if k != 'path'}
            for field, suffix in (('rotation_text', '-rotation.txt'), ('source_config', '-config.json')):
                path = output / ('chasca' + suffix)
                if field == 'rotation_text': path.write_bytes(row.pop(field).encode())
                else: write_json(path, row.pop(field))
                row['rotation_file' if field == 'rotation_text' else 'source_config_file'] = path.relative_to(ROOT).as_posix()
                if field == 'source_config': row['source_config_sha256'] = gate._sha(path)
            write_json(job / 'case.json', row)
            (job / 'bundled-mechanics').mkdir()
            bundle = ROOT / 'native/gcsim_optimizer/set-rule-cache'
            if bundle.is_dir(): shutil.copytree(bundle, job / 'bundled-mechanics', dirs_exist_ok=True)
            module = job / 'native/gcsim_optimizer'
            module.mkdir(parents=True)
            for name in ('go.mod', 'go.sum'):
                original = ROOT / 'native/gcsim_optimizer' / name
                if original.is_file(): shutil.copyfile(original, module / name)
            for name, raw in images.items():
                path = module / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            temp = job / 'temp'
            temp.mkdir()
            env = dict(os.environ, GOTOOLCHAIN='local', GOMAXPROCS='2', GOMEMLIMIT='2GiB',
                GOFLAGS='-p=2 -mod=readonly', GOTMPDIR=str(temp), TMP=str(temp), TEMP=str(temp),
                GTT_SCRATCH_DIR=str(job), PYTHONDONTWRITEBYTECODE='1')
            snapshot = json.loads((ROOT / 'docs/optimizer-evidence/2026-10-26-response-pilot/whole-search-chasca-v3-target-snapshot.json').read_bytes())
            env = target.pin_target(env, snapshot)
            consumer = job / 'gtt-optimizer.exe'
            started = time.monotonic()
            record['phase'] = 'consumer_build'
            save()
            with (output / 'consumer-build.log').open('w', encoding='utf-8') as log:
                subprocess.run([str(GO), '-C', str(module), 'build', '-trimpath', '-buildvcs=false', '-o', str(consumer), './cmd/gtt-optimizer'],
                    env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
            record.update(consumer_builds=1, consumer_build_seconds=time.monotonic() - started,
                consumer_sha256=gate._sha(consumer), consumer_target=target.assert_binary_target(snapshot, target.inspect_binary(GO, consumer, env, ROOT)),
                producer_target=target.assert_binary_target(snapshot, target.inspect_binary(GO, Path(binding['artifact_path']), env, ROOT)))
            record.update(status='prepared_waiting_root', phase='review', engine_calls=0)
            save()
            print(json.dumps({'status': record['status'], 'owner': str(output / 'owner.json')}), flush=True)
            while time.time() < record['deadline'] - 300:
                if (job / 'release').exists(): break
                arm = 'off' if not record['arms'] else 'on' if len(record['arms']) == 1 else None
                if len(record['arms']) == 2:
                    warm = record['arms'][1]['warm']
                    if not warm['confirmed_no_new_compile'] and any(warm['ir'].get(k, 0) > 0 for k in ('semantic_analyses', 'misses')):
                        arm = 'warm'
                if arm is None: time.sleep(1); continue
                command = job / arm
                if not command.exists(): time.sleep(1); continue
                command.unlink()
                if any(a['status'] != 'success' for a in record['arms']) or len(record['arms']) >= 3:
                    raise ValueError('first anomaly or completed pair holds further arms')
                if {str(p.relative_to(ROOT)): gate._sha(p) for p in harness_files} != harness or preserved_state() != before:
                    raise ValueError('frozen harness or protected account/runtime changed')
                record.update(status='running_' + arm, phase=arm)
                save()
                result = run_arm(job, output, arm, frozen, row, store, consumer,
                    min(WATCHDOG, int(record['deadline'] - time.time() - 360)))
                record['arms'].append(result)
                record.update(status=arm + '_complete_waiting_root', phase='review')
                save()
                print(json.dumps({'status': record['status'], 'arm_status': result['status']}), flush=True)
        except BaseException as error:
            record.update(status='failure_waiting_root', error_class=type(error).__name__, error=str(error)[:4096])
            save()
            print(json.dumps({'status': record['status'], 'error': record['error']}), flush=True)
            while time.time() < record['deadline'] - 300 and not (job / 'release').exists(): time.sleep(1)
        finally:
            record['protected_exact'] = preserved_state() == before
            record['cleanup_started'] = time.time()
            save()
    record.update(job_removed=not job.exists(), owner_finished=time.time(), status='closed_' + record['status'])
    save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--action', choices=('prepare', 'off', 'on', 'warm', 'release'), required=True)
    args = parser.parse_args()
    if args.action == 'prepare': prepare_and_wait(args.output)
    else:
        record = json.loads((args.output / 'owner.json').read_bytes())
        job = Path(record['job'])
        managed.assert_unlinked(job)
        if job.parent != managed.MANAGED_ROOT or not job.name.startswith('job-') or time.time() >= record['deadline'] - 300:
            raise ValueError('R1 live finite managed owner unavailable')
        (job / args.action).touch(exist_ok=False)


if __name__ == '__main__': main()
