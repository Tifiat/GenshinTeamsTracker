from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
import unittest

from run_workspace.gcsim.engine_store import GcsimEngineManifest
from run_workspace.gcsim.source_manifest_build import (
    canonical_json as source_manifest_canonical_json,
)
from run_workspace.gcsim.trace_equation import (
    ENGINE_TRACE_V3_CAPABILITY,
    ENGINE_TRACE_V3_SCHEMA_VERSION,
    ENGINE_TRACE_V4_CAPABILITY,
    ENGINE_TRACE_V4_SCHEMA_VERSION,
    SourceDependencyEvidenceTrace,
    SourceFormulaIdentity,
    SourceGoToolchain,
    SourceIROperator,
    SourceIRNode,
    SourceLocator,
    SourceManifestBinding,
    SourceManifestBody,
    SourceManifestEntry,
    SourceOutputKind,
    SourcePatchDigest,
    SourceSeam,
    SourceSliceStatus,
    SourceSliceTemplate,
    TraceContractError,
    ValueReadMode,
    canonical_json,
    decode_engine_trace,
    decode_engine_trace_v3,
    decode_engine_trace_v4,
    decode_source_manifest_binding,
    decode_source_manifest_body,
    encode_source_manifest_binding,
    encode_source_manifest_body,
    evaluate_source_value_binding,
    source_patch_stack_sha256,
)

from .test_contracts import _document
from .test_provider_evidence_v2 import _raw_engine_trace_v2


