"""Finite R5 native checks and retained-input costs, with zero engine calls."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path

from tools.managed_optimizer_experiment import managed_scratch
from . import r5_redundant as source
from .r3_offline import GO, command
from .r4_button import FLAGS
from .r3_recovery import map_sha, mapping


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--measure', action='store_true')
    parser.add_argument('--evaluate-confirm', action='store_true')
    parser.add_argument('--combined', action='store_true')
    args = parser.parse_args()
    output = source.OUT / (args.label + '.json')
    log = output.with_suffix('.log')
    if output.exists() or log.exists():
        raise FileExistsError(output)
    record = {'schema': 'r5_focused_v1', 'engine_calls': 0, 'search_calls': 0,
              'installed': False, 'status': 'started', 'commands': [], 'flags': FLAGS}
    logs = []
    with managed_scratch() as job:
        record['job'] = str(job)
        try:
            images = source.native_images()
            record.update(source_files=mapping(images), source_map_sha256=map_sha(images))
            module = job / 'native/gcsim_optimizer'
            for name, data in images.items():
                path = module / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            public = job / 'tests/fixtures/gcsim_optimizer_go_v1'
            public.mkdir(parents=True)
            record['public_fixtures'] = {}
            for name in ('request_v1.json', 'compact_ir_v1.json'):
                data = (source.ROOT / 'tests/fixtures/gcsim_optimizer_go_v1' / name).read_bytes()
                (public / name).write_bytes(data)
                record['public_fixtures'][name] = hashlib.sha256(data).hexdigest()
            cache, temporary = job / 'go-cache', job / 'temp'
            cache.mkdir(); temporary.mkdir()
            env = dict(os.environ, **FLAGS, GOCACHE=str(cache), GOTMPDIR=str(temporary),
                       TMP=str(temporary), TEMP=str(temporary), GTT_SCRATCH_DIR=str(job),
                       GOTOOLCHAIN='local', GOMAXPROCS='4', GOMEMLIMIT='2GiB', CGO_ENABLED='0')
            if args.measure:
                inputs = job / 'saved-inputs'
                inputs.mkdir()
                receipt = json.loads((source.OUT / 'architecture-inputs-v1.json').read_bytes())
                for row in receipt['saved_payloads']:
                    directory = inputs / str(row['seed'])
                    directory.mkdir()
                    for name, pin in row['files'].items():
                        stored = (source.ROOT / pin['path']).read_bytes()
                        if hashlib.sha256(stored).hexdigest() != pin['stored_sha256']:
                            raise ValueError('retained archive drift')
                        data = gzip.decompress(stored)
                        if len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
                            raise ValueError('retained input drift')
                        (directory / name).write_bytes(data)
                env['GTT_R5_SAVED_INPUTS'] = str(inputs)
                binary = source.ROOT / 'data/gcsim/engines/engines/gcsim-v2.45.0-mechanic-compiler-20261025/build/gtt-gcsim.exe'
                if hashlib.sha256(binary.read_bytes()).hexdigest() != 'f1e076b7fa9d292d0bab83aed9d3db0ec917437b288dcc6798cd69f4718f9b93':
                    raise ValueError('saved-cost binary differs from the unchanged R4 producer')
                env['GTT_R5_HASH_BINARY'] = str(binary)
            argv = [str(GO), 'test', '-p=1', '-count=1', '-v',
                    './internal/formula', './internal/evaluator', './internal/engineclient',
                    './internal/setcontext', '-run', '^TestR5Saved' if args.measure else '^TestR5']
            if args.evaluate_confirm:
                if not args.measure:
                    raise ValueError('confirmation requires the retained-input mode')
                argv = [str(GO),'test','-p=1','-count=1','-v','./internal/formula',
                        '-run','^TestR5(EvaluateFiniteBitsReuseAndErrors|SavedEvaluateConfirmation)$']
            if args.combined:
                pattern = ('^(TestR5(EvaluateFiniteBitsReuseAndErrors|SearchViewOwnScratchZeroPreflight|StreamingIntegrityRetainsEveryCheck)'
                    '|TestArtifactArithmetic.*|TestArtifactChangedMask.*'
                    '|TestIncrementalUnchangedLiveStatsStillValidateAllInputs'
                    '|TestParametricSpecializationCacheIdentityAndScratch'
                    '|TestArtifactProgramTheoryForkOwnsPreviousAndValueScratch'
                    '|TestParametricSearchViewUsesBoundProgramAndNoStaleActorDetail'
                    '|TestContextReplacementPreservesFrameAndRestores|TestContextIdentityCoversAllInputs'
                    '|TestNeutralModelSavedFixtureOwnershipAndResponse'
                    '|TestBoundEngineDetectsStageMutation'
                    '|TestVerifyFullBuildCancellationBeforeDispatchDoesNotSpendAttempt'
                    '|TestR2GroupedProductRetainsActualMixedIterations)$')
                argv=[str(GO),'test','-p=1','-count=1','-v','./internal/formula',
                      './internal/evaluator','./internal/engineclient','./internal/setcontext',
                      './internal/allsets','./internal/finalists','./cmd/gtt-optimizer','-run',pattern]
            call, raw = command(argv, module, env)
            record['commands'].append(call); logs.append(raw)
            if args.measure:
                record['measurements'] = {}
                for path in sorted(inputs.glob('r5-*costs.json')):
                    data = path.read_bytes()
                    target = source.OUT / (args.label + '-' + path.name)
                    with target.open('xb') as handle:
                        handle.write(data)
                    record['measurements'][path.name] = {
                        'file': target.name, 'sha256': hashlib.sha256(data).hexdigest()}
            if call['returncode'] != 0:
                raise RuntimeError('focused R5 gate failed')
            record['status'] = 'passed'
        except Exception as error:
            record.update(status='failed', error=f'{type(error).__name__}: {error}')
        finally:
            log.write_bytes(b'\n'.join(logs))
            record['log_sha256'] = hashlib.sha256(log.read_bytes()).hexdigest()
    record['job_removed'] = not Path(record['job']).exists()
    output.write_text(json.dumps(record, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in record.items() if k != 'source_files'}))
    return 0 if record['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
