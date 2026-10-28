"""Reconstruct an explicit product-Python image, preserving foreign live files.

The baseline is a readable delta over a pinned Git tree. R5 changes apply only
to this image; no dirty product file is staged or overwritten. The full product
module namespace is pinned before lazy imports, not guessed retrospectively.
"""
from __future__ import annotations

import argparse
import difflib
import importlib.abc
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys

from .r3_recovery import apply_delta, lines, mapping, map_sha, sha

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'docs/optimizer-evidence/2026-10-27-engineering-efficiency'
BASE = 'e6e600d74f64cce33423d1228208f4b9bc36acd9'
PRODUCT_ROOTS = ('run_workspace', 'ui', 'hoyolab_export', 'localization')
EXCLUDED_SOURCE_DIRS = frozenset({'profile', 'profiles', 'private', 'generated', '__pycache__', '.git'})


def product_python_paths():
    """Prune private/generated directories before entering or reading them."""
    names = {'main.py'}
    for prefix in PRODUCT_ROOTS:
        for directory, children, files in os.walk(ROOT / prefix, topdown=True, followlinks=False):
            folder = Path(directory)
            children[:] = sorted(name for name in children
                if name.casefold() not in EXCLUDED_SOURCE_DIRS
                and not name.startswith('.') and not (folder / name).is_symlink())
            for name in files:
                path = folder / name
                if name.endswith('.py') and not path.is_symlink():
                    names.add(path.relative_to(ROOT).as_posix())
    return names


def git_images(names):
    listing = subprocess.check_output(['git', 'ls-tree', '-r', '-z', BASE], cwd=ROOT)
    blobs = {}
    for row in listing.split(b'\0'):
        if not row:
            continue
        header, name = row.split(b'\t', 1)
        name = name.decode()
        if name not in names:
            continue
        mode, kind, blob = header.decode().split()
        if mode not in ('100644', '100755') or kind != 'blob':
            raise ValueError('non-file Python source')
        blobs[name] = blob
    keys = sorted(blobs)
    raw = subprocess.check_output(['git', 'cat-file', '--batch'], cwd=ROOT,
        input=''.join(blobs[k] + '\n' for k in keys).encode())
    stream, images = io.BytesIO(raw), {}
    for name in keys:
        blob, kind, size = stream.readline().decode().split()
        if blob != blobs[name] or kind != 'blob':
            raise ValueError('Python Git source mismatch')
        images[name] = stream.read(int(size))
        if stream.read(1) != b'\n':
            raise ValueError('Python Git source truncated')
    if stream.read():
        raise ValueError('unexpected Python Git bytes')
    return images


def _recover_snapshot(prefix):
    receipt = json.loads((OUT / (prefix+'.json')).read_bytes())
    if receipt['base_commit'] != BASE:
        raise ValueError('Python baseline commit changed')
    before = git_images(set(receipt['files']))
    if mapping(before) != receipt['baseline_files']:
        raise ValueError('Python baseline Git bytes changed')
    for name, ending in receipt.get('checkout_line_endings', {}).items():
        data = before[name].replace(b'\r\n', b'\n')
        before[name] = data.replace(b'\n', b'\r\n') if ending == 'crlf' else data
    patch = (OUT / (prefix+'.patch')).read_bytes()
    if sha(patch) != receipt['patch_sha256']:
        raise ValueError('Python baseline delta changed')
    result = apply_delta(before, patch)
    if mapping(result) != receipt['files'] or map_sha(result) != receipt['source_map_sha256']:
        raise ValueError('Python baseline image changed')
    return result


def baseline_images():
    return _recover_snapshot('r5-python-baseline-v1')


def harness_baseline_images():
    return _recover_snapshot('r5-harness-baseline-v1')


def python_images():
    from .r5_python_changes import apply_changes
    return apply_changes(baseline_images())


class ProductImageFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """An experiment-owned source image; ordinary package/data paths stay valid."""
    def __init__(self, images):
        self.images = dict(images)
        self.pins = mapping(images)
        self.imports = {}

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] not in PRODUCT_ROOTS and fullname != 'main':
            return None
        if any(part.casefold() in EXCLUDED_SOURCE_DIRS for part in fullname.split('.')):
            raise ImportError('Excluded product Python namespace: ' + fullname)
        stem = fullname.replace('.', '/')
        candidates = ((stem + '/__init__.py', True), (stem + '.py', False))
        for name, package in candidates:
            if name in self.images:
                spec = importlib.util.spec_from_loader(fullname, self, is_package=package)
                spec.origin = str(ROOT / name)
                return spec
        # Namespace packages still use the existing path; a concrete unpinned
        # module may never fall through to a dirty live file.
        if (any(name.startswith(stem + '/') for name in self.images)
                and (ROOT / stem).is_dir() and not (ROOT / stem / '__init__.py').exists()):
            return None
        raise ImportError('Product Python module absent from frozen image: ' + fullname)

    def create_module(self, spec):
        return None

    def get_resource_reader(self, fullname):
        from importlib.resources.readers import FileReader
        from types import SimpleNamespace
        path = ROOT / (fullname.replace('.', '/') + '/__init__.py')
        return FileReader(SimpleNamespace(path=str(path)))

    def exec_module(self, module):
        stem = module.__name__.replace('.', '/')
        name = stem + '/__init__.py' if module.__spec__.submodule_search_locations is not None else stem + '.py'
        raw = self.images[name]
        if sha(raw) != self.pins[name]:
            raise ImportError('Product Python image changed: ' + name)
        module.__file__ = str(ROOT / name)
        if module.__spec__.submodule_search_locations is not None:
            module.__path__ = [str((ROOT / name).parent)]
        self.imports[name] = self.pins[name]
        exec(compile(raw, module.__file__, 'exec', dont_inherit=True), module.__dict__)

    def verify(self):
        if mapping(self.images) != self.pins:
            raise ValueError('Product Python image mutated')
        return dict(self.imports)


def install_image(images=None):
    if any(name.split('.')[0] in PRODUCT_ROOTS or name == 'main' for name in sys.modules):
        raise RuntimeError('Product Python image must be installed before product imports')
    finder = ProductImageFinder(python_images() if images is None else images)
    sys.meta_path.insert(0, finder)
    return finder


def capture_baseline():
    manifest = OUT / 'r5-python-baseline-v1.json'
    patch_path = OUT / 'r5-python-baseline-v1.patch'
    if manifest.exists() or patch_path.exists():
        raise FileExistsError(manifest)
    names = product_python_paths()
    desired = {name: (ROOT / name).read_bytes() for name in sorted(names)}
    before = git_images(names)
    output, changed = [], []
    for name, raw in sorted(desired.items()):
        if before.get(name) == raw:
            continue
        changed.append(name)
        output.append(f'diff --git a/{name} b/{name}\n')
        if name not in before:
            output.append('new file mode 100644\n')
        for row in difflib.unified_diff(lines(before.get(name, b'').decode('utf-8')),
                lines(raw.decode('utf-8')), fromfile='a/' + name if name in before else '/dev/null',
                tofile='b/' + name, lineterm='\n'):
            output.append(row)
            if not row.endswith('\n'):
                output.append('\n\\ No newline at end of file\n')
    patch = ''.join(output).encode()
    receipt = {'schema': 'r5_product_python_baseline_v1', 'base_commit': BASE,
               'files': mapping(desired), 'baseline_files': mapping(before),
               'source_map_sha256': map_sha(desired), 'patch_sha256': sha(patch),
               'changed_files': changed, 'patch_bytes': len(patch),
               'excluded_source_directories': sorted(EXCLUDED_SOURCE_DIRS),
               'scope': 'Prospective full product module namespace, including lazy imports. Foreign baseline differences are data in an explicit image, not live product edits/staging or R4 provenance. No profile/account/runtime bytes.'}
    patch_path.write_bytes(patch)
    manifest.write_bytes((json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode())
    if baseline_images() != desired:
        raise ValueError('Python reconstruction byte parity failed')
    print(json.dumps({'files': len(desired), 'changed': len(changed),
                      'patch_bytes': len(patch), 'map': map_sha(desired)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--capture-baseline', action='store_true')
    args = parser.parse_args()
    if args.capture_baseline:
        capture_baseline()
    else:
        images = baseline_images()
        print(json.dumps({'files': len(images), 'map': map_sha(images)}))
