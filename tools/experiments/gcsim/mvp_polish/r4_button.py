"""R4 three-module configuration of the existing R3 full-account button owner."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from . import r3_button as previous
from . import r4_redundant as source
from .mechanic_packet_evidence import write_json

base, ROOT, OUT = previous.base, source.ROOT, source.OUT
PREVIOUS = OUT / 'run-v1/owner.json'
FLAGS = {**previous.FLAGS, **{k: '1' for k in ('GTT_R4_OWNED_DIGEST', 'GTT_R4_TYPED_PANEL', 'GTT_R4_FAST_COUNTERS')}}
CHILD = 'tools.experiments.gcsim.mvp_polish.r4_button.R4ButtonExecutionTest.test_one_case'
_run_arm = previous._run_arm


def preflight():
    _, row, packet = previous.preflight()
    images = source.native_images()
    mapping = {k: hashlib.sha256(v).hexdigest() for k, v in sorted(images.items())}
    paths = [Path(__file__), Path(source.__file__)]
    compiled_names = {Path(k).name for k in images}
    paths += [p for p in sorted(Path(__file__).parent.glob('r4_*.go')) if p.name in compiled_names]
    packet.update(experiment='R4_redundant_operations', parent_r3_source_image_sha256=source.R3_MAP,
                  source_images=mapping, source_image_sha256=base.canonical_sha256(mapping),
                  r4_harness_files={p.relative_to(ROOT).as_posix(): base.gate._sha(p) for p in paths},
                  r4_flags=FLAGS, accepted_r4_modules=['owned_raw_digest', 'typed_panel_canonical', 'fixed_atomic_counters'],
                  rejected_r4_module='dirty frontier: no established time benefit on retained input; production region/fork exact R3',
                  retained_validation='Public mutable member slices; public compiler semantic validation preserved')
    return images, row, packet


class R4ButtonExecutionTest(unittest.TestCase):
    def test_one_case(self):
        from run_workspace.gcsim import optimizer_go_session as session
        if any(os.environ.get(k) != v for k, v in FLAGS.items()) or 'GTT_R4_DIRTY_REGIONS' in os.environ:
            raise ValueError('R4 child flags differ')
        observed = []
        original = session.start_optimizer_process

        def launcher(argv, *args, **kwargs):
            env = kwargs.get('env') or {}
            if any(env.get(k) != v for k, v in FLAGS.items()) or 'GTT_R4_DIRTY_REGIONS' in env:
                raise ValueError('actual R4 native flags differ')
            observed.append({'stage': argv[1], 'flags': {k: env[k] for k in FLAGS}, 'dirty_frontier': 'excluded'})
            return original(argv, *args, **kwargs)

        try:
            with patch.object(session, 'start_optimizer_process', launcher):
                previous.R3ButtonExecutionTest('test_one_case').test_one_case()
            if [r['stage'] for r in observed] != ['validate-request', 'optimize-all-sets']:
                raise ValueError('R4 native observations incomplete')
        finally:
            write_json(Path(os.environ['GTT_R4_OBSERVATIONS']), observed)


def summarize(job, arm, result, output):
    compact = previous.summarize(job, arm, result, output)
    path = output / (arm + '-details.json')
    evidence = json.loads(path.read_bytes())
    evidence.update(schema='r4_redundant_button_result_v1', r4_flags=FLAGS,
                    dirty_frontier='excluded; source region_binding/theory_fork exact R3')
    write_json(path, evidence)
    compact.update(schema=evidence['schema'], r4_flags=FLAGS)
    return compact


def checked_arm(job, output, arm, *args):
    if arm != 'off':
        raise ValueError('R4 authorizes one OFF only')
    owner = json.loads((output / 'owner.json').read_bytes())
    packet = owner['packet']
    if owner.get('arms') or packet.get('r4_flags') != FLAGS:
        raise ValueError('R4 one-OFF contract/flags differ')
    for group in ('r3_harness_files', 'r4_harness_files'):
        for name, sha in packet[group].items():
            if base.gate._sha(ROOT / name) != sha:
                raise ValueError('frozen R4 source/harness changed')
    original_env = base.gate.run_case._child_environment

    def environment(*args, **kwargs):
        env = original_env(*args, **kwargs)
        env.update(FLAGS)
        env.pop('GTT_R4_DIRTY_REGIONS', None)
        env['GTT_R3_OBSERVATIONS'] = str(output / (arm + '-r3-observations.json'))
        env['GTT_R4_OBSERVATIONS'] = str(output / (arm + '-r4-observations.json'))
        return env

    with patch.object(base.gate.run_case, '_child_environment', environment):
        return _run_arm(job, output, arm, *args)


def prepare(output):
    reference = json.loads(PREVIOUS.read_bytes())['inventory']
    snapshot = base.gate.snapshot_active_inventory

    def frozen_inventory(**kwargs):
        current = snapshot(**kwargs)
        for key in ('profile_id_sha256', 'artifact_input_sha256', 'artifact_count', 'eligible_count', 'set_domain_count'):
            if current[key] != reference[key]:
                raise ValueError('R4 full-account input differs from R3: ' + key)
        return current

    with ExitStack() as stack:
        for name, value in [('OUT', OUT), ('preflight', preflight), ('CHILD', CHILD), ('run_arm', checked_arm), ('summarize', summarize)]:
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
            if owner.get('arms') or owner['packet'].get('r4_flags') != FLAGS:
                raise ValueError('R4 OFF already completed or flags differ')
        with patch.object(os.sys, 'argv', [__file__, '--output', str(args.output), '--action', args.action]):
            base.main()


if __name__ == '__main__':
    main()
