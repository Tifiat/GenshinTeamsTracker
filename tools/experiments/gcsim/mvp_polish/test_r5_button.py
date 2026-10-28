"""Offline source/bootstrap/dispatch checks; never call the numerical arm."""
from __future__ import annotations

import json
import ast
from importlib.util import resolve_name
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from . import r5_button as runner
from .r5_python import python_images, mapping


class R5ButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native,cls.row,cls.packet=runner.preflight()

    def test_exact_source_image_and_unchanged_policy(self):
        packet=self.packet
        self.assertEqual(packet['source_image_sha256'],runner.map_sha(self.native))
        self.assertEqual(packet['parent_r4_source_image_sha256'],runner.source.R4_MAP)
        self.assertEqual(packet['r5_product_python_files'],mapping(python_images()))
        self.assertEqual(packet['result_options'],{'set_group_limit':3,'builds_per_group':3,'fast_mode':False})
        self.assertEqual(packet['seeds'],[742031889,742031890])
        self.assertEqual(packet['permitted_arms'],['off'])
        self.assertEqual(len(packet['r4_flags']),8)
        runner.verify_packet_sources(packet)

    def test_source_mutation_and_duplicate_dispatch_rejected(self):
        changed=dict(python_images());changed['run_workspace/gcsim/tree_identity.py']=b'changed'
        with patch.object(runner,'python_images',return_value=changed):
            with self.assertRaisesRegex(ValueError,'Python image changed'):
                runner.verify_packet_sources(self.packet)
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder);owner={'arms':[{'arm':'off'}]}
            (out/'owner.json').write_text(json.dumps(owner))
            with self.assertRaisesRegex(ValueError,'exactly one OFF'):
                runner.checked_arm(out,out,'off')
            owner['arms']=[];(out/'owner.json').write_text(json.dumps(owner))
            with self.assertRaisesRegex(ValueError,'exactly one OFF'):
                runner.checked_arm(out,out,'on')

    def test_pinned_route_covers_function_local_harness_imports(self):
        required=set()
        for name in runner.HARNESS_ROUTE:
            package='.'.join(Path(name).parts[:-1])
            tree=ast.parse((runner.ROOT/name).read_bytes(),filename=name)
            for node in ast.walk(tree):
                modules=[]
                if isinstance(node,ast.Import): modules=[alias.name for alias in node.names]
                elif isinstance(node,ast.ImportFrom):
                    base=resolve_name('.'*node.level+(node.module or ''),package) if node.level else (node.module or '')
                    modules=[base]+[base+'.'+alias.name for alias in node.names if alias.name!='*']
                for module in modules:
                    if module.split('.')[0] not in ('tools','tests'):continue
                    stem=module.replace('.','/')
                    for candidate in (stem+'.py',stem+'/__init__.py'):
                        if (runner.ROOT/candidate).is_file(): required.add(candidate)
        self.assertFalse(required-set(self.packet['r5_harness_files']),sorted(required-set(self.packet['r5_harness_files'])))

    def test_actual_startup_freezes_appshell_imports_without_running_it(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'sitecustomize.py').write_bytes(runner.BOOTSTRAP.encode())
            env=dict(os.environ,PYTHONPATH=os.pathsep.join((str(root),str(runner.ROOT))),QT_QPA_PLATFORM='offscreen')
            env.pop('GTT_R5_IMAGE_BOOTSTRAPPED',None)
            script='''import json,os
from tools.experiments.gcsim.mvp_polish import r5_button as r
r.preload_button_sources()
_native,_row,packet=r.preflight()
r.verify_packet_sources(packet)
assert os.environ['GTT_R5_IMAGE_BOOTSTRAPPED']==r.map_sha(r.IMAGE.images)
imports=r.IMAGE.verify()
assert 'ui/app_shell.py' in imports
assert 'run_workspace/gcsim/optimizer_go_inputs.py' in imports
print(json.dumps({'image_map':r.map_sha(r.IMAGE.images),'product_imports':len(imports),'harness':r.harness_files()}))
'''
            child=subprocess.run([sys.executable,'-B','-c',script],cwd=runner.ROOT,env=env,
                                 capture_output=True,text=True,timeout=60)
            self.assertEqual(child.returncode,0,child.stdout+child.stderr)
            observed=json.loads(child.stdout.strip().splitlines()[-1])
            self.assertEqual(observed['image_map'],self.packet['r5_product_python_map_sha256'])
            self.assertGreater(observed['product_imports'],90)
            self.assertFalse(set(observed['harness'])-set(self.packet['r5_harness_files']))


if __name__=='__main__':unittest.main()
