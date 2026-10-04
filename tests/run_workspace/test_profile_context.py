from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


_PROFILE_INSPECTION_SCRIPT = r"""
import json
import os
from pathlib import Path

import run_workspace.account_profiles as profiles

# profile_context normally resolves a managed root from the profile registry.
# Keep this test hermetic: point that resolver at a temporary root and do not
# call bootstrap_profile(), which owns real profile selection and migration.
profiles.profile_root = lambda profile_id, **kwargs: Path(os.environ["TEST_ACCOUNT_ROOT"])

import run_workspace.profile_context as profile_context
from hoyolab_export import paths as hoyolab_paths
from hoyolab_export.artifact_db import ARTIFACT_DB_PATH
from run_workspace.history_artwork import ARTWORK_ROOT
from run_workspace.pvp.account_deck_export import DEFAULT_OUTPUT_DIR as DECK_EXPORT_DIR
from run_workspace.pvp.deck_preset import DEFAULT_PVP_DECK_PRESET_DIR
from run_workspace.pvp.session_bundle import DEFAULT_SESSION_BUNDLE_OUTPUT_DIR
from run_workspace.gcsim.artifact_runner import DEFAULT_GCSIM_RUNS_DIR
from run_workspace.gcsim.cleanup import (
    DEFAULT_GCSIM_FARMING_RUNS_DIR,
    DEFAULT_GCSIM_OPTIMIZER_RUNS_DIR as CLEANUP_OPTIMIZER_RUNS_DIR,
)
from run_workspace.gcsim.optimizer_cache import DEFAULT_GCSIM_OPTIMIZER_CACHE_DIR
from run_workspace.gcsim.optimizer_run_retention import DEFAULT_GO_RUN_ROOT
from run_workspace.gcsim.optimizer_runner import (
    DEFAULT_GCSIM_OPTIMIZER_RUNS_DIR as OPTIMIZER_RUNS_DIR,
)
from run_workspace.gcsim.engine_store import DEFAULT_GCSIM_ENGINE_STORE_DIR

paths = {
    "hoyolab_data": hoyolab_paths.HOYOLAB_DATA_DIR,
    "artifact_db": ARTIFACT_DB_PATH,
    "history": ARTWORK_ROOT,
    "deck_export": DECK_EXPORT_DIR,
    "deck_presets": DEFAULT_PVP_DECK_PRESET_DIR,
    "session_bundles": DEFAULT_SESSION_BUNDLE_OUTPUT_DIR,
    "gcsim_runs": DEFAULT_GCSIM_RUNS_DIR,
    "gcsim_farming_runs": DEFAULT_GCSIM_FARMING_RUNS_DIR,
    "gcsim_optimizer_runs_cleanup": CLEANUP_OPTIMIZER_RUNS_DIR,
    "gcsim_optimizer_runs": OPTIMIZER_RUNS_DIR,
    "gcsim_optimizer_cache": DEFAULT_GCSIM_OPTIMIZER_CACHE_DIR,
    "gcsim_optimizer_go_runs": DEFAULT_GO_RUN_ROOT,
    "shared_engine_store": DEFAULT_GCSIM_ENGINE_STORE_DIR,
}

result = {
    "profile_id": profile_context.PROFILE_ID,
    "account_root": str(profile_context.ACCOUNT_ROOT),
    "project_root": str(profile_context.PROJECT_ROOT),
    "paths": {name: str(path) for name, path in paths.items()},
    "asset_hoyolab": str(profile_context.account_asset_path("assets/hoyolab/characters/example.png")),
    "asset_legacy_profile": str(profile_context.account_asset_path(
        "data/profiles/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/assets/hoyolab/characters/example.png"
    )),
    "asset_static_catalog": str(profile_context.account_asset_path("assets/artifact_sets/example.png")),
    "asset_absolute": str(profile_context.account_asset_path(
        Path(os.environ["TEST_ACCOUNT_ROOT"]) / "external.png"
    )),
}
print(json.dumps(result))
"""


class ProfileContextIsolationTests(unittest.TestCase):
    def _inspect_profile(self, profile_id: str, account_root: Path) -> dict[str, object]:
        env = os.environ.copy()
        env["GTT_ACCOUNT_PROFILE"] = profile_id
        env["TEST_ACCOUNT_ROOT"] = str(account_root)
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(PROJECT_ROOT), existing_pythonpath) if part
        )
        completed = subprocess.run(
            [sys.executable, "-c", _PROFILE_INSPECTION_SCRIPT],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            check=True,
            text=True,
            timeout=30,
        )
        return json.loads(completed.stdout)

    def test_account_paths_are_isolated_and_shared_engines_stay_project_wide(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gtt-profile-context-") as temp_dir:
            temp_root = Path(temp_dir)
            first_root = temp_root / "profile-one"
            second_root = temp_root / "profile-two"
            first = self._inspect_profile("1" * 32, first_root)
            second = self._inspect_profile("2" * 32, second_root)

        account_path_names = (
            "hoyolab_data",
            "artifact_db",
            "history",
            "deck_export",
            "deck_presets",
            "session_bundles",
            "gcsim_runs",
            "gcsim_farming_runs",
            "gcsim_optimizer_runs_cleanup",
            "gcsim_optimizer_runs",
            "gcsim_optimizer_cache",
            "gcsim_optimizer_go_runs",
        )

        for inspected, profile_id, account_root in (
            (first, "1" * 32, first_root),
            (second, "2" * 32, second_root),
        ):
            self.assertEqual(inspected["profile_id"], profile_id)
            self.assertEqual(Path(inspected["account_root"]), account_root)
            for name in account_path_names:
                with self.subTest(profile=profile_id, path=name):
                    self.assertTrue(
                        Path(inspected["paths"][name]).is_relative_to(account_root),
                        inspected["paths"][name],
                    )
            self.assertEqual(
                Path(inspected["asset_hoyolab"]),
                account_root / "assets" / "hoyolab" / "characters" / "example.png",
            )
            self.assertEqual(
                Path(inspected["asset_legacy_profile"]),
                account_root / "assets" / "hoyolab" / "characters" / "example.png",
            )
            self.assertEqual(
                Path(inspected["asset_static_catalog"]),
                Path(inspected["project_root"]) / "assets" / "artifact_sets" / "example.png",
            )
            self.assertEqual(
                Path(inspected["asset_absolute"]),
                account_root / "external.png",
            )

        self.assertNotEqual(first["paths"]["artifact_db"], second["paths"]["artifact_db"])
        self.assertNotEqual(first["paths"]["history"], second["paths"]["history"])
        self.assertNotEqual(first["paths"]["gcsim_runs"], second["paths"]["gcsim_runs"])
        self.assertEqual(first["paths"]["shared_engine_store"], second["paths"]["shared_engine_store"])
        self.assertEqual(
            Path(first["paths"]["shared_engine_store"]),
            Path(first["project_root"]) / "data" / "gcsim" / "engines",
        )
        self.assertFalse(
            Path(first["paths"]["shared_engine_store"]).is_relative_to(Path(first["account_root"]))
        )


if __name__ == "__main__":
    unittest.main()
