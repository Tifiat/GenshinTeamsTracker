from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from run_workspace.gcsim.artifact_set_catalog import (
    GcsimArtifactSetCapability,
    GcsimArtifactSetCatalog,
)
from run_workspace.gcsim.optimizer_backend import (
    GcsimBoundOptimizerError,
    prepare_bound_gcsim_four_piece_optimizer_candidate,
    resolve_gcsim_optimizer_worker_count,
)
from run_workspace.gcsim.optimizer_config import GcsimFiveStarMainStatLayout
from run_workspace.gcsim.optimizer_engine_context import GcsimOptimizerEngineContext


CONFIG = """furina char lvl=90/90 cons=0 talent=9,9,9;
furina add weapon="wolffang" refine=1 lvl=90/90;
furina add set="goldentroupe" count=4;
furina add stats hp=4780 atk=311 hp%=0.466 hydro%=0.466 cr=0.311;
options iteration=10 workers=20;
target lvl=100 hp=999999999;
active furina;
"""


class GcsimOptimizerBackendTest(unittest.TestCase):
    def test_bound_candidate_owns_artifact_workers_and_cache_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            context = _context(artifact)
            bound = prepare_bound_gcsim_four_piece_optimizer_candidate(
                CONFIG,
                engine_context=context,
                set_assignments={"furina": "goldentroupe"},
                main_stat_layouts={
                    "furina": GcsimFiveStarMainStatLayout(
                        "hp%",
                        "hydro%",
                        "cr",
                    )
                },
            )

            execution = bound.build_execution(
                worker_count=3,
                run_dir=root / "run",
                overall_timeout_seconds=123,
                optimizer_options={"fine_tune": 0},
            )
            request = execution.request
            identity = execution.cache_identity

            self.assertTrue(bound.ready)
            self.assertIn("options iteration=10 workers=3;", request.config_text)
            self.assertEqual(request.environment["GOMAXPROCS"], "3")
            self.assertEqual(request.overall_timeout_seconds, 123)
            self.assertEqual(request.artifact_path, str(artifact))
            self.assertEqual(request.expected_artifact_sha256, context.artifact_sha256)
            self.assertEqual(request.engine_binding_sha256, context.binding_sha256)
            self.assertEqual(identity.engine_sha256, context.artifact_sha256)
            self.assertEqual(identity.optimizer_options, (("fine_tune", "0"),))
            self.assertEqual(
                identity.catalog_fingerprint,
                context.catalog.source_fingerprint,
            )

    def test_untrusted_or_wrong_version_context_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "gtt-gcsim.exe"
            artifact.write_bytes(b"engine")
            context = _context(artifact)

            with self.assertRaisesRegex(GcsimBoundOptimizerError, "not resealed"):
                prepare_bound_gcsim_four_piece_optimizer_candidate(
                    CONFIG,
                    engine_context=_context(artifact, trusted=False),
                    set_assignments={"furina": "goldentroupe"},
                    main_stat_layouts={"furina": _layout()},
                )
            with self.assertRaisesRegex(GcsimBoundOptimizerError, "Unsupported"):
                prepare_bound_gcsim_four_piece_optimizer_candidate(
                    CONFIG,
                    engine_context=_context(
                        artifact,
                        contract="gcsim-v9.0.0",
                    ),
                    set_assignments={"furina": "goldentroupe"},
                    main_stat_layouts={"furina": _layout()},
                )

    def test_worker_count_cannot_oversubscribe_detected_logical_cpus(self) -> None:
        with self.assertRaisesRegex(GcsimBoundOptimizerError, "cannot exceed"):
            resolve_gcsim_optimizer_worker_count(10**6)


def _layout() -> GcsimFiveStarMainStatLayout:
    return GcsimFiveStarMainStatLayout("hp%", "hydro%", "cr")


def _context(
    artifact: Path,
    *,
    trusted: bool = True,
    contract: str = "gcsim-v2.42.2",
) -> GcsimOptimizerEngineContext:
    capability = GcsimArtifactSetCapability(
        key="goldentroupe",
        package_name="goldentroupe",
        key_constant="GoldenTroupe",
        max_rarity=5,
        registered=True,
        has_two_piece_code=True,
        has_four_piece_code=True,
        two_piece_modeled=True,
        four_piece_modeled=True,
    )
    catalog = GcsimArtifactSetCatalog(
        source_root="fixture",
        source_fingerprint="c" * 64,
        sets=(capability,),
    )
    artifact_sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return GcsimOptimizerEngineContext(
        engine_id="fixture",
        engine_root=str(artifact.parent),
        engine_version="fixture-version",
        optimizer_contract_version=contract,
        artifact_path=str(artifact),
        artifact_sha256=artifact_sha256,
        engine_tree_sha256="e" * 64,
        catalog=catalog,
        manifest_artifact_sha256=artifact_sha256,
        manifest_engine_tree_sha256="e" * 64,
        binding_sha256="b" * 64,
        trusted=trusted,
        issues=() if trusted else ("drift",),
    )


if __name__ == "__main__":
    unittest.main()
