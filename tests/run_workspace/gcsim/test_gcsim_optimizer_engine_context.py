from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from run_workspace.gcsim.engine_store import (
    GcsimEngineInstallation,
    GcsimEngineManifest,
)
from run_workspace.gcsim.optimizer_engine_context import (
    GcsimOptimizerEngineContextError,
    build_gcsim_optimizer_engine_context,
)


class GcsimOptimizerEngineContextTest(unittest.TestCase):
    def test_resealed_context_binds_tree_catalog_and_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_engine_fixture(root)
            manifest = _manifest(root)
            diagnostic = build_gcsim_optimizer_engine_context(
                GcsimEngineInstallation("engine", root, manifest),
                require_resealed=False,
            )
            sealed_manifest = replace(
                manifest,
                engine_tree_hash=diagnostic.engine_tree_sha256,
                metadata={
                    **dict(manifest.metadata),
                    "artifact_sha256": diagnostic.artifact_sha256,
                },
            )

            context = build_gcsim_optimizer_engine_context(
                GcsimEngineInstallation("engine", root, sealed_manifest)
            )

            self.assertTrue(context.trusted)
            self.assertEqual(context.issues, ())
            self.assertEqual(context.optimizer_contract_version, "gcsim-v2.42.2")
            self.assertEqual(context.catalog.modeled_four_piece_keys, ("alpha",))
            self.assertEqual(len(context.binding_sha256), 64)

            (root / "build" / "gtt-gcsim.exe").write_bytes(b"tampered")
            with self.assertRaisesRegex(
                GcsimOptimizerEngineContextError,
                "not resealed",
            ):
                build_gcsim_optimizer_engine_context(
                    GcsimEngineInstallation("engine", root, sealed_manifest)
                )


def _manifest(root: Path) -> GcsimEngineManifest:
    return GcsimEngineManifest(
        engine_id="engine",
        source_label="gcsim-v2.42.2",
        source_path=str(root),
        source_tree_hash="source",
        engine_tree_hash="",
        prepared_at_utc="2026-07-19T00:00:00+00:00",
        patch_backend="fixture",
        patch_count=0,
        metadata={
            "artifact_relative_path": "build/gtt-gcsim.exe",
            "artifact_version_stdout": "fixture-version",
        },
    )


def _write_engine_fixture(root: Path) -> None:
    artifact = root / "build" / "gtt-gcsim.exe"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"engine")
    package = root / "internal" / "artifacts" / "alpha"
    package.mkdir(parents=True)
    (package / "config.yml").write_text("key: alpha\n", encoding="utf-8")
    (package / "alpha.go").write_text(
        "package alpha\n"
        "func init() { core.RegisterSetFunc(keys.Alpha, NewSet) }\n"
        "func NewSet(count int) { if count >= 2 {}; if count >= 4 {} }\n",
        encoding="utf-8",
    )
    issues = (
        root
        / "ui"
        / "packages"
        / "docs"
        / "src"
        / "components"
        / "Issues"
        / "artifact_data.json"
    )
    issues.parent.mkdir(parents=True)
    issues.write_text(json.dumps({}), encoding="utf-8")
    optimizer = root / "pkg" / "optimization" / "substats.go"
    optimizer.parent.mkdir(parents=True)
    optimizer.write_text(
        "func load() { s.artifactSets4Star = []keys.Set{} }\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
