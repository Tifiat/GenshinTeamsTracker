"""Two complete source publications, switching and deletion in temporary roots."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from hoyolab_export.import_store import prepare_import_store, stage_import_attempt, commit_import_snapshot
from run_workspace.account_profiles import (
    active_profile, activate_profile, create_profile, profile_root, update_profile_metadata,
)
from run_workspace.profile_control import apply_profile_operation
from tests.hoyolab_export.account.test_account_storage import (
    fake_account_character, fake_account_weapon, fake_account_details,
)


class MultiaccountIsolationTest(unittest.TestCase):
    def _import(self, project: Path, profile: dict, uid: str, name: str) -> Path:
        root = profile_root(profile["id"], project_root=project)
        db = root / "data/artifacts.db"
        prepare_import_store(db)
        character = fake_account_character(name=name)
        details = fake_account_details(character_name=name)
        details["json"]["retcode"] = 0
        details["json"]["data"]["list"][0]["relics"] = []
        attempt = stage_import_attempt(
            db, account_uid=uid, server="os_euro", account_characters=[character],
            account_weapons=[fake_account_weapon(character_name=name)], account_character_details=details,
        )
        commit_import_snapshot(db, attempt_id=attempt, account_sync_context={
            "character_stats_catalog": None, "weapon_stats_catalog": None,
            "character_region_entries": [], "character_trait_entries": [], "gcsim_key_resolver": None,
        }, side_icon_cache_dir=root / "assets/hoyolab/side")
        update_profile_metadata(profile["id"], {"uid": uid, "server": "os_euro", "nickname": name},
                                imported=True, project_root=project)
        return db

    def test_import_update_switch_delete_and_reset_remain_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            settings = project / "settings.json"
            settings.write_text(json.dumps({"hoyolab_change_equipment_on_import": False,
                                            "hoyolab_login_hint_dismissed": True,
                                            "future_dismissed_flag": True}))
            first = create_profile(project_root=project)
            first_db = self._import(project, first, "100001", "First")
            first_root = first_db.parent.parent
            for relative in ("data/history/snapshots/fixture.json", "data/pvp/decks/fixture.json",
                             "hoyolab_export/profile/fixture-session", "assets/hoyolab/account/avatar.png"):
                target = first_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"isolated fixture")
            second = create_profile(project_root=project)
            second_db = self._import(project, second, "100002", "Second")
            activate_profile(first["id"], project_root=project)
            self.assertEqual(active_profile(project_root=project)["metadata"]["nickname"], "First")
            self._import(project, first, "100001", "First updated")
            with closing(sqlite3.connect(second_db)) as connection:
                self.assertEqual(connection.execute("SELECT account_uid FROM hoyolab_account_binding").fetchone()[0], "100002")
                self.assertEqual(connection.execute("SELECT name FROM account_characters").fetchone()[0], "Second")
            apply_profile_operation("delete", first["id"], project_root=project)
            self.assertFalse(first_root.exists())
            self.assertTrue(second_db.exists())
            self.assertEqual(active_profile(project_root=project)["id"], second["id"])
            self.assertTrue(json.loads(settings.read_text())["hoyolab_login_hint_dismissed"])
            apply_profile_operation("reset", project_root=project)
            self.assertIsNone(active_profile(project_root=project))
            self.assertFalse(second_db.exists())
            self.assertEqual(json.loads(settings.read_text()), {})


if __name__ == "__main__":
    unittest.main()
