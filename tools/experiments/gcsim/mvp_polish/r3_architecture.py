"""Freeze the reviewed R2 sources and inspect existing R3 inputs; no engine/build."""
from __future__ import annotations

import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'docs/optimizer-evidence/2026-10-27-engineering-efficiency'
R2_MAP = '5091c1ca4365c894b93db7685dc3e0d6905bdb226c1772b8cd06ab1fd0c64d14'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def save_once(path, raw):
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('refusing to replace frozen evidence: ' + str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def main():
    reads = set()

    def audit(event, args):
        if event != 'open' or not isinstance(args[0], (str, bytes)):
            return
        try:
            path = Path(args[0]).resolve()
            relative = path.relative_to(ROOT)
        except (ValueError, OSError, TypeError):
            return
        mode = args[1]
        if mode is None or 'r' in mode:
            reads.add(relative.as_posix())

    sys.addaudithook(audit)
    from tools.experiments.gcsim.mvp_polish import r2_staged_finalists as r2
    images = r2.native_images()
    mapping = {k: sha(v) for k, v in sorted(images.items())}
    if sha(encoded(mapping)) != R2_MAP:
        raise ValueError('R2 reconstruction drift')
    for module in list(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if not name:
            continue
        path = Path(name).resolve()
        if path.suffix == '.py' and path.is_relative_to(ROOT):
            reads.add(path.relative_to(ROOT).as_posix())
    dependencies = {}
    for name in sorted(reads):
        path = ROOT / name
        if path.is_file() and path.suffix != '.pyc':
            raw = path.read_bytes()
            dependencies[name] = {'bytes': len(raw), 'sha256': sha(raw)}

    # A complete deterministic native module, including go.mod; no private data.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(images.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw, compresslevel=9)
    archive_bytes = buffer.getvalue()
    archive_path = OUT / 'r2-native-source-v1.zip'
    save_once(archive_path, archive_bytes)
    manifest = {'schema': 'r3_r2_frozen_recovery_v1', 'source_map_sha256': R2_MAP,
                'files': mapping, 'file_count': len(images), 'source_bytes': sum(map(len, images.values())),
                'archive': {'path': archive_path.relative_to(ROOT).as_posix(),
                            'bytes': len(archive_bytes), 'sha256': sha(archive_bytes)},
                'historical_reconstruction_dependencies': dependencies,
                'scope': 'Complete R2 native module only; Python button/producer recovery remains separately pinned.'}
    save_once(OUT / 'r2-native-source-v1.json', json.dumps(manifest, sort_keys=True, indent=2).encode() + b'\n')

    base = ROOT / 'docs/optimizer-evidence/2026-10-15-mvp-polish'
    prefix = 'candidate-preservation-chasca-v2-result__cases__chasca__candidate__verification__contexts__context-a9c6f8f457880e6eca59aa2303d3814c12adf868e13163e58a32ec1755de5dc3__seed-'
    payloads = []
    for seed in (742031889, 742031890):
        row = {'seed': seed, 'files': {}}
        decoded = {}
        for leaf in ('config.txt', 'capture-request.json', 'member.json', 'member.json.effects.json'):
            path = base / (prefix + str(seed) + '__' + leaf + '.gz')
            stored = path.read_bytes()
            raw = gzip.decompress(stored)
            row['files'][leaf] = {'path': path.relative_to(ROOT).as_posix(), 'stored_bytes': len(stored),
                                  'stored_sha256': sha(stored), 'bytes': len(raw), 'sha256': sha(raw)}
            if leaf.endswith('.json'):
                decoded[leaf] = json.loads(raw)
        member, sidecar = decoded['member.json'], decoded['member.json.effects.json']
        if member['seed'] != seed or sidecar['seed'] != str(seed) or sidecar['member_content_sha256'] != row['files']['member.json']['sha256']:
            raise ValueError('historical payload identity differs')
        row.update(nodes=len(member['nodes']), channels=len(member['channels']),
                   member_keys=sorted(member), source_manifest_sha256=sidecar['source_manifest_body_sha256'],
                   config_sha256=sidecar['input_config_sha256'], owners=sidecar['character_keys'],
                   neutral_keys=sorted(sidecar['neutral']), has_mechanic_invocations='mechanic_invocations' in sidecar,
                   sidecar_counts={k: len(v) for k, v in sidecar.items() if isinstance(v, list)})
        payloads.append(row)
    receipt = {'schema': 'r3_architecture_inputs_v1', 'engine_calls': 0, 'builds': 0, 'search_calls': 0,
               'r2_recovery_manifest': 'r2-native-source-v1.json', 'saved_payloads': payloads,
               'representativeness': 'Real historical Chasca capture pair. Not the removed R2 job payload; different producer manifest/context, and no mechanic-invocation section. Member and legacy neutral-sidecar codec/allocation work is measurable; current f1e invocation extension is not represented.',
               'candidate': 'Typed canonical JSON for IRSeedMember only: reuse frozen unexecuted typed-canonical view, retain strict raw-vs-typed equality and all semantic validation. Wire and exporter unchanged; no binary exporter proposal until current total costs justify one.',
               'admission': 'ROOT chooses transport direction before implementation/exporter edits. Parallel capture, owner-local adjoint reuse and direct cache-identity reuse may proceed independently under R3 contract.'}
    save_once(OUT / 'architecture-inputs-v1.json', json.dumps(receipt, sort_keys=True, indent=2).encode() + b'\n')
    print(json.dumps({'source_files': len(images), 'source_map_sha256': R2_MAP,
                      'archive_bytes': len(archive_bytes), 'archive_sha256': sha(archive_bytes),
                      'dependency_files': len(dependencies),
                      'payload_bytes': [{k: v['bytes'] for k, v in p['files'].items()} for p in payloads],
                      'output': str(OUT)}))


if __name__ == '__main__':
    main()
