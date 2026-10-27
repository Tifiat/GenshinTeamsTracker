"""Exact R2 source recovery from one committed tree plus a readable source delta.

No dirty native reads, historical helper chain, temporary checkout, or Git writes.
Only the 411 declared R2 module files are returned. The local zip is optional.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'docs/optimizer-evidence/2026-10-27-engineering-efficiency'
BASE = '6f1cab8389bc63e53297a91a7b14b743009ebd96'
R2_MAP = '5091c1ca4365c894b93db7685dc3e0d6905bdb226c1772b8cd06ab1fd0c64d14'
PREFIX = 'native/gcsim_optimizer/'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def mapping(images):
    return {k: sha(v) for k, v in sorted(images.items())}


def map_sha(images):
    return sha(json.dumps(mapping(images), sort_keys=True, separators=(',', ':')).encode())


def baseline_images(names):
    listing = subprocess.check_output(['git', 'ls-tree', '-r', '-z', BASE, '--', PREFIX], cwd=ROOT)
    blobs = {}
    excluded = []
    for record in listing.split(b'\0'):
        if not record:
            continue
        header, path = record.split(b'\t', 1)
        mode, kind, object_id = header.decode().split()
        name = path.decode().removeprefix(PREFIX)
        if name not in names:
            excluded.append(name)
            continue
        if mode not in ('100644', '100755') or kind != 'blob':
            raise ValueError('non-file baseline source')
        blobs[name] = object_id
    requested = sorted(blobs)
    raw = subprocess.check_output(['git', 'cat-file', '--batch'], cwd=ROOT,
                                  input=''.join(blobs[n] + '\n' for n in requested).encode())
    stream, images = io.BytesIO(raw), {}
    for name in requested:
        object_id, kind, size = stream.readline().decode().strip().split()
        if object_id != blobs[name] or kind != 'blob':
            raise ValueError('baseline Git blob mismatch')
        images[name] = stream.read(int(size))
        if stream.read(1) != b'\n':
            raise ValueError('baseline Git blob truncation')
    if stream.read():
        raise ValueError('unexpected baseline Git output')
    return images, sorted(excluded)


def lines(text):
    # Split only LF: CR/CRLF/mixed historical bytes must survive exactly.
    chunks = text.split('\n')
    return [line + '\n' for line in chunks[:-1]] + ([chunks[-1]] if chunks[-1] else [])


def apply_delta(images, patch):
    rows = []
    for line in lines(patch.decode('utf-8')):
        if line == '\\ No newline at end of file\n':
            if not rows or not rows[-1].endswith('\n'):
                raise ValueError('invalid no-newline marker')
            rows[-1] = rows[-1][:-1]
        else:
            rows.append(line)
    images = dict(images)
    at = 0
    while at < len(rows):
        header = rows[at]
        if not header.startswith('diff --git a/'):
            raise ValueError('source delta header differs')
        names = header.rstrip('\n').split(' ')
        name = names[2].removeprefix('a/')
        if names[3] != 'b/' + name or Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('unsafe source delta path')
        at += 1
        if rows[at] == 'new file mode 100644\n':
            at += 1
            if name in images:
                raise ValueError('new source already exists')
        if not rows[at].startswith('--- ') or rows[at + 1] != '+++ b/' + name + '\n':
            raise ValueError('source delta file boundary differs')
        at += 2
        original = lines(images.get(name, b'').decode('utf-8'))
        result, cursor = [], 0
        while at < len(rows) and rows[at].startswith('@@ '):
            hunk = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@\n', rows[at])
            if not hunk:
                raise ValueError('source delta hunk differs')
            old_start, old_count, _, new_count = hunk.groups()
            old_count = int(old_count) if old_count is not None else 1
            new_count = int(new_count) if new_count is not None else 1
            offset = int(old_start) - (1 if old_count else 0)
            if offset < cursor or offset > len(original):
                raise ValueError('source delta offset differs')
            result.extend(original[cursor:offset]); cursor = offset
            consumed, emitted = 0, 0
            at += 1
            while at < len(rows) and rows[at][:1] in (' ', '+', '-'):
                line = rows[at]; tag, content = line[0], line[1:]
                if tag in (' ', '-'):
                    if cursor >= len(original) or original[cursor] != content:
                        raise ValueError('source delta context differs: ' + name)
                    cursor += 1; consumed += 1
                if tag in (' ', '+'):
                    result.append(content); emitted += 1
                at += 1
            if consumed != old_count or emitted != new_count:
                raise ValueError('source delta hunk length differs')
        result.extend(original[cursor:])
        images[name] = ''.join(result).encode('utf-8')
    return images


def recover_images():
    receipt = json.loads((OUT / 'r2-source-delta-v1.json').read_bytes())
    if receipt['base_commit'] != BASE or receipt['source_map_sha256'] != R2_MAP or len(receipt['files']) != 411:
        raise ValueError('source recovery receipt differs')
    patch = (OUT / 'r2-source-delta-v1.patch').read_bytes()
    if sha(patch) != receipt['patch_sha256']:
        raise ValueError('source delta identity differs')
    images, excluded = baseline_images(set(receipt['files']))
    if mapping(images) != receipt['baseline_files'] or excluded != receipt['excluded_baseline_files']:
        raise ValueError('pinned committed source differs')
    images = apply_delta(images, patch)
    if mapping(images) != receipt['files'] or map_sha(images) != R2_MAP:
        raise ValueError('recovered R2 source map differs')
    return images


def create():
    manifest = json.loads((OUT / 'r2-native-source-v1.json').read_bytes())
    archive = (OUT / 'r2-native-source-v1.zip').read_bytes()
    if sha(archive) != manifest['archive']['sha256']:
        raise ValueError('local R2 archive differs')
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        desired = {name: source.read(name) for name in source.namelist()}
    if map_sha(desired) != R2_MAP:
        raise ValueError('local source map differs')
    baseline, excluded = baseline_images(set(desired))
    output = []
    changed = []
    for name, raw in sorted(desired.items()):
        before = baseline.get(name, b'')
        if name in baseline and raw == before:
            continue
        changed.append(name)
        output.append(f'diff --git a/{name} b/{name}\n')
        if name not in baseline:
            output.append('new file mode 100644\n')
        for row in difflib.unified_diff(lines(before.decode('utf-8')), lines(raw.decode('utf-8')),
                                       fromfile='a/' + name if name in baseline else '/dev/null',
                                       tofile='b/' + name, lineterm='\n'):
            output.append(row)
            if not row.endswith('\n'):
                output.append('\n\\ No newline at end of file\n')
    patch = ''.join(output).encode('utf-8')
    receipt = {'schema': 'r3_r2_source_delta_v1', 'base_commit': BASE, 'source_map_sha256': R2_MAP,
               'baseline_files': mapping(baseline), 'files': mapping(desired),
               'excluded_baseline_files': excluded, 'changed_files': changed,
               'patch_sha256': sha(patch), 'patch_bytes': len(patch),
               'new_files': len(set(desired) - set(baseline)),
               'scope': 'Only the exact 411-file R2 module is materialized. Excluded committed native files are not inputs. No historical helpers, local zip or private payload required for recovery.'}
    for name, raw in [('r2-source-delta-v1.patch', patch),
                      ('r2-source-delta-v1.json', (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode())]:
        path = OUT / name
        if path.exists():
            raise FileExistsError(path)
        path.write_bytes(raw)
    recovered = recover_images()
    if recovered != desired:
        raise ValueError('source recovery byte parity differs')
    print(json.dumps({'source_map_sha256': map_sha(recovered), 'files': len(recovered),
                      'new_files': receipt['new_files'], 'changed_files': len(changed),
                      'patch_bytes': len(patch), 'patch_sha256': sha(patch)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--create', action='store_true')
    args = parser.parse_args()
    if args.create:
        create()
    else:
        images = recover_images()
        print(json.dumps({'files': len(images), 'source_map_sha256': map_sha(images)}))
