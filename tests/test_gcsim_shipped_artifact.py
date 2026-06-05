from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from run_workspace.gcsim.shipped_artifact import (
    DEFAULT_SHIPPED_GCSIM_ARTIFACT_RELATIVE_PATH,
    STATUS_CANDIDATE_MISSING,
    STATUS_CANDIDATE_INVALID_PATH,
    STATUS_CANDIDATE_NOT_FILE,
    STATUS_CANDIDATE_READY,
    STATUS_DISABLED,
    resolve_shipped_gcsim_artifact,
)


class GcsimShippedArtifactTest(unittest.TestCase):
    def test_resolver_disabled_reports_candidate_without_requiring_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = resolve_shipped_gcsim_artifact(project_root=root)

            self.assertFalse(result.enabled)
            self.assertFalse(result.ready)
            self.assertEqual(result.status, STATUS_DISABLED)
            self.assertEqual(
                result.candidate_path,
                str((root / DEFAULT_SHIPPED_GCSIM_ARTIFACT_RELATIVE_PATH).resolve()),
            )
            self.assertEqual(result.artifact_path, "")

    def test_resolver_reports_missing_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = resolve_shipped_gcsim_artifact(
                enabled=True,
                candidate_path="missing/gtt-gcsim.exe",
                project_root=root,
            )

            self.assertFalse(result.ready)
            self.assertEqual(result.status, STATUS_CANDIDATE_MISSING)
            self.assertEqual(result.artifact_path, "")

    def test_resolver_reports_ready_candidate_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "shipped" / "gtt-gcsim.exe"
            artifact.parent.mkdir(parents=True)
            artifact.write_bytes(b"fake shipped executable")

            result = resolve_shipped_gcsim_artifact(
                enabled=True,
                candidate_path=artifact,
                project_root=root,
            )

            self.assertTrue(result.ready)
            self.assertEqual(result.status, STATUS_CANDIDATE_READY)
            self.assertEqual(result.artifact_path, str(artifact.resolve()))

    def test_resolver_reports_candidate_not_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "shipped-dir"
            candidate.mkdir()

            result = resolve_shipped_gcsim_artifact(
                enabled=True,
                candidate_path=candidate,
                project_root=root,
            )

            self.assertFalse(result.ready)
            self.assertEqual(result.status, STATUS_CANDIDATE_NOT_FILE)

    def test_resolver_reports_invalid_relative_candidate_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = resolve_shipped_gcsim_artifact(
                enabled=True,
                candidate_path="../outside/gtt-gcsim.exe",
                project_root=root,
            )

            self.assertFalse(result.ready)
            self.assertEqual(result.status, STATUS_CANDIDATE_INVALID_PATH)
            self.assertIn("must not contain", result.error)


if __name__ == "__main__":
    unittest.main()
