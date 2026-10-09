from __future__ import annotations

from io import BytesIO
import unittest
from unittest.mock import patch

from run_workspace.pvp import abyss_client


def _row(
    system_id: str, root: str | None, updated_at: str, *,
    archived: bool = False, mode: str = "shiyu", title: str = "Abyss Cup",
) -> dict:
    return {
        "_id": system_id,
        "root": root,
        "updatedAt": updated_at,
        "archived": archived,
        "main": {"title": title, "mode": mode},
    }


class AbyssClientTests(unittest.TestCase):
    def test_paginated_list_selects_newest_non_archived_per_family(self) -> None:
        root_a = "a" * 24
        root_b = "b" * 24
        pages = [
            {"count": 4, "items": [
                _row("1" * 24, root_a, "2026-09-01T00:00:00Z", title="A old"),
                _row("2" * 24, root_b, "2026-10-02T00:00:00Z", title="B"),
            ]},
            {"count": 4, "items": [
                _row("3" * 24, root_a, "2026-10-03T00:00:00Z", title="A new"),
                _row("4" * 24, root_b, "2026-10-04T00:00:00Z", archived=True),
            ]},
        ]
        with patch.object(abyss_client, "_get_public_json", side_effect=pages) as get:
            choices = abyss_client.list_latest_rulesets()

        self.assertEqual([(x.system_id, x.family_id, x.title) for x in choices], [
            ("3" * 24, root_a, "A new"), ("2" * 24, root_b, "B"),
        ])
        self.assertEqual(get.call_args_list[0].args[0],
                         "/draft_systems?withDetails=true&skip=0&limit=50")
        self.assertEqual(get.call_args_list[1].args[0],
                         "/draft_systems?withDetails=true&skip=2&limit=50")

    def test_rootless_family_and_shiyu_mode_are_included(self) -> None:
        page = {"count": 2, "items": [
            _row("5" * 24, None, "2026-01-01T00:00:00Z", mode="shiyu"),
            _row("6" * 24, "a" * 24, "2026-01-02T00:00:00Z", mode="other"),
        ]}
        with patch.object(abyss_client, "_get_public_json", return_value=page):
            choices = abyss_client.list_latest_rulesets()
        self.assertEqual({x.family_id for x in choices}, {"5" * 24, "a" * 24})

    def test_catalog_requires_details_and_finite_pagination(self) -> None:
        bad_pages = [
            {"count": abyss_client.MAX_SYSTEMS + 1, "items": []},
            {"count": 1, "items": []},
            {"count": 1, "items": [_row("1" * 24, None, "2026-01-01T00:00:00Z")
                                   | {"archived": None}]},
        ]
        for page in bad_pages:
            with self.subTest(page=page), patch.object(
                abyss_client, "_get_public_json", return_value=page,
            ), self.assertRaises(abyss_client.AbyssSchemaError):
                abyss_client.list_latest_rulesets()

    def test_fetch_rejects_invalid_or_mismatched_version_before_catalogs(self) -> None:
        with patch.object(abyss_client, "_get_public_json") as get:
            with self.assertRaises(abyss_client.AbyssVersionError):
                abyss_client.fetch_ruleset_source("../agents")
            get.assert_not_called()
        with patch.object(abyss_client, "_get_public_json", return_value={"_id": "b" * 24}) as get:
            with self.assertRaises(abyss_client.AbyssVersionError):
                abyss_client.fetch_ruleset_source("a" * 24)
            self.assertEqual(get.call_count, 1)

    def test_fetch_returns_exact_source_and_catalogs(self) -> None:
        system_id = "a" * 24
        system = {"_id": system_id, "costs": {"agents": []}}
        agents = [{"_id": "b" * 24}]
        engines = [{"_id": "c" * 24}]
        with patch.object(abyss_client, "_get_public_json", side_effect=[system, agents, engines]) as get:
            self.assertEqual(abyss_client.fetch_ruleset_source(system_id), (system, agents, engines))
        self.assertEqual([call.args[0] for call in get.call_args_list], [
            f"/draft_systems/{system_id}", "/agents", "/engines",
        ])

    def test_public_get_uses_bounded_unauthenticated_request(self) -> None:
        with patch.object(abyss_client, "urlopen", return_value=BytesIO(b"{}")) as open_url:
            self.assertEqual(abyss_client._get_public_json("/agents"), {})
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "https://abyss.darte.gg/api/abyss/agents")
        self.assertEqual(dict(request.header_items())["User-agent"], "Mozilla/5.0")
        self.assertEqual(open_url.call_args.kwargs["timeout"], 15)
        with patch.object(
            abyss_client, "urlopen",
            return_value=BytesIO(b" " * (abyss_client.MAX_RESPONSE_BYTES + 1)),
        ), self.assertRaises(abyss_client.AbyssSchemaError):
            abyss_client._get_public_json("/agents")


if __name__ == "__main__":
    unittest.main()
