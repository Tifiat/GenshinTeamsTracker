from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from run_workspace.gcsim.artifact_build import build_gcsim_artifact
from run_workspace.gcsim.source_manifest_build import (
    SOURCE_MANIFEST_BODY_KIND,
    SOURCE_MANIFEST_BODY_RELATIVE_PATH,
    SOURCE_MANIFEST_GENERATED_GO_RELATIVE_PATH,
    SOURCE_MANIFEST_INPUT_KIND,
    SOURCE_MANIFEST_OVERLAY_DIR_RELATIVE_PATH,
    SOURCE_MANIFEST_OVERLAY_RELATIVE_PATH,
    canonical_json,
    compute_patched_source_tree_sha256,
    prepare_source_manifest,
)


class GcsimSourceManifestBuildTest(unittest.TestCase):
    def test_relative_engine_root_builds_into_the_same_directory(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            root = Path(tmp).resolve()
            _write_generator_marker(root)
            _write_gtt_marker(root)
            runner = _BuildRunner()
            result = build_gcsim_artifact(
                root.relative_to(Path.cwd()),
                go_work_dir=root / ".go",
                runner=runner,
                require_gtt_marker=True,
                source_manifest_binding_input=_binding_input(),
            )
            self.assertTrue(result.runtime_ready, result.error)
            command = next(call for call in runner.calls if call[:2] == ("go", "build"))
            self.assertEqual(Path(command[command.index("-o") + 1]), root / "build/gtt-gcsim.exe")
            self.assertTrue((root / "build/gtt-gcsim.exe").is_file())

    def test_manifest_numeric_canonicalization_matches_go_json(self) -> None:
        self.assertEqual(
            canonical_json(
                {"integral": 2.0, "small": 1e-7, "large": 1e20, "negative_zero": -0.0}
            ),
            (
                '{"integral":2,"large":100000000000000000000,'
                '"negative_zero":-0,"small":1e-7}'
            ),
        )

    def test_generator_round_trip_is_canonical_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_generator_marker(root)
            runner = _GeneratorRunner()

            first = prepare_source_manifest(
                root,
                binding_input=_binding_input(),
                go_version="go1.24.1",
                go_os="windows",
                go_arch="amd64",
                go_executable="go",
                env={},
                timeout_seconds=30,
                runner=runner,
            )
            first_bytes = (root / SOURCE_MANIFEST_BODY_RELATIVE_PATH).read_bytes()
            second = prepare_source_manifest(
                root,
                binding_input=_binding_input(),
                go_version="go1.24.1",
                go_os="windows",
                go_arch="amd64",
                go_executable="go",
                env={},
                timeout_seconds=30,
                runner=runner,
            )

            self.assertTrue(first.ready)
            self.assertEqual(first.status, "source_manifest_passed")
            self.assertEqual(first.body_sha256, second.body_sha256)
            self.assertEqual(
                first.body_sha256,
                hashlib.sha256(
                    (root / SOURCE_MANIFEST_BODY_RELATIVE_PATH)
                    .read_text(encoding="utf-8")
                    .strip()
                    .encode("utf-8")
                ).hexdigest(),
            )
            self.assertEqual(
                first_bytes,
                (root / SOURCE_MANIFEST_BODY_RELATIVE_PATH).read_bytes(),
            )
            self.assertEqual(first.compiler_version, "gtt_source_compiler_v2")
            self.assertIn("-binding-in", first.command)
            self.assertIn("-overlay-out", first.command)
            self.assertEqual(
                first.overlay_relative_path,
                SOURCE_MANIFEST_OVERLAY_RELATIVE_PATH.as_posix(),
            )

    def test_required_generator_without_binding_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_generator_marker(root)

            result = prepare_source_manifest(
                root,
                binding_input=None,
                go_version="go1.24.1",
                go_os="windows",
                go_arch="amd64",
                go_executable="go",
                env={},
                timeout_seconds=30,
                runner=_GeneratorRunner(),
            )

            self.assertFalse(result.ready)
            self.assertEqual(result.status, "binding_input_missing")

    def test_generator_cannot_rewrite_bound_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_generator_marker(root)
            runner = _GeneratorRunner(rewrite={"upstream_ref": "wrong"})

            result = prepare_source_manifest(
                root,
                binding_input=_binding_input(),
                go_version="go1.24.1",
                go_os="windows",
                go_arch="amd64",
                go_executable="go",
                env={},
                timeout_seconds=30,
                runner=runner,
            )

            self.assertFalse(result.ready)
            self.assertEqual(result.status, "source_manifest_output_invalid")
            self.assertIn("changed bound field", result.error)

    def test_generator_body_rejected_when_strict_v6_decoder_rejects_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_generator_marker(root)
            runner = _GeneratorRunner(
                rewrite={"compiler_version": "gtt_go_source_compiler_v1"}
            )

            result = prepare_source_manifest(
                root,
                binding_input=_binding_input(),
                go_version="go1.24.1",
                go_os="windows",
                go_arch="amd64",
                go_executable="go",
                env={},
                timeout_seconds=30,
                runner=runner,
            )

            self.assertFalse(result.ready)
            self.assertEqual(result.status, "source_manifest_output_invalid")
            self.assertIn("compiler_version", result.error)

    def test_artifact_build_binds_generated_body_to_executable_info(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_generator_marker(root)
            _write_gtt_marker(root)
            runner = _BuildRunner()

            result = build_gcsim_artifact(
                root,
                go_work_dir=root / ".go",
                runner=runner,
                require_gtt_marker=True,
                source_manifest_binding_input=_binding_input(),
            )

            self.assertTrue(result.runtime_ready)
            self.assertTrue(result.source_manifest_ready)
            self.assertEqual(result.status, "gtt_info_passed")
            self.assertEqual(len(result.source_manifest_body_sha256), 64)
            build_command = next(call for call in runner.calls if call[:2] == ("go", "build"))
            self.assertIn("-trimpath", build_command)
            overlay_index = build_command.index("-overlay")
            self.assertEqual(
                build_command[overlay_index + 1],
                str((root / SOURCE_MANIFEST_OVERLAY_RELATIVE_PATH).resolve()),
            )

    def test_generator_overlay_escape_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_generator_marker(root)
            runner = _GeneratorRunner(escape_overlay=True)

            result = prepare_source_manifest(
                root,
                binding_input=_binding_input(),
                go_version="go1.24.1",
                go_os="windows",
                go_arch="amd64",
                go_executable="go",
                env={},
                timeout_seconds=30,
                runner=runner,
            )

            self.assertFalse(result.ready)
            self.assertEqual(result.status, "source_manifest_output_invalid")
            self.assertIn("inside overlay directory", result.error)

    def test_generator_cannot_claim_a_different_patched_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_generator_marker(root)

            result = prepare_source_manifest(
                root,
                binding_input=_binding_input(),
                go_version="go1.24.1",
                go_os="windows",
                go_arch="amd64",
                go_executable="go",
                env={},
                timeout_seconds=30,
                runner=_GeneratorRunner(wrong_tree_hash=True),
            )

            self.assertFalse(result.ready)
            self.assertEqual(result.status, "source_manifest_output_invalid")
            self.assertIn("independently hashed source tree", result.error)

    def test_patched_tree_hash_excludes_only_generated_and_build_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "internal" / "formula.go"
            source.parent.mkdir(parents=True)
            source.write_text("package internal\n", encoding="utf-8")
            initial = compute_patched_source_tree_sha256(root)

            generated = root / SOURCE_MANIFEST_GENERATED_GO_RELATIVE_PATH
            generated.parent.mkdir(parents=True)
            generated.write_text("generated one\n", encoding="utf-8")
            build_output = root / "build" / "temporary.json"
            build_output.parent.mkdir(parents=True)
            build_output.write_text("temporary\n", encoding="utf-8")
            self.assertEqual(initial, compute_patched_source_tree_sha256(root))

            generated.write_text("generated two\n", encoding="utf-8")
            build_output.write_text("changed temporary\n", encoding="utf-8")
            self.assertEqual(initial, compute_patched_source_tree_sha256(root))

            source.write_text("package internal\n// changed\n", encoding="utf-8")
            self.assertNotEqual(initial, compute_patched_source_tree_sha256(root))

    def test_artifact_build_rejects_mismatched_embedded_body_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_generator_marker(root)
            _write_gtt_marker(root)
            runner = _BuildRunner(reported_hash="0" * 64)

            result = build_gcsim_artifact(
                root,
                go_work_dir=root / ".go",
                runner=runner,
                require_gtt_marker=True,
                source_manifest_binding_input=_binding_input(),
            )

            self.assertFalse(result.runtime_ready)
            self.assertEqual(result.status, "source_manifest_info_mismatch")


class _GeneratorRunner:
    def __init__(
        self,
        *,
        rewrite: dict[str, object] | None = None,
        escape_overlay: bool = False,
        wrong_tree_hash: bool = False,
    ) -> None:
        self.rewrite = dict(rewrite or {})
        self.escape_overlay = escape_overlay
        self.wrong_tree_hash = wrong_tree_hash

    def __call__(self, command, cwd: Path, _env, _timeout):
        input_path = cwd / command[command.index("-binding-in") + 1]
        body_path = cwd / command[command.index("-json-out") + 1]
        go_path = cwd / command[command.index("-go-out") + 1]
        overlay_path = cwd / command[command.index("-overlay-out") + 1]
        overlay_dir = cwd / command[command.index("-overlay-dir") + 1]
        go_path.parent.mkdir(parents=True, exist_ok=True)
        go_path.write_text("package gttsource\n", encoding="utf-8")
        original = cwd / "internal" / "synthetic" / "formula.go"
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_text("package synthetic\n", encoding="utf-8")
        replacement = overlay_dir / "internal" / "synthetic" / "formula.go"
        replacement.parent.mkdir(parents=True, exist_ok=True)
        replacement.write_text("package synthetic\n", encoding="utf-8")
        if self.escape_overlay:
            escaped = cwd.parent / "escaped-formula.go"
            escaped.write_text("package synthetic\n", encoding="utf-8")
            replacement = escaped
        overlay_path.parent.mkdir(parents=True, exist_ok=True)
        overlay_path.write_text(
            json.dumps(
                {"Replace": {str(original.resolve()): str(replacement.resolve())}},
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        body = json.loads(input_path.read_text(encoding="utf-8"))
        body["kind"] = SOURCE_MANIFEST_BODY_KIND
        body["compiler_version"] = "gtt_source_compiler_v2"
        body["patched_source_tree_sha256"] = (
            "b" * 64
            if self.wrong_tree_hash
            else compute_patched_source_tree_sha256(cwd)
        )
        body["entries"] = []
        body.update(self.rewrite)
        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_text(json.dumps(body), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "generated\n", "")


class _BuildRunner:
    def __init__(self, *, reported_hash: str | None = None) -> None:
        self.reported_hash = reported_hash
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, command, cwd, env, timeout):
        command = tuple(str(part) for part in command)
        self.calls.append(command)
        if command[:2] == ("go", "version"):
            return subprocess.CompletedProcess(
                command, 0, "go version go1.24.1 windows/amd64\n", ""
            )
        if "./cmd/gtt-source-manifest" in command:
            return _GeneratorRunner()(command, Path(cwd), env, timeout)
        if command[:2] == ("go", "build"):
            output = Path(command[command.index("-o") + 1])
            if not output.is_absolute():
                output = Path(cwd) / output
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"bound executable")
            return subprocess.CompletedProcess(command, 0, "built\n", "")
        if command[-1] == "-version":
            return subprocess.CompletedProcess(command, 0, "gcsim test\n", "")
        if command[-1] == "-gtt-info":
            body_text = (
                Path(cwd) / SOURCE_MANIFEST_BODY_RELATIVE_PATH
            ).read_text(encoding="utf-8").strip()
            body = json.loads(body_text)
            body_sha256 = hashlib.sha256(body_text.encode("utf-8")).hexdigest()
            payload = {
                "gtt_engine": True,
                "gtt_patch_version": "gtt-source-manifest-v1",
                "capabilities": ["gtt_engine_marker", "gtt_source_manifest_v1"],
                "sequential_waves": True,
                "upstream_version": "gcsim test",
                "source_manifest_body_sha256": self.reported_hash or body_sha256,
                "source_manifest_compiler_version": body["compiler_version"],
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
        raise AssertionError(f"Unexpected command: {command}")


def _write_generator_marker(root: Path) -> None:
    path = root / "cmd" / "gtt-source-manifest" / "main.go"
    path.parent.mkdir(parents=True)
    path.write_text("package main\n", encoding="utf-8")


def _write_gtt_marker(root: Path) -> None:
    main = root / "cmd" / "gcsim" / "main.go"
    main.parent.mkdir(parents=True, exist_ok=True)
    main.write_text("package main\n// gtt-info\n", encoding="utf-8")
    info = root / "pkg" / "gtt" / "info.go"
    info.parent.mkdir(parents=True, exist_ok=True)
    info.write_text("package gtt\n", encoding="utf-8")


def _binding_input() -> dict[str, object]:
    patches = [{"path": "0013.patch", "sha256": "c" * 64}]
    patch_stack_payload = json.dumps(
        {"schema_version": 1, "patches": patches},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "schema_version": 1,
        "kind": SOURCE_MANIFEST_INPUT_KIND,
        "upstream_repo": "https://github.com/genshinsim/gcsim",
        "upstream_ref": "v-test",
        "pristine_source_tree_sha256": "a" * 64,
        "patches": patches,
        "patch_stack_sha256": hashlib.sha256(
            patch_stack_payload.encode("utf-8")
        ).hexdigest(),
        "trace_schema_version": 6,
        "trace_capability": "gtt_trace_equation_v6",
        "formula_identities": [
            {"id": "gtt_trace_formula_v1", "sha256": "e" * 64},
            {
                "id": "gtt_source_ir_v2",
                "sha256": (
                    "8b8dfcb9cb97e2b06145638e47ba915a"
                    "6016a11f956708d7de7ee826ae730792"
                ),
            },
        ],
    }


if __name__ == "__main__":
    unittest.main()
