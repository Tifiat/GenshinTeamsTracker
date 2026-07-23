from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from run_workspace.gcsim.artifact_set_catalog import (
    GcsimArtifactSetCapability,
    GcsimArtifactSetCatalog,
    GcsimArtifactSetCatalogError,
    load_gcsim_artifact_set_catalog,
)


class GcsimArtifactSetCatalogTest(unittest.TestCase):
    def test_catalog_distinguishes_modeled_and_explicitly_missing_bonuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_set(
                root,
                package="alpha",
                key="alphaset",
                source="""
package alpha
func init() { core.RegisterSetFunc(keys.Alpha, NewSet) }
func NewSet(count int) {
    if count >= 2 { /* 2pc */ }
    if count >= 4 { /* 4pc */ }
}
""",
            )
            _write_set(
                root,
                package="beta",
                key="betaset",
                source="""
package beta
func init() { core.RegisterSetFunc(keys.Beta, NewSet) }
func NewSet(count int) {
    if count >= 2 { /* 2pc */ }
    if count >= 4 { log("4pc not implemented") }
}
""",
            )
            _write_issues(root, {"betaset": ["4pc is not implemented yet"]})
            _write_four_star_sets(root, {"Beta"})

            catalog = load_gcsim_artifact_set_catalog(root)

            self.assertEqual(catalog.modeled_four_piece_keys, ("alphaset",))
            self.assertEqual(catalog.modeled_two_piece_keys, ("alphaset", "betaset"))
            self.assertTrue(catalog.get("ALPHASET").four_piece_modeled)
            self.assertFalse(catalog.get("betaset").four_piece_modeled)
            self.assertEqual(catalog.get("alphaset").max_rarity, 5)
            self.assertEqual(catalog.get("betaset").max_rarity, 4)
            self.assertEqual(catalog.modeled_five_star_four_piece_keys, ("alphaset",))
            self.assertEqual(len(catalog.source_fingerprint), 64)

    def test_catalog_detects_source_only_not_implemented_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_set(
                root,
                package="lava",
                key="lava",
                source="""
package lava
func init() { core.RegisterSetFunc(keys.Lava, NewSet) }
func NewSet(count int) {
    if count >= 2 { log("2 pc not implemented") }
    if count >= 4 { /* 4 Piece implemented */ }
}
""",
            )
            _write_issues(root, {})
            _write_four_star_sets(root, set())

            catalog = load_gcsim_artifact_set_catalog(root)

            capability = catalog.get("lava")
            self.assertFalse(capability.two_piece_modeled)
            self.assertTrue(capability.four_piece_modeled)
            self.assertFalse(capability.complete_four_piece_modeled)
            self.assertEqual(catalog.modeled_four_piece_keys, ())

    def test_catalog_requires_issue_snapshot_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_set(
                root,
                package="alpha",
                key="alpha",
                source="func init() { core.RegisterSetFunc(keys.Alpha, NewSet) } // 4pc",
            )

            with self.assertRaises(GcsimArtifactSetCatalogError):
                load_gcsim_artifact_set_catalog(root)

            catalog = load_gcsim_artifact_set_catalog(
                root,
                require_issue_metadata=False,
                require_optimizer_metadata=False,
            )
            self.assertEqual(
                catalog.warnings,
                (
                    "artifact_issue_metadata_missing",
                    "optimizer_set_rarity_metadata_missing",
                ),
            )
            capability = catalog.get("alpha")
            self.assertTrue(capability.registered)
            self.assertFalse(capability.complete_four_piece_modeled)

    def test_comments_and_test_files_do_not_create_modeled_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_set(
                root,
                package="alpha",
                key="alpha",
                source="""
package alpha
// core.RegisterSetFunc(keys.Alpha, NewSet)
// if count >= 2 {} and if count >= 4 {}
func init() {}
""",
            )
            package_dir = root / "internal" / "artifacts" / "alpha"
            (package_dir / "alpha_test.go").write_text(
                "func fake() { core.RegisterSetFunc(keys.Alpha, NewSet); "
                "if count >= 2 {}; if count >= 4 {} }",
                encoding="utf-8",
            )
            _write_issues(root, {})
            _write_four_star_sets(root, set())

            catalog = load_gcsim_artifact_set_catalog(root)

            capability = catalog.get("alpha")
            self.assertFalse(capability.registered)
            self.assertFalse(capability.has_two_piece_code)
            self.assertFalse(capability.has_four_piece_code)
            self.assertFalse(capability.complete_four_piece_modeled)

    def test_catalog_rejects_duplicate_keys_and_freezes_lookup(self) -> None:
        first = _capability("same")
        second = _capability(" SAME ")

        with self.assertRaises(GcsimArtifactSetCatalogError):
            GcsimArtifactSetCatalog(
                source_root="fixture",
                source_fingerprint="f" * 64,
                sets=(first, second),
            )

        catalog = GcsimArtifactSetCatalog(
            source_root="fixture",
            source_fingerprint="f" * 64,
            sets=(first,),
        )
        with self.assertRaises(TypeError):
            catalog._by_key["other"] = first  # type: ignore[index]

    def test_parameterized_set_is_modeled_but_not_phase_one_optimizer_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_set(
                root,
                package="husk",
                key="husk",
                source="""
package husk
func init() { core.RegisterSetFunc(keys.Husk, NewSet) }
func NewSet(count int, param map[string]float64) {
    if count >= 2 {}
    if count >= 4 { stacks := param["stacks"]; _ = stacks }
}
""",
            )
            _write_issues(root, {})
            _write_four_star_sets(root, set())

            catalog = load_gcsim_artifact_set_catalog(root)
            capability = catalog.get("husk")

            self.assertTrue(capability.complete_four_piece_modeled)
            self.assertEqual(capability.parameter_keys, ("stacks",))
            self.assertFalse(capability.optimizer_four_piece_ready)
            self.assertEqual(catalog.modeled_four_piece_keys, ("husk",))
            self.assertEqual(catalog.optimizer_ready_four_piece_keys, ())


def _write_set(root: Path, *, package: str, key: str, source: str) -> None:
    package_dir = root / "internal" / "artifacts" / package
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "config.yml").write_text(f"key: {key}\n", encoding="utf-8")
    (package_dir / f"{package}.go").write_text(source, encoding="utf-8")


def _capability(key: str) -> GcsimArtifactSetCapability:
    return GcsimArtifactSetCapability(
        key=key,
        package_name="fixture",
        key_constant="Fixture",
        max_rarity=5,
        registered=True,
        has_two_piece_code=True,
        has_four_piece_code=True,
        two_piece_modeled=True,
        four_piece_modeled=True,
    )


def _write_issues(root: Path, payload: dict[str, list[str]]) -> None:
    path = (
        root
        / "ui"
        / "packages"
        / "docs"
        / "src"
        / "components"
        / "Issues"
        / "artifact_data.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_four_star_sets(root: Path, constants: set[str]) -> None:
    path = root / "pkg" / "optimization" / "substats.go"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"        keys.{constant}," for constant in sorted(constants))
    path.write_text(
        "func load() {\n"
        "    s.artifactSets4Star = []keys.Set{\n"
        f"{body}\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
