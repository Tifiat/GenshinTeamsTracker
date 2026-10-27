"""The existing R2 real button owner with exactly five admitted R3 toggles."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from . import r2_button as previous
from . import r3_engineering as source
from .mechanic_packet_evidence import write_json

base, ROOT, OUT = previous.base, source.ROOT, source.OUT
PREVIOUS = ROOT / 'docs/optimizer-evidence/2026-10-27-staged-finalists/run-v1/owner.json'
FLAGS = {name: '1' for name in ('GTT_R3_PARALLEL_CAPTURE', 'GTT_R3_TYPED_CANONICAL',
         'GTT_R3_ADJOINT_REUSE', 'GTT_R3_PROGRAM_IDENTITY', 'GTT_R3_OPERATION_SWITCH')}
CHILD = 'tools.experiments.gcsim.mvp_polish.r3_button.R3ButtonExecutionTest.test_one_case'
_run_arm = previous._run_arm


def preflight():
    # Reuse the R1 material/rotation/target proof with our recovered native
    # closure. No historical native source helper is needed for this route.
    with patch.object(base.source, 'native_images', source.native_images):
        images, row, packet = previous._preflight()
    paths = [Path(__file__), Path(source.__file__), Path(previous.__file__),
             Path(__file__).with_name('r2_result_text.py'), Path(__file__).with_name('r3_recovery.py'),
             Path(__file__).with_name('seed_member_typed_canonical_parity_test.go'),
             OUT / 'r2-source-delta-v1.patch', OUT / 'r2-source-delta-v1.json']
    paths += sorted(Path(__file__).parent.glob('r3_*.go'))
    packet.update(experiment='R3_engineering_efficiency', parent_r2_source_image_sha256=source.R2_MAP,
                  r3_harness_files={p.relative_to(ROOT).as_posix(): base.gate._sha(p) for p in paths},
                  r3_flags=FLAGS, permitted_arms=['off'], cache_enabled=False, cpu_budget=os.cpu_count(),
                  policy='Unchanged R2 search/coverage/77 intermediate checks/3x3/two seeds/n100-n500 four-SE',
                  source_recovery='6f1cab8 plus r2-source-delta-v1, exact411-map; optional local zip')
    if os.cpu_count() != 16:
        raise ValueError('R3 comparison requires the same16CPU budget')
    return images, row, packet


class R3ButtonExecutionTest(unittest.TestCase):
    def test_one_case(self):
        from run_workspace.gcsim import optimizer_go_session as session
        if any(os.environ.get(k) != v for k, v in FLAGS.items()):
            raise ValueError('R3 child process flags differ')
        observed = []
        original = session.start_optimizer_process

        def launcher(argv, *args, **kwargs):
            env = kwargs.get('env') or {}
            if any(env.get(k) != v for k, v in FLAGS.items()):
                raise ValueError('actual R3 native process flags differ')
            observed.append({'stage': argv[1], 'r3_flags': {k: env[k] for k in FLAGS}})
            return original(argv, *args, **kwargs)

        try:
            with patch.object(session, 'start_optimizer_process', launcher):
                previous.R2ButtonExecutionTest('test_one_case').test_one_case()
            if [r['stage'] for r in observed] != ['validate-request', 'optimize-all-sets']:
                raise ValueError('R3 native launch observations incomplete')
        finally:
            write_json(Path(os.environ['GTT_R3_OBSERVATIONS']), observed)


def summarize(job, arm, result, output):
    compact = previous.summarize(job, arm, result, output)
    path = output / (arm + '-details.json')
    evidence = json.loads(path.read_bytes())
    evidence.update(schema='r3_engineering_button_result_v1', r3_flags=FLAGS)
    if result.get('status') == 'success':
        counts = evidence['counters']['Counts']
        phases = evidence['counters']['Phases']
        if (counts.get('r3.capture_batch_workers') != 2 or counts.get('engine.compact.process_attempts') != 2
                or counts.get('engine.compact.process_exit_success') != 2
                or counts.get('r1.neutral_models') != 1 or phases.get('r3.capture_batch_wall', {}).get('Calls') != 1):
            raise ValueError('R3 expected one parallel2seed neutral batch')
        evidence['capture_timing_scope'] = 'r3.capture_batch_wall overlaps per-seed process/decode sums; no additive speed claim'
    write_json(path, evidence)
    compact.update(schema=evidence['schema'], r3_flags=FLAGS)
    return compact


def checked_arm(job, output, arm, *args):
    if arm != 'off':
        raise ValueError('R3 authorizes exactly one OFF')
    owner = json.loads((output / 'owner.json').read_bytes())
    packet = owner['packet']
    if owner.get('arms') or packet.get('r3_flags') != FLAGS:
        raise ValueError('R3 one-OFF contract or frozen flags differ')
    for name, sha in packet['r3_harness_files'].items():
        if base.gate._sha(ROOT / name) != sha:
            raise ValueError('frozen R3 harness/source changed')
    original_env = base.gate.run_case._child_environment

    def environment(*args, **kwargs):
        env = original_env(*args, **kwargs)
        env.update(FLAGS)
        env['GTT_R3_OBSERVATIONS'] = str(output / (arm + '-r3-observations.json'))
        return env

    with patch.object(base.gate.run_case, '_child_environment', environment):
        return _run_arm(job, output, arm, *args)


def prepare(output):
    reference = json.loads(PREVIOUS.read_bytes())['inventory']
    snapshot = base.gate.snapshot_active_inventory

    def frozen_inventory(**kwargs):
        current = snapshot(**kwargs)
        for key in ('profile_id_sha256', 'artifact_input_sha256', 'artifact_count', 'eligible_count'):
            if current[key] != reference[key]:
                raise ValueError('R3 full-account input differs from R2: ' + key)
        return current

    with ExitStack() as stack:
        for name, value in [('OUT', OUT), ('preflight', preflight), ('CHILD', CHILD),
                            ('run_arm', checked_arm), ('summarize', summarize)]:
            stack.enter_context(patch.object(base, name, value))
        stack.enter_context(patch.object(base.gate, 'snapshot_active_inventory', frozen_inventory))
        base.prepare_and_wait(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--action', choices=('prepare', 'off', 'release'), required=True)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.output)
    else:
        if args.action == 'off':
            owner = json.loads((args.output / 'owner.json').read_bytes())
            if owner.get('arms') or owner['packet'].get('r3_flags') != FLAGS:
                raise ValueError('R3 OFF already completed or flags differ')
        with patch.object(os.sys, 'argv', [__file__, '--output', str(args.output), '--action', args.action]):
            base.main()


if __name__ == '__main__':
    main()
