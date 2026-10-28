"""R5 exact Python/native image on the unchanged full-account button owner."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from .r5_python import ProductImageFinder, install_image, python_images, harness_baseline_images, mapping, map_sha, sha

IMAGE = next((item for item in sys.meta_path if isinstance(item, ProductImageFinder)), None)
if IMAGE is None:
    IMAGE = install_image()
elif IMAGE.pins != mapping(python_images()):
    raise ValueError('R5 startup image differs')

from . import r4_button as previous
from . import r5_redundant as source
from .mechanic_packet_evidence import write_json

base, ROOT, OUT = previous.base, source.ROOT, source.OUT
FLAGS = previous.FLAGS
CHILD = 'tools.experiments.gcsim.mvp_polish.r5_button.R5ButtonExecutionTest.test_one_case'
PREVIOUS = OUT / 'r4-run-v1/owner.json'
HARNESS_ROUTE = (
    'tools/experiments/gcsim/mvp_polish/r1_button.py',
    'tools/experiments/gcsim/mvp_polish/r2_button.py',
    'tools/experiments/gcsim/mvp_polish/r3_button.py',
    'tools/experiments/gcsim/mvp_polish/r4_button.py',
    'tools/experiments/gcsim/mvp_polish/r5_button.py',
    'tools/experiments/gcsim/mvp_polish/mechanic_button_gate.py',
    'tools/experiments/gcsim/mvp_polish/whole_chasca_button.py',
    'tools/experiments/gcsim/mvp_polish/run_case.py',
    'tools/experiments/gcsim/mvp_polish/real_inventory_adapter.py',
    'tools/experiments/gcsim/mvp_polish/mechanic_candidate_store.py',
    'tools/experiments/gcsim/mvp_polish/mechanic_packet_evidence.py',
    'tests/tools/test_optimizer_archetype_button_cases.py',
)
BOOTSTRAP = '''from tools.experiments.gcsim.mvp_polish.r5_python import install_image, map_sha
import os
_r5_image = install_image()
os.environ['GTT_R5_IMAGE_BOOTSTRAPPED'] = map_sha(_r5_image.images)
'''


def preload_button_sources():
    # Import definitions only, without QApplication construction or test methods.
    from tests.tools import test_optimizer_archetype_button_cases
    from ui import app_shell
    from . import real_inventory_adapter, mechanic_candidate_store
    return test_optimizer_archetype_button_cases, app_shell


def harness_files():
    files = {name:sha((ROOT/name).read_bytes()) for name in HARNESS_ROUTE}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if not filename:
            continue
        path = Path(filename).resolve()
        try:
            relative = path.relative_to(ROOT).as_posix()
        except ValueError:
            continue
        if relative.endswith('.py') and relative.split('/')[0] in ('tools', 'tests'):
            files[relative] = sha(path.read_bytes())
    return dict(sorted(files.items()))


def runtime_dependencies():
    import _sqlite3, _decimal, sqlite3
    import PySide6
    from PySide6 import QtCore, QtGui, QtWidgets
    files={Path(sys.executable),Path(sys._base_executable)}
    files.update(Path(module.__file__) for module in (_sqlite3,_decimal,QtCore,QtGui,QtWidgets))
    candidates=[Path(sys.base_prefix)/'python311.dll']
    candidates += [Path(PySide6.__file__).parent/name for name in ('Qt6Core.dll','Qt6Gui.dll','Qt6Widgets.dll')]
    files.update(path for path in candidates if path.is_file())
    return {'python_version':sys.version,'pyside6_version':PySide6.__version__,
            'qt_version':QtCore.qVersion(),'sqlite_version':sqlite3.sqlite_version,
            'files':{str(path.resolve()):sha(path.read_bytes()) for path in sorted(files)}}


def verify_harness_reconstruction(files):
    recovered=mapping(harness_baseline_images())
    for name,digest in files.items():
        if name.rsplit('/',1)[-1].startswith(('r5_','test_r5_')):
            continue  # These exact owned files belong to the R5 source milestone.
        if recovered.get(name)!=digest:
            raise ValueError('R5 harness is not reconstructible: '+name)


def preflight():
    _, row, packet = previous.preflight()
    preload_button_sources()
    native = source.native_images()
    dependencies=runtime_dependencies()
    harness=harness_files()
    verify_harness_reconstruction(harness)
    packet.update(experiment='R5_bounded_final_audit',
        parent_r4_source_image_sha256=source.R4_MAP,
        source_images=mapping(native), source_image_sha256=map_sha(native),
        r5_product_python_files=IMAGE.pins,
        r5_product_python_map_sha256=map_sha(IMAGE.images),
        r5_harness_files=harness,
        r5_native_harness_files={path.relative_to(ROOT).as_posix():sha(path.read_bytes())
                                 for path in sorted(source.HERE.glob('r5_*.go'))},
        r5_harness_recovery_map_sha256=map_sha(harness_baseline_images()),
        r5_harness_recovery_manifest_sha256=sha((OUT/'r5-harness-baseline-v1.json').read_bytes()),
        r5_runtime_dependencies=dependencies,
        r5_deferred_harness_route=list(HARNESS_ROUTE),
        r5_bootstrap_sha256=sha(BOOTSTRAP.encode()),
        python_control_limit='R4 product Python identity was not frozen; historical button comparison is qualified.',
        python_resource_scope='Executable product Python is frozen. Existing package/data paths remain original and retain their separate input/source checks.',
        r5_disposition={
            'inventory_equipment':'one owned readonly SQLite view; old independent public API retains its recheck',
            'first_report':'first full report replaced by common slot/mapping payload; second final report and validators retained',
            'source_reads':'requested binary digest from store-tree stream; verified repository/go.mod bytes reused; mutable cross-stage rechecks retained',
            'views':'single private scratch copy; zero-baseline evaluation retained; complete context construction retained',
            'evaluate':'finite/bit-change scan fused; all inputs checked before reuse, R4 early-error state and FP order retained',
            'diagnostics_integrity':'last8x2048 chars plus original last8 Finish markers; complete log; every Go integrity check streamed',
            'provenance':'prospective reconstructed product Python, exact native and imported harness sources pinned before run'},
    )
    return native, row, packet


def verify_packet_sources(packet):
    IMAGE.verify()
    if packet['r5_product_python_files'] != mapping(python_images()):
        raise ValueError('R5 Python image changed')
    if IMAGE.pins != packet['r5_product_python_files']:
        raise ValueError('R5 loaded Python image differs')
    pinned={}
    for key in ('r3_harness_files','r4_harness_files','r5_harness_files','r5_native_harness_files'):
        pinned.update(packet[key])
    for name, digest in pinned.items():
        if sha((ROOT / name).read_bytes()) != digest:
            raise ValueError('R5 harness source changed: ' + name)
    if sha((OUT/'r5-harness-baseline-v1.json').read_bytes())!=packet['r5_harness_recovery_manifest_sha256']:
        raise ValueError('R5 harness reconstruction manifest changed')
    verify_harness_reconstruction(packet['r5_harness_files'])
    if runtime_dependencies()!=packet['r5_runtime_dependencies']:
        raise ValueError('R5 runtime dependencies changed')


class R5ButtonExecutionTest(unittest.TestCase):
    def test_one_case(self):
        owner = json.loads(Path(os.environ['GTT_R5_OWNER']).read_bytes())
        packet = owner['packet']
        if os.environ.get('GTT_R5_IMAGE_BOOTSTRAPPED') != packet['r5_product_python_map_sha256']:
            raise ValueError('R5 actual child was not bootstrapped with the frozen product image')
        preload_button_sources()
        verify_packet_sources(packet)
        try:
            previous.R4ButtonExecutionTest('test_one_case').test_one_case()
        finally:
            imports = IMAGE.verify()
            verify_packet_sources(packet)
            current = harness_files()
            unexpected = sorted(set(current) - set(packet['r5_harness_files']))
            write_json(Path(os.environ['GTT_R5_OBSERVATIONS']), {
                'schema':'r5_actual_python_image_v1','product_python_map_sha256':map_sha(IMAGE.images),
                'product_imports':imports,'harness_files':current,'unlisted_harness_imports':unexpected,
                'source_unchanged':True,'bootstrap_sha256':packet['r5_bootstrap_sha256'],
            })
            if unexpected:
                raise ValueError('R5 actual harness imported unpinned source: ' + ','.join(unexpected))


def summarize(job, arm, result, output):
    compact = previous.summarize(job, arm, result, output)
    path = output / (arm + '-details.json')
    evidence = json.loads(path.read_bytes())
    evidence.update(schema='r5_bounded_button_result_v1',
                    product_python_map_sha256=map_sha(IMAGE.images))
    write_json(path, evidence)
    compact.update(schema=evidence['schema'],product_python_map_sha256=evidence['product_python_map_sha256'])
    return compact


def checked_arm(job, output, arm, *args):
    owner = json.loads((output/'owner.json').read_bytes())
    if arm != 'off' or owner.get('arms'):
        raise ValueError('R5 authorizes exactly one OFF')
    packet = owner['packet']
    verify_packet_sources(packet)
    bootstrap = job / 'r5-python-bootstrap'
    bootstrap.mkdir()
    (bootstrap/'sitecustomize.py').write_bytes(BOOTSTRAP.encode())
    if sha((bootstrap/'sitecustomize.py').read_bytes()) != packet['r5_bootstrap_sha256']:
        raise ValueError('R5 bootstrap bytes differ')
    environment = base.gate.run_case._child_environment
    def owned_environment(*args, **kwargs):
        env = environment(*args, **kwargs)
        env['PYTHONPATH'] = os.pathsep.join(filter(None,(str(bootstrap),str(ROOT),env.get('PYTHONPATH',''))))
        env['GTT_R5_OWNER'] = str(output/'owner.json')
        env['GTT_R5_OBSERVATIONS'] = str(output/(arm+'-r5-observations.json'))
        env.pop('GTT_R5_IMAGE_BOOTSTRAPPED',None)
        return env
    with patch.object(base.gate.run_case,'_child_environment',owned_environment):
        result = previous.checked_arm(job,output,arm,*args)
    verify_packet_sources(packet)
    return result


def prepare(output):
    reference=json.loads(PREVIOUS.read_bytes())['inventory']
    snapshot=base.gate.snapshot_active_inventory
    def frozen_inventory(**kwargs):
        current=snapshot(**kwargs)
        for key in ('profile_id_sha256','artifact_input_sha256','artifact_count','eligible_count','set_domain_count'):
            if current[key]!=reference[key]:raise ValueError('R5 full-account input differs: '+key)
        return current
    with ExitStack() as stack:
        for name,value in [('OUT',OUT),('preflight',preflight),('CHILD',CHILD),('run_arm',checked_arm),('summarize',summarize)]:
            stack.enter_context(patch.object(base,name,value))
        stack.enter_context(patch.object(base.gate,'snapshot_active_inventory',frozen_inventory))
        base.prepare_and_wait(output)


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--action',choices=('prepare','off','release'),required=True)
    args=parser.parse_args()
    if args.action=='prepare':prepare(args.output)
    else:
        if args.action=='off':
            owner=json.loads((args.output/'owner.json').read_bytes())
            if owner.get('arms'):raise ValueError('R5 OFF already completed')
            verify_packet_sources(owner['packet'])
        with patch.object(sys,'argv',[__file__,'--output',str(args.output),'--action',args.action]):base.main()


if __name__=='__main__':main()