class SourceDependenciesV4Tests(unittest.TestCase):
    def test_manifest_body_and_semantic_engine_binding_are_byte_bound(self) -> None:
        request, _, binding, _ = _fixture()
        body = binding.manifest_body

        synthetic_entry = next(
            row
            for row in body.entries
            if row.locator.enclosing_symbol == "syntheticFormula"
        )
        self.assertEqual(
            synthetic_entry.source_id,
            "47c97c5c7a8262fa0bf44b319257dfefded05b021acccaab1e53d4e3f1b06643",
        )

        self.assertNotIn("body_sha256", body.to_dict())
        expected_stack = hashlib.sha256(
            json.dumps(
                {
                    "patches": [row.to_dict() for row in body.patches],
                    "schema_version": 1,
                },
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(body.patch_stack_sha256, expected_stack)
        self.assertEqual(source_patch_stack_sha256(body.patches), expected_stack)
        self.assertEqual(
            decode_source_manifest_body(encode_source_manifest_body(body)),
            body,
        )
        self.assertEqual(
            encode_source_manifest_body(body),
            source_manifest_canonical_json(body.to_dict()),
        )
        raw_body = json.loads(encode_source_manifest_body(body))
        go_style_body = source_manifest_canonical_json(raw_body)
        self.assertIn('"constant_value":2', go_style_body)
        self.assertNotIn('"constant_value":2.0', go_style_body)
        self.assertIn('"constant_value":1e-7', go_style_body)
        decoded_body = decode_source_manifest_body(go_style_body)
        self.assertEqual(
            decoded_body.body_sha256,
            hashlib.sha256(go_style_body.encode("utf-8")).hexdigest(),
        )

        engine_a = _engine_manifest(request, body, source_path="C:/one", prepared="one")
        engine_b = replace(engine_a, source_path="D:/two", prepared_at_utc="two")
        first = SourceManifestBinding.from_engine_manifest(
            manifest_body=body,
            engine_manifest=engine_a,
            engine_binding_sha256=request.engine_binding_sha256,
        )
        second = SourceManifestBinding.from_engine_manifest(
            manifest_body=body,
            engine_manifest=engine_b,
            engine_binding_sha256=request.engine_binding_sha256,
        )
        self.assertEqual(first, binding)
        self.assertEqual(first.binding_sha256, second.binding_sha256)
        self.assertEqual(
            decode_source_manifest_binding(encode_source_manifest_binding(first)),
            first,
        )

        bad_metadata = dict(engine_a.patch_metadata)
        bad_metadata["patch_file_sha256"] = json.dumps(
            {body.patches[0].path: "0" * 64}, separators=(",", ":")
        )
        with self.assertRaisesRegex(TraceContractError, "per-file patch"):
            SourceManifestBinding.from_engine_manifest(
                manifest_body=body,
                engine_manifest=replace(engine_a, patch_metadata=bad_metadata),
                engine_binding_sha256=request.engine_binding_sha256,
            )

    def test_v4_is_strictly_external_manifest_bound_without_v3_downgrade(self) -> None:
        request, raw, binding, _ = _fixture()
        payload = canonical_json(raw)

        with self.assertRaisesRegex(TraceContractError, "external source manifest"):
            decode_engine_trace(payload, request=request)

        direct = decode_engine_trace_v4(
            payload,
            request=request,
            source_manifest_binding=binding,
        )
        dispatched = decode_engine_trace(
            payload,
            request=request,
            source_manifest_binding=binding,
        )
        self.assertIsInstance(direct, SourceDependencyEvidenceTrace)
        self.assertEqual(direct, dispatched)
        self.assertFalse(direct.exact_replay_eligible)
        self.assertFalse(direct.hard_prune_allowed)
        self.assertFalse(direct.publishable)

        v3 = deepcopy(raw)
        v3["schema_version"] = ENGINE_TRACE_V3_SCHEMA_VERSION
        v3["capability"] = ENGINE_TRACE_V3_CAPABILITY
        del v3["source_manifest_body_sha256"]
        del v3["source_occurrences"]
        del v3["source_value_bindings"]
        self.assertEqual(
            direct.reaction_evidence,
            decode_engine_trace_v3(canonical_json(v3), request=request),
        )

        missing = deepcopy(raw)
        del missing["source_value_bindings"]
        with self.assertRaisesRegex(TraceContractError, "missing"):
            decode_engine_trace(
                canonical_json(missing),
                request=request,
                source_manifest_binding=binding,
            )

        wrong_body = deepcopy(raw)
        wrong_body["source_manifest_body_sha256"] = "0" * 64
        with self.assertRaisesRegex(TraceContractError, "does not match"):
            decode_engine_trace_v4(
                canonical_json(wrong_body),
                request=request,
                source_manifest_binding=binding,
            )

    def test_supported_hp_slice_and_opaque_closures_are_non_authoritative(self) -> None:
        request, raw, binding, ids = _fixture()
        evidence = decode_engine_trace_v4(
            canonical_json(raw),
            request=request,
            source_manifest_binding=binding,
        )

        synthetic = evaluate_source_value_binding(evidence, "source-binding:0:0", {})
        self.assertTrue(math.isclose(synthetic.baseline_value, 13.0000001))
        self.assertTrue(math.isclose(synthetic.candidate_value, 13.0000001))
        self.assertEqual(synthetic.uncertainty_codes, ())

        hp = evaluate_source_value_binding(
            evidence,
            "source-binding:1:0",
            {("furina", "max_hp"): 22_000.0},
        )
        self.assertTrue(math.isclose(hp.baseline_value, 1_100.0))
        self.assertTrue(math.isclose(hp.candidate_value, 2_200.0))
        self.assertEqual(hp.uncertainty_codes, ())
        self.assertFalse(hp.authoritative)
        self.assertFalse(hp.hard_prune_allowed)
        self.assertFalse(hp.publishable)

        opaque = evaluate_source_value_binding(
            evidence,
            "source-binding:3:0",
            {("furina", "hp%"): 0.5},
        )
        self.assertEqual(opaque.baseline_value, 7.0)
        self.assertEqual(opaque.candidate_value, 7.0)
        self.assertIn("opaque_candidate_dependencies_incomplete", opaque.uncertainty_codes)
        self.assertTrue(
            any(code.startswith("opaque_frozen:") for code in opaque.uncertainty_codes)
        )

        furina_occurrence = next(
            row for row in evidence.occurrences if row.source_id == ids["furina"]
        )
        self.assertFalse(
            any(
                row.occurrence_id == furina_occurrence.occurrence_id
                for row in evidence.value_bindings
            )
        )
        self.assertIn(
            f"source_occurrence_unbound:{furina_occurrence.occurrence_id}",
            evidence.uncertainty_codes,
        )
        furina_entry = binding.manifest_body.entry_by_id(ids["furina"])
        self.assertIsNotNone(furina_entry)
        self.assertEqual(furina_entry.template.status, SourceSliceStatus.SUPPORTED)

    def test_v4_rejects_source_and_runtime_binding_tampering(self) -> None:
        request, raw, binding, _ = _fixture()
        mutations = (
            (
                "unknown source",
                lambda row: row["source_occurrences"][0].__setitem__(
                    "source_id", "0" * 64
                ),
                "unknown source_id",
            ),
            (
                "template",
                lambda row: row["source_value_bindings"][0].__setitem__(
                    "template_sha256", "0" * 64
                ),
                "template does not match",
            ),
            (
                "output",
                lambda row: row["source_value_bindings"][1].__setitem__(
                    "observed_value", 1099.0
                ),
                "baseline does not match",
            ),
            (
                "candidate read frame",
                lambda row: row["source_value_bindings"][1]["parameters"][1].__setitem__(
                    "read_frame", 119
                ),
                "read frame",
            ),
            (
                "candidate observed value",
                lambda row: row["source_value_bindings"][1]["parameters"][1].__setitem__(
                    "observed_value", 12_000.0
                ),
                "baseline does not match|terminal snapshot",
            ),
            (
                "parameter set",
                lambda row: row["source_value_bindings"][1]["parameters"].pop(),
                "parameters do not match",
            ),
        )
        for label, mutate, expected in mutations:
            changed = deepcopy(raw)
            mutate(changed)
            with self.subTest(label=label):
                with self.assertRaisesRegex(TraceContractError, expected):
                    decode_engine_trace_v4(
                        canonical_json(changed),
                        request=request,
                        source_manifest_binding=binding,
                    )

    def test_v4_accepts_live_candidate_value_captured_before_queue_seam(self) -> None:
        request, raw, binding, _ = _fixture()
        raw["source_value_bindings"][1]["parameters"][1]["read_frame"] = 117

        evidence = decode_engine_trace_v4(
            canonical_json(raw),
            request=request,
            source_manifest_binding=binding,
        )

        parameter = evidence.value_bindings[1].parameters[1]
        self.assertEqual(parameter.read_mode, ValueReadMode.LIVE)
        self.assertEqual(parameter.read_frame, 117)


def _fixture():
    request = replace(_document().request, character_keys=("furina",))
    synthetic = _supported_template(
        (
            SourceIRNode(0, SourceIROperator.PARAM, (), parameter_key="x"),
            SourceIRNode(1, SourceIROperator.CONST, (), constant_value=2.0),
            SourceIRNode(2, SourceIROperator.MUL, (0, 1)),
            SourceIRNode(3, SourceIROperator.CONST, (), constant_value=3.0),
            SourceIRNode(4, SourceIROperator.ADD, (2, 3)),
            SourceIRNode(5, SourceIROperator.CONST, (), constant_value=1e-7),
            SourceIRNode(6, SourceIROperator.ADD, (4, 5)),
        ),
        ("x",),
    )
    hp = _supported_template(
        (
            SourceIRNode(0, SourceIROperator.PARAM, (), parameter_key="p0"),
            SourceIRNode(1, SourceIROperator.PARAM, (), parameter_key="p1"),
            SourceIRNode(2, SourceIROperator.MUL, (0, 1)),
        ),
        ("p0", "p1"),
    )
    furina = _supported_template(
        (
            SourceIRNode(0, SourceIROperator.PARAM, (), parameter_key="p0"),
            SourceIRNode(1, SourceIROperator.PARAM, (), parameter_key="p1"),
            SourceIRNode(2, SourceIROperator.MIN, (0, 1)),
            SourceIRNode(3, SourceIROperator.PARAM, (), parameter_key="p2"),
            SourceIRNode(4, SourceIROperator.MUL, (2, 3)),
        ),
        ("p0", "p1", "p2"),
    )
    opaque = _opaque_template("unsupported_control_flow")
    specifications = (
        ("synthetic", "internal/gtt/synthetic.go", "syntheticFormula", SourceSeam.EVENT_CALLBACK, synthetic),
        ("furina", "internal/characters/furina/burst.go", "burstDamageBonus", SourceSeam.MODIFIER_AMOUNT, furina),
        ("hp", "internal/characters/furina/pets.go", "queuePetAttack", SourceSeam.QUEUED_ATTACK, hp),
        ("opaque", "internal/characters/example/task.go", "opaqueTask", SourceSeam.TASK_CALLBACK, opaque),
    )
    entries = []
    ids: dict[str, str] = {}
    for ordinal, (name, module, symbol, seam, template) in enumerate(specifications):
        locator = SourceLocator(module, symbol, seam, ordinal)
        ids[name] = locator.source_id
        entries.append(
            SourceManifestEntry(
                source_id=locator.source_id,
                locator=locator,
                source_node_sha256=hashlib.sha256(name.encode("ascii")).hexdigest(),
                template=template,
            )
        )
    patches = (
        SourcePatchDigest(
            path="0001-trace.patch",
            sha256=hashlib.sha256(b"patch-one").hexdigest(),
        ),
    )
    body = SourceManifestBody(
        compiler_version="gtt_source_compiler_v1",
        upstream_repo="github.com/genshinsim/gcsim",
        upstream_ref="v0.0.0-test",
        pristine_source_tree_sha256="a" * 64,
        patches=patches,
        patch_stack_sha256=source_patch_stack_sha256(patches),
        patched_source_tree_sha256="c" * 64,
        trace_schema_version=4,
        trace_capability=ENGINE_TRACE_V4_CAPABILITY,
        formula_identities=(
            SourceFormulaIdentity(
                "gtt_source_ir_v1",
                "243f34e59a6a6df869ccafa0bcdfdcb80a986ff5ebf9a41e52059b1ee5e95208",
            ),
        ),
        go_toolchain=SourceGoToolchain("go1.24.1", "windows", "amd64"),
        build_flags=("-trimpath",),
        entries=tuple(sorted(entries, key=lambda row: row.source_id)),
    )
    binding = SourceManifestBinding.build(
        manifest_body=body,
        source_tree_sha256=body.pristine_source_tree_sha256,
        engine_tree_sha256="e" * 64,
        engine_artifact_sha256=request.engine_artifact_sha256,
        engine_binding_sha256=request.engine_binding_sha256,
    )
    raw = _raw_v4(request, binding, ids, synthetic, hp, opaque)
    return request, raw, binding, ids


def _raw_v4(request, binding, ids, synthetic, hp, opaque):
    raw = deepcopy(_raw_engine_trace_v2(request))
    raw["schema_version"] = ENGINE_TRACE_V4_SCHEMA_VERSION
    raw["capability"] = ENGINE_TRACE_V4_CAPABILITY
    hit = raw["hits"][0]
    hit["parent_target_key"] = None
    hit["reaction_formula"] = None
    character = _provider("character", "furina", 0)
    hit["provider"] = character
    hit["attack_mods"] = [
        {
            "modifier_key": "attackmod:furina-burst",
            "source_key": "character:furina",
            "owner_index": 0,
            "accepted": True,
            "before_damage": None,
            "after_damage": None,
            "delta": {"dmg%": 0.417},
            "provider": character,
        }
    ]
    hit.update(
        {
            "mult": 0.0,
            "flat_dmg": 1100.0,
            "base_damage": 1100.0,
            "damage_bonus": 0.617,
            "pre_amp_damage": 1100.0 * 1.617 * 0.5 * 0.9,
            "uncapped_damage": 1100.0 * 1.617 * 0.5 * 0.9,
            "actual_damage": 1100.0 * 1.617 * 0.5 * 0.9,
            "reported_damage": 1100.0 * 1.617 * 0.5 * 0.9,
            "hp_after": 10000.0 - 1100.0 * 1.617 * 0.5 * 0.9,
        }
    )
    raw["source_manifest_body_sha256"] = binding.manifest_body_sha256
    raw["source_occurrences"] = [
        _occurrence(0, "source-occurrence:0", ids["synthetic"], "event_callback", 100, _provider("global_rule", "synthetic", -1), None),
        _occurrence(1, "source-occurrence:1", ids["hp"], "queued_attack", 118, character, "hit:1"),
        _occurrence(2, "source-occurrence:2", ids["furina"], "modifier_amount", 120, character, "hit:1"),
        _occurrence(3, "source-occurrence:3", ids["opaque"], "task_callback", 121, _provider("global_rule", "task", -1), None),
    ]
    raw["source_value_bindings"] = [
        {
            "binding_id": "source-binding:0:0",
            "occurrence_id": "source-occurrence:0",
            "template_sha256": synthetic.template_sha256,
            "output_kind": SourceOutputKind.DIAGNOSTIC_SCALAR.value,
            "terminal_event_id": None,
            "provider_sequence_index": None,
            "output_key": "synthetic_value",
            "observed_value": 13.0000001,
            "parameters": [
                _parameter("x", "frozen_source_value", 5.0, None, None, None, "constant", 0, True)
            ],
        },
        {
            "binding_id": "source-binding:1:0",
            "occurrence_id": "source-occurrence:1",
            "template_sha256": hp.template_sha256,
            "output_kind": SourceOutputKind.TERMINAL_FLAT_DMG.value,
            "terminal_event_id": "hit:1",
            "provider_sequence_index": None,
            "output_key": "flat_dmg",
            "observed_value": 1100.0,
            "parameters": [
                _parameter("p0", "frozen_source_value", 0.1, None, None, None, "constant", 118, True),
                _parameter("p1", "candidate_stat", 11000.0, 0, "furina", "max_hp", "live", 118, True),
            ],
        },
        {
            "binding_id": "source-binding:3:0",
            "occurrence_id": "source-occurrence:3",
            "template_sha256": opaque.template_sha256,
            "output_kind": SourceOutputKind.DIAGNOSTIC_SCALAR.value,
            "terminal_event_id": None,
            "provider_sequence_index": None,
            "output_key": "opaque_value",
            "observed_value": 7.0,
            "parameters": [],
        },
    ]
    return raw


def _supported_template(nodes, parameters):
    return SourceSliceTemplate.build(
        status=SourceSliceStatus.SUPPORTED,
        nodes=nodes,
        root_node_id=nodes[-1].node_id,
        parameter_keys=parameters,
        dependencies_complete=True,
        stop_reason_code=None,
    )


def _opaque_template(reason):
    return SourceSliceTemplate.build(
        status=SourceSliceStatus.OPAQUE_FROZEN,
        nodes=(),
        root_node_id=None,
        parameter_keys=(),
        dependencies_complete=False,
        stop_reason_code=reason,
    )


def _provider(kind, key, owner_index):
    return {
        "known": True,
        "kind": kind,
        "key": key,
        "owner_index": owner_index,
        "piece_count": 0,
    }


def _occurrence(index, occurrence_id, source_id, seam, frame, provider, event):
    return {
        "sequence_index": index,
        "occurrence_id": occurrence_id,
        "source_id": source_id,
        "seam": seam,
        "frame": frame,
        "parent_occurrence_id": None,
        "provider": provider,
        "terminal_event_id": event,
    }


def _parameter(key, kind, value, actor_index, actor_key, stat_key, read_mode, read_frame, complete):
    return {
        "parameter_key": key,
        "kind": kind,
        "observed_value": value,
        "actor_index": actor_index,
        "actor_key": actor_key,
        "stat_key": stat_key,
        "read_mode": read_mode,
        "read_frame": read_frame,
        "candidate_dependency_complete": complete,
    }


def _engine_manifest(request, body, *, source_path, prepared):
    patch_paths = [row.path for row in body.patches]
    patch_hashes = {row.path: row.sha256 for row in body.patches}
    return GcsimEngineManifest(
        engine_id="engine-test",
        source_label="official",
        source_path=source_path,
        source_tree_hash=body.pristine_source_tree_sha256,
        engine_tree_hash="e" * 64,
        prepared_at_utc=prepared,
        patch_backend="git_apply",
        patch_count=len(body.patches),
        patch_metadata={
            "patch_files": json.dumps(patch_paths),
            "patch_file_sha256": json.dumps(
                patch_hashes, ensure_ascii=True, sort_keys=True, separators=(",", ":")
            ),
            "patch_stack_sha256": body.patch_stack_sha256,
        },
        capabilities=("gtt_source_manifest_v1",),
        metadata={
            "artifact_sha256": request.engine_artifact_sha256,
            "go_version": body.go_toolchain.version,
            "source_manifest_body_sha256": body.body_sha256,
            "source_manifest_compiler_version": body.compiler_version,
            "source_manifest_patched_tree_sha256": body.patched_source_tree_sha256,
        },
    )


if __name__ == "__main__":
    unittest.main()
