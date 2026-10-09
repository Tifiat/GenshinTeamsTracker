from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from run_workspace.gcsim.rotation_database import (
    MAX_RESPONSE_BYTES,
    DatabaseMember,
    RotationRecord,
    _fetch_json,
    rank_records,
    search_team,
)


KEYS = ("chiori", "layla", "ningguang", "rosaria")


def entry(record_id: str, *, keys=KEYS, cons=None, weapons=None, config="active layla;\nlayla skill;"):
    cons = cons or (0, 6, 6, 6)
    weapons = weapons or ("harbingerofdawn", "favsword", "widsith", "favlance")
    team = [
        {"name": key, "cons": c, "weapon": {"name": weapon, "refine": 5}, "sets": {"gt": 4}}
        for key, c, weapon in zip(keys, cons, weapons)
    ]
    return {
        "_id": record_id,
        "config": config,
        "description": f"Description {record_id}",
        "submitter": "author",
        "summary": {"char_names": list(keys), "team": team, "mean_dps_per_target": 12345},
    }


def member(key: str, constellation: int = 0, weapon: str = "weapon") -> DatabaseMember:
    return DatabaseMember(key, constellation, weapon)


class RotationDatabaseTests(unittest.TestCase):
    def test_search_paginates_filters_exact_team_and_dedupes(self):
        calls = []
        pages = [
            [entry("first"), entry("wrong", keys=("chiori", "layla", "ningguang", "furina"))],
            [entry("first"), entry("later", config="rotation from later page;")],
            [],
        ]

        def fetch(url, timeout):
            self.assertEqual(timeout, 3)
            parsed = urlsplit(url)
            self.assertEqual(parsed.scheme, "https")
            self.assertEqual(parsed.netloc, "db.kqm.gg")
            q = json.loads(parse_qs(parsed.query)["q"][0])
            self.assertEqual(q["query"], {"$and": [{"summary.char_names": key} for key in KEYS]})
            self.assertEqual(q["limit"], 2)
            calls.append(q["skip"])
            return {"data": pages[len(calls) - 1]}

        result = search_team(KEYS, page_size=2, timeout=3, fetch_json=fetch)
        self.assertTrue(result.complete)
        self.assertEqual(result.status, "ok")
        self.assertEqual(calls, [0, 2, 4])
        self.assertEqual([record.id for record in result.records], ["first", "later"])
        self.assertEqual(result.records[1].config, "rotation from later page;")
        self.assertEqual(result.records[0].members[0].refinement, 5)
        self.assertEqual(result.records[0].members[0].sets, {"gt": 4})
        self.assertEqual(result.records[0].url, "https://db.kqm.gg/db/first")

    def test_empty_network_error_cap_and_malformed_are_distinct(self):
        empty = search_team(KEYS, fetch_json=lambda *_: {"data": []})
        self.assertTrue(empty.complete)
        self.assertEqual(empty.status, "empty")
        self.assertIsNone(empty.error)

        failed = search_team(KEYS, fetch_json=lambda *_: (_ for _ in ()).throw(URLError("offline")))
        self.assertFalse(failed.complete)
        self.assertEqual(failed.status, "error")
        self.assertIn("URLError", failed.error)

        capped = search_team(KEYS, page_size=1, max_pages=1, fetch_json=lambda *_: {"data": [entry("one")]})
        self.assertFalse(capped.complete)
        self.assertEqual(capped.status, "incomplete")
        self.assertEqual([record.id for record in capped.records], ["one"])

        bad = entry("broken")
        bad.pop("config")
        malformed = search_team(KEYS, fetch_json=lambda *_: {"data": [bad]})
        self.assertFalse(malformed.complete)
        self.assertEqual(malformed.status, "incomplete")

    def test_rank_prioritizes_constellation_then_weapon_and_ignores_refinement(self):
        desired = (
            member("chiori", 0, "harbingerofdawn"), member("layla", 6, "favsword"),
            member("ningguang", 6, "widsith"), member("rosaria", 6, "favlance"),
        )

        def record(record_id, *, cons=(0, 6, 6, 6), weapons=None, missing_c=False, reverse=False):
            weapons = weapons or tuple(m.weapon for m in desired)
            members = tuple(
                DatabaseMember(key, None if missing_c and i == 0 else cons[i], weapons[i], 1, {"other": 4})
                for i, key in enumerate(KEYS)
            )
            return RotationRecord(record_id, "config", "", "", "https://db.kqm.gg/db/" + record_id, tuple(reversed(members)) if reverse else members)

        records = [
            record("changed_c_two", cons=(2, 6, 6, 6)),
            record("changed_weapon_two", weapons=("other", "other", "widsith", "favlance")),
            record("unknown_c", missing_c=True),
            record("changed_c_one", cons=(1, 6, 6, 6), weapons=("other", "favsword", "widsith", "favlance")),
            record("changed_weapon_one", weapons=("other", "favsword", "widsith", "favlance")),
            record("exact_z"),
            record("exact_a", reverse=True),
        ]
        self.assertEqual(
            [item.id for item in rank_records(records, desired)],
            ["exact_a", "exact_z", "changed_weapon_one", "changed_weapon_two", "changed_c_one", "changed_c_two", "unknown_c"],
        )

    def test_missing_source_fields_never_rank_as_c0_or_exact_weapon(self):
        desired = tuple(member(key) for key in KEYS)
        exact = RotationRecord("exact", "cfg", "", "", "", desired)
        missing_weapon = RotationRecord("no_weapon", "cfg", "", "", "", (DatabaseMember(KEYS[0], 0),) + desired[1:])
        missing_c = RotationRecord("no_c", "cfg", "", "", "", (DatabaseMember(KEYS[0], None, "weapon"),) + desired[1:])
        self.assertEqual([r.id for r in rank_records((missing_c, missing_weapon, exact), desired)], ["exact", "no_weapon", "no_c"])

    def test_missing_summary_c0_uses_only_explicit_unambiguous_config_declaration(self):
        zero = entry("zero", config="furina char lvl=90/90 cons=0 talent=9,9,9;\nactive furina;")
        zero["summary"]["team"][0]["name"] = "furina"
        zero["summary"]["char_names"][0] = "furina"
        zero["summary"]["team"][0].pop("cons")
        zero["summary"]["team"][0]["weapon"].pop("refine")
        wanted = ("furina",) + KEYS[1:]

        def parsed(config):
            raw = entry("candidate", keys=wanted, config=config)
            raw["summary"]["team"][0].pop("cons")
            return search_team(wanted, fetch_json=lambda *_: {"data": [raw]}).records[0].members[0].constellation

        result = search_team(wanted, fetch_json=lambda *_: {"data": [zero]})
        self.assertEqual(result.records[0].members[0].constellation, 0)
        self.assertIsNone(result.records[0].members[0].refinement)
        self.assertIsNone(parsed("active furina;\nfurina skill;"))
        self.assertIsNone(parsed("# furina char cons=0;\nactive furina;"))
        self.assertIsNone(parsed("/*\nfurina char cons=0;\n*/\nactive furina;"))
        self.assertIsNone(parsed("furina char cons=0;\nfurina char cons=6;\nactive furina;"))
        self.assertIsNone(parsed('furina char note="cons=0";\nactive furina;'))
        self.assertIsNone(parsed('let note = "furina char cons=0;";\nactive furina;'))
        self.assertIsNone(parsed('furina char lvl=90/90 +params=[cons=0];\nactive furina;'))
        self.assertEqual(parsed("furina char lvl=90/90\n cons=0 talent=9,9,9;\nactive furina;"), 0)

    def test_recursion_error_is_reported_as_network_parse_failure(self):
        result = search_team(KEYS, fetch_json=lambda *_: (_ for _ in ()).throw(RecursionError()))
        self.assertEqual(result.status, "error")
        self.assertFalse(result.complete)

    def test_fetch_bounds_response_and_disables_cache(self):
        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.close()

        requests = []

        def open_response(request, timeout):
            requests.append((request, timeout))
            return Response(b"x" * (MAX_RESPONSE_BYTES + 1))

        with patch("run_workspace.gcsim.rotation_database.urlopen", open_response):
            with self.assertRaisesRegex(ValueError, "size limit"):
                _fetch_json("https://db.kqm.gg/api/db?q=x", 2)
        self.assertEqual(requests[0][1], 2)
        self.assertEqual(requests[0][0].get_header("Cache-control"), "no-store")


if __name__ == "__main__":
    unittest.main()
