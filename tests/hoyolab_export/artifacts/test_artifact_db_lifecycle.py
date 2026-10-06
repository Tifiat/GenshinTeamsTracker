from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hoyolab_export.artifact_db import init_artifact_db


class ArtifactDatabaseLifecycleTest(unittest.TestCase):
    def test_initializer_releases_its_database_handle(self) -> None:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "artifacts.db"
            self.assertEqual(init_artifact_db(database), database)
            database.unlink()
            self.assertFalse(database.exists())


if __name__ == "__main__":
    unittest.main()
