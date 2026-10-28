from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

from run_workspace.gcsim.source_manifest_build import canonical_json
from run_workspace.gcsim.source_manifest_codec import (
    SOURCE_STATE_IR_FORMULA_SHA256,
    SourceFormulaIdentity,
    SourceGoToolchain,
    SourceIROperator,
    SourceIRNode,
    SourceLocator,
    SourceManifestBody,
    SourceManifestEntry,
    SourceSeam,
    SourceSliceStatus,
    SourceSliceTemplate,
    decode_source_manifest_body,
    encode_source_manifest_body,
    source_patch_stack_sha256,
)
from run_workspace.gcsim.trace_contract_error import TraceContractError


def _body() -> SourceManifestBody:
    locator = SourceLocator(
        "internal/characters/example/burst.go", "damage", SourceSeam.EVENT_CALLBACK, 0
    )
    template = SourceSliceTemplate.build(
        status=SourceSliceStatus.SUPPORTED,
        nodes=(SourceIRNode(0, SourceIROperator.CONST, (), constant_value=1e-7),),
        root_node_id=0,
        parameter_keys=(),
        dependencies_complete=True,
        stop_reason_code=None,
    )
    return SourceManifestBody(
        compiler_version="gtt_source_compiler_v2",
        upstream_repo="github.com/genshinsim/gcsim",
        upstream_ref="v0.0.0-test",
        pristine_source_tree_sha256="a" * 64,
        patches=(),
        patch_stack_sha256=source_patch_stack_sha256(()),
        patched_source_tree_sha256="b" * 64,
        trace_schema_version=6,
        trace_capability="gtt_trace_equation_v6",
        formula_identities=(
            SourceFormulaIdentity("gtt_source_ir_v2", SOURCE_STATE_IR_FORMULA_SHA256),
        ),
        go_toolchain=SourceGoToolchain("go1.24.1", "windows", "amd64"),
        build_flags=("-trimpath",),
        entries=(
            SourceManifestEntry(
                locator.source_id, locator, "c" * 64, template
            ),
        ),
    )


class SourceManifestCodecTests(unittest.TestCase):
    def test_canonical_bytes_and_trace_reexports(self) -> None:
        from run_workspace.gcsim.trace_equation import source_dependencies as trace

        body = _body()
        encoded = encode_source_manifest_body(body)
        self.assertEqual(encoded, canonical_json(body.to_dict()))
        self.assertIn('"constant_value":1e-7', encoded)
        self.assertEqual(decode_source_manifest_body(encoded), body)
        self.assertEqual(body.body_sha256, hashlib.sha256(encoded.encode()).hexdigest())
        self.assertIs(trace.SourceManifestBody, SourceManifestBody)
        self.assertIs(trace.SourceSliceTemplate, SourceSliceTemplate)
        self.assertIs(trace.decode_source_manifest_body, decode_source_manifest_body)
        self.assertIs(trace.TraceContractError, TraceContractError)

        changed = json.loads(encoded)
        changed["entries"][0]["template"]["unexpected"] = True
        with self.assertRaises(TraceContractError):
            decode_source_manifest_body(canonical_json(changed))

    def test_manifest_validation_import_does_not_load_trace_package(self) -> None:
        script = (
            "import json, sys\n"
            "from run_workspace.gcsim.source_manifest_build import "
            "_validate_strict_body_contract\n"
            "_validate_strict_body_contract(json.loads(sys.stdin.read()))\n"
            "assert not any(name.startswith('run_workspace.gcsim.trace_equation') "
            "for name in sys.modules)\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            input=encode_source_manifest_body(_body()),
            text=True,
            capture_output=True,
            cwd=Path(__file__).resolve().parents[3],
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
