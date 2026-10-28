"""Finite focused R4 gate; no gameplay/build/install of a runtime consumer."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path

from tools.managed_optimizer_experiment import managed_scratch
from . import r4_redundant as source
from .r3_offline import GO, command

FLAGS = {name: '1' for name in ('GTT_R4_OWNED_DIGEST', 'GTT_R4_TYPED_PANEL',
                               'GTT_R4_FAST_COUNTERS')}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--measure', action='store_true')
    parser.add_argument('--region-candidate', action='store_true')
    parser.add_argument('--cmd-only', action='store_true')
    args = parser.parse_args()
    flags = dict(FLAGS)
    if args.region_candidate:
        flags['GTT_R4_DIRTY_REGIONS'] = '1'
    output = source.OUT / (args.label + '.json')
    log = output.with_suffix('.log')
    if output.exists() or log.exists():
        raise FileExistsError(output)
    record = {'schema': 'r4_focused_v1', 'engine_calls': 0, 'search_calls': 0,
              'installed': False, 'status': 'started', 'commands': [], 'flags': flags}
    logs = []
    with managed_scratch() as job:
        record['job'] = str(job)
        try:
            images = source.native_images(region_candidate=args.region_candidate)
            mapping = {k: hashlib.sha256(v).hexdigest() for k, v in sorted(images.items())}
            record['source_files'] = mapping
            record['source_map_sha256'] = hashlib.sha256(json.dumps(mapping, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            module = job / 'native/gcsim_optimizer'
            for name, raw in images.items():
                path = module / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            public = job / 'tests/fixtures/gcsim_optimizer_go_v1'
            public.mkdir(parents=True)
            record['public_fixtures'] = {}
            for name in ('request_v1.json', 'compact_ir_v1.json'):
                data=(source.ROOT/'tests/fixtures/gcsim_optimizer_go_v1'/name).read_bytes()
                (public/name).write_bytes(data)
                record['public_fixtures'][name]=hashlib.sha256(data).hexdigest()
            cache, temporary = job / 'go-cache', job / 'temp'
            cache.mkdir(); temporary.mkdir()
            env = dict(os.environ, **flags, GOCACHE=str(cache), GOTMPDIR=str(temporary),
                       TMP=str(temporary), TEMP=str(temporary), GTT_SCRATCH_DIR=str(job),
                       GOTOOLCHAIN='local', GOMAXPROCS='4', GOMEMLIMIT='2GiB', CGO_ENABLED='0',
                       GTT_R3_PARALLEL_CAPTURE='1', GTT_R3_ADJOINT_REUSE='1',
                       GTT_R3_PROGRAM_IDENTITY='1', GTT_R3_TYPED_CANONICAL='1', GTT_R3_OPERATION_SWITCH='1')
            argv = [str(GO), 'test', '-p=1', '-count=1', '-v', './internal/contracts',
                    './internal/engineclient', './internal/formula', './internal/projectionmetrics',
                    './internal/setcontext', './internal/finalists', './cmd/gtt-optimizer',
                    '-run', '^(TestR4|TestRegions|TestEffectSidecar|TestSeedMemberTypedCanonical|TestR3Capture|TestR2)']
            if args.cmd_only:
                argv=[str(GO),'test','-p=1','-count=1','-v','./cmd/gtt-optimizer','-run','^TestR2GroupedProductRetainsActualMixedIterations$']
            if args.measure:
                inputs=job/'saved-inputs';inputs.mkdir()
                receipt=json.loads((source.OUT/'architecture-inputs-v1.json').read_bytes())
                for row in receipt['saved_payloads']:
                    directory=inputs/str(row['seed']);directory.mkdir()
                    for name,pin in row['files'].items():
                        stored=(source.ROOT/pin['path']).read_bytes()
                        if hashlib.sha256(stored).hexdigest()!=pin['stored_sha256']:raise ValueError('saved archive drift')
                        data=gzip.decompress(stored)
                        if len(data)!=pin['bytes'] or hashlib.sha256(data).hexdigest()!=pin['sha256']:raise ValueError('saved input drift')
                        (directory/name).write_bytes(data)
                env['GTT_R4_SAVED_INPUTS']=str(inputs)
                argv=[str(GO),'test','-p=1','-count=1','-v','./internal/contracts','./internal/formula','./internal/projectionmetrics','-run','^TestR4Saved']
            call, raw = command(argv, module, env)
            record['commands'].append(call); logs.append(raw)
            if args.measure:
                record['measurements']={}
                for name in ('r4-canonical-hash-costs.json','r4-region-costs.json','r4-counter-costs.json'):
                    path=inputs/name
                    if path.exists():
                        data=path.read_bytes();target=source.OUT/(args.label+'-'+name)
                        with target.open('xb') as file:file.write(data)
                        record['measurements'][name]={'file':target.name,'sha256':hashlib.sha256(data).hexdigest()}
            if call['returncode'] != 0:
                raise RuntimeError('focused R4 gate failed')
            record['status'] = 'passed'
            record['race'] = 'Unavailable: fixed Windows Go/CGO=0/no gcc; no toolchain change. Bounded concurrency and lifecycle checks executed.'
        except Exception as error:
            record['status'] = 'failed'
            record['error'] = f'{type(error).__name__}: {error}'
        finally:
            log.write_bytes(b'\n'.join(logs))
            record['log_sha256'] = hashlib.sha256(log.read_bytes()).hexdigest()
    record['job_removed'] = not Path(record['job']).exists()
    output.write_text(json.dumps(record, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in record.items() if k != 'source_files'}))
    return 0 if record['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
