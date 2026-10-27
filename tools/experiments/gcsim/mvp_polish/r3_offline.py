"""Finite engine-free source gate for the isolated R3 module; no button run."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from tools.managed_optimizer_experiment import managed_scratch
from . import r3_engineering as r3

GO = Path('C:/Program Files/Go/bin/go.exe')


def command(args, cwd, env, timeout=240):
    started = time.monotonic()
    process = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        raw, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raw, _ = process.communicate(timeout=15)
        raise RuntimeError('offline command exceeded finite ownership timeout')
    return {'argv': args, 'returncode': process.returncode, 'wall_s': time.monotonic() - started}, raw


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--measure', action='store_true')
    parser.add_argument('--ready-corrective', action='store_true')
    parser.add_argument('--validator-only', action='store_true')
    args = parser.parse_args()
    if args.ready_corrective or args.validator_only:
        args.measure = True
    target = r3.OUT / (args.label + '.json')
    log = target.with_suffix('.log')
    if target.exists() or log.exists():
        raise FileExistsError(target)
    record = {'schema': 'r3_offline_gate_v1', 'engine_calls': 0, 'search_calls': 0,
              'installed': False, 'commands': [], 'status': 'started'}
    outputs = []
    with managed_scratch() as job:
        record['job'] = str(job)
        try:
            images = r3.native_images()
            mapping = {k: hashlib.sha256(v).hexdigest() for k, v in sorted(images.items())}
            record['source_files'] = mapping
            record['source_map_sha256'] = hashlib.sha256(json.dumps(mapping, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            source = job / 'source'
            for name, raw in images.items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            cache, temporary = job / 'go-cache', job / 'temp'
            cache.mkdir(); temporary.mkdir()
            env = dict(os.environ, GOCACHE=str(cache), GOTMPDIR=str(temporary),
                       TMP=str(temporary), TEMP=str(temporary), GTT_SCRATCH_DIR=str(job),
                       GOTOOLCHAIN='local', GOMAXPROCS='4', CGO_ENABLED='0',
                       GOMEMLIMIT='2GiB',
                       GTT_R3_PARALLEL_CAPTURE='1', GTT_R3_ADJOINT_REUSE='1',
                       GTT_R3_PROGRAM_IDENTITY='1', GTT_R3_TYPED_CANONICAL='1')
            env['GTT_R3_OPERATION_SWITCH'] = '1'
            if args.measure:
                inputs = job / 'saved-inputs'
                inputs.mkdir()
                receipt = json.loads((r3.OUT / 'architecture-inputs-v1.json').read_bytes())
                for row in receipt['saved_payloads']:
                    directory = inputs / str(row['seed'])
                    directory.mkdir()
                    for leaf, pin in row['files'].items():
                        stored = (r3.ROOT / pin['path']).read_bytes()
                        if hashlib.sha256(stored).hexdigest() != pin['stored_sha256']:
                            raise ValueError('saved archive drift')
                        raw = gzip.decompress(stored)
                        if len(raw) != pin['bytes'] or hashlib.sha256(raw).hexdigest() != pin['sha256']:
                            raise ValueError('saved payload drift')
                        (directory / leaf).write_bytes(raw)
                    pins = {'source': row['source_manifest_sha256'], 'config': row['config_sha256'],
                            'member': row['files']['member.json']['sha256'],
                            'sidecar': row['files']['member.json.effects.json']['sha256']}
                    (directory / 'pins.json').write_text(json.dumps(pins), encoding='utf-8')
                env['GTT_R3_SAVED_INPUTS'] = str(inputs)
                argv = [str(GO), 'test', '-p=1', '-count=1', '-v', './internal/contracts',
                        './internal/formula', './internal/engineclient', '-run', '^TestR3Saved']
                if args.ready_corrective:
                    env['GTT_R3_READY_CORRECTIVE'] = '1'
                    argv = [str(GO), 'test', '-p=1', '-count=1', '-v', './internal/engineclient',
                            '-run', '^TestR3SavedReadyCosts$']
                if args.validator_only:
                    argv = [str(GO), 'test', '-p=1', '-count=1', '-v', './internal/contracts',
                            '-run', '^(TestR3OperationValidator|TestR3SavedOperationCosts)']
                record['measurement_scope'] = receipt['representativeness']
            else:
                argv = [str(GO), 'test', '-count=1', '-v', './internal/contracts',
                        './internal/formula', './internal/setcontext', '-run',
                        '^(TestR3|TestSeedMemberTypedCanonical|TestProvider|TestNeutralConstant|TestNeutralSymbolic)']
            call, raw = command(argv, source, env)
            record['commands'].append(call); outputs.append(raw)
            if args.measure:
                record['measurements'] = {}
                for name in ('codec-costs.json', 'gradient-costs.json', 'ready-costs.json', 'operation-costs.json'):
                    path = inputs / name
                    if path.exists():
                        data = path.read_bytes()
                        exported = r3.OUT / (args.label + '-' + name)
                        if exported.exists():
                            raise FileExistsError(exported)
                        exported.write_bytes(data)
                        record['measurements'][name] = {'file': exported.name, 'sha256': hashlib.sha256(data).hexdigest()}
                for name, sample in [('ready-cpu.pprof', 'cpu'), ('ready-allocs.pprof', 'alloc_space')]:
                    path = inputs / name
                    if path.exists():
                        profile_call, profile_raw = command([str(GO), 'tool', 'pprof', '-top',
                                                            '-nodecount=12', '-sample_index=' + sample,
                                                            str(path)], source, env)
                        record['commands'].append(profile_call)
                        exported = r3.OUT / (args.label + '-' + name + '.txt')
                        exported.write_bytes(profile_raw)
            if call['returncode'] != 0:
                raise RuntimeError('focused Go gate failed')
            compiler = shutil.which('gcc') if not args.measure else None
            if compiler:
                race_env = dict(env, CGO_ENABLED='1', CC=compiler)
                call, raw = command([str(GO), 'test', '-race', '-count=1', '-v',
                                     './internal/setcontext', '-run', '^TestR3Capture'], source, race_env)
                record['commands'].append(call); outputs.append(raw)
                if call['returncode'] != 0:
                    raise RuntimeError('capture race gate failed')
                record['race'] = 'PASS: bounded seed collector and cancellation/join'
            elif not args.measure:
                record['race'] = 'unavailable: fixed Windows toolchain has CGO=0 and no gcc in PATH; no install attempted'
            record['status'] = 'passed'
        except Exception as error:
            record['status'] = 'failed'
            record['error'] = f'{type(error).__name__}: {error}'
        finally:
            log.write_bytes(b'\n'.join(outputs))
            record['log_sha256'] = hashlib.sha256(log.read_bytes()).hexdigest()
    record['job_removed'] = not Path(record['job']).exists()
    target.write_text(json.dumps(record, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in record.items() if k != 'source_files'}))
    return 0 if record['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
