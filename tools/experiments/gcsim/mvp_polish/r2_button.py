"""R2 configuration/export over the existing R1 managed full-account owner."""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from . import r1_button as base
from . import r2_staged_finalists as source
from .r2_result_text import format_staged_result
from .mechanic_packet_evidence import write_json

OUT, ROOT = source.OUT, source.ROOT
PREVIOUS = ROOT / 'docs/optimizer-evidence/2026-10-27-single-trace/run-v1/owner.json'
CHILD = 'tools.experiments.gcsim.mvp_polish.r2_button.R2ButtonExecutionTest.test_one_case'
_preflight, _run_arm = base.preflight, base.run_arm


def preflight():
    images, row, packet = _preflight()
    images = source.overlay(images)
    mapping = {k: hashlib.sha256(v).hexdigest() for k, v in sorted(images.items())}
    paths = [Path(__file__), Path(source.__file__), Path(__file__).with_name('r2_result_text.py'),
        Path(__file__).with_name('r2_staged_finalists.go')]
    packet.update(experiment='R2_staged_finalists', source_images=mapping,
        source_image_sha256=base.canonical_sha256(mapping),
        parent_r1_source_image_sha256=source.R1_MAP,
        r2_harness_files={p.relative_to(ROOT).as_posix(): base.gate._sha(p) for p in paths},
        policy='nine n100; pilot leader and four-SE contenders independent n500; recheck after each wave; max18calls/5400iterations',
        cache_enabled=False, permitted_arms=['off'], cpu_budget=os.cpu_count())
    if os.cpu_count() != 16: raise ValueError('R2 comparison requires the same16CPU budget')
    return images, row, packet


class R2ButtonExecutionTest(unittest.TestCase):
    def test_one_case(self):
        import ui.app_shell as shell
        with patch.object(shell, 'format_gcsim_optimizer_go_selected_result', format_staged_result):
            result = unittest.TestResult()
            base.R1ButtonExecutionTest('test_one_case').run(result)
            if not result.wasSuccessful() or result.testsRun != 1:
                raise AssertionError('R2 button failed; inspect retained native and staged receipts')


def summarize(job, arm, result, output):
    raw = job / 'raw' / arm
    paths = list(raw.rglob('all-sets-result.json'))
    evidence = {'schema': 'r2_staged_button_result_v1', 'arm': arm, 'status': result.get('status'),
        'error_code': result.get('error_code'), 'raw_root': str(raw),
        'button_ms': result.get('case', {}).get('timings_ms', {}).get('button_click_to_terminal_ms')}
    if len(paths) == 1:
        path = paths[0]
        native = json.loads(path.read_bytes())
        request = json.loads((path.parent.parent / 'request.json').read_bytes())
        verification = native['verification']
        staged = verification['staged']
        if (request['result_options'] != base.OPTIONS or request['stochastic']['seeds'] != base.SEEDS
                or staged['input_candidates'] != 9 or staged['status'] != 'completed'
                or verification['iterations'] != 0 or verification['winner']['iterations'] != 500):
            raise ValueError('R2 input/staged verification contract differs')
        rows = base.transport.measured_rows(request, native, allowed_iterations=(100, 500))
        product = native['product_result']
        measured_assignments = {tuple(x for owner in b['measurement']['assignment'] for x in owner) for b in rows}
        published = product['candidates']
        if not 1 <= len(published) <= 9 or product['measured']['iterations'] != 500:
            raise ValueError('R2 confirmed winner or bounded publication missing')
        for candidate in published:
            if tuple(a['artifact_id'] for a in candidate['artifacts']) not in measured_assignments:
                raise ValueError('published R2 candidate was not measured')
        counters = json.loads((path.parent / 'whole-search-counters.json').read_bytes())
        base.transport.validate_counters(counters, 'wall_and_counts')
        adaptive = native.get('adaptive_policy') or {}
        evidence.update(measured_builds=rows, actual_simulated_finalists=len(rows), actual_published_finalists=len(published),
            actual_final_inputs=staged['input_candidates'], counters=counters,
            verification={k: v for k, v in verification.items() if k != 'staged'}, staged_verification=staged,
            adaptive_policy={k: adaptive.get(k) for k in ('active', 'calls', 'engine_ms', 'engine_wall_ms', 'samples',
                'events', 'early_preparation', 'damped_preparation', 'secondary_refinement', 'final_pair_completion')},
            result_options=request['result_options'], seeds=request['stochastic']['seeds'], artifact_count=len(request['artifacts']),
            canonical_request_sha256=base.canonical_sha256(request), result_sha256=base.gate._sha(path),
            native={k: native.get(k) for k in ('search_seconds', 'source_preparation_seconds', 'total_elapsed_ms',
                'search_stop_reason', 'capture_members', 'search_work', 'neutral_cycles', 'neutral_model',
                'provider_timings', 'neutral_joint_seconds', 'neutral_package_joint', 'neutral_stabilization',
                'rule_parse_cache', 'support_response')})
    elif result.get('status') == 'success':
        raise ValueError('R2 successful result missing from retained raw')
    else:
        evidence['partial_stages'] = [json.loads(p.read_bytes()) for p in raw.rglob('verification-stages.json')]
    write_json(output / (arm + '-details.json'), evidence)
    return {k: v for k, v in evidence.items() if k not in ('native', 'counters', 'measured_builds', 'verification',
        'staged_verification', 'adaptive_policy', 'partial_stages')}


def checked_arm(job, output, arm, *args):
    if arm != 'off': raise ValueError('R2 authorizes one OFF only')
    owner = json.loads((output / 'owner.json').read_bytes())
    for name, sha in owner['packet']['r2_harness_files'].items():
        if base.gate._sha(ROOT / name) != sha: raise ValueError('frozen R2 harness/source changed')
    return _run_arm(job, output, arm, *args)


def prepare(output):
    previous = json.loads(PREVIOUS.read_bytes())['inventory']
    snapshot = base.gate.snapshot_active_inventory
    def frozen_inventory(**kwargs):
        current = snapshot(**kwargs)
        for key in ('profile_id_sha256', 'artifact_input_sha256', 'artifact_count', 'eligible_count'):
            if current[key] != previous[key]: raise ValueError('R2 full-account input differs from R1: ' + key)
        return current
    with ExitStack() as stack:
        stack.enter_context(patch.object(base, 'OUT', OUT))
        stack.enter_context(patch.object(base, 'preflight', preflight))
        stack.enter_context(patch.object(base, 'CHILD', CHILD))
        stack.enter_context(patch.object(base, 'run_arm', checked_arm))
        stack.enter_context(patch.object(base, 'summarize', summarize))
        stack.enter_context(patch.object(base.gate, 'snapshot_active_inventory', frozen_inventory))
        base.prepare_and_wait(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--action', choices=('prepare', 'off', 'release'), required=True)
    args = parser.parse_args()
    if args.action == 'prepare': prepare(args.output)
    else:
        with patch.object(os.sys, 'argv', [__file__, '--output', str(args.output), '--action', args.action]):
            base.main()


if __name__ == '__main__': main()
