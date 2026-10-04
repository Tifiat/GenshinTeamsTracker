from __future__ import annotations

import unittest
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

from hoyolab_export.account_summary import (
    AccountSummaryError,
    GENSHIN_INDEX_URL,
    fetch_account_summary,
)


class FetchAccountSummaryTest(unittest.IsolatedAsyncioTestCase):
    async def test_uses_bound_index_and_in_game_avatar_field(self) -> None:
        in_game_icon = "https://upload-bbs.mihoyo.com/game_record/genshin/player_icon.png"
        community_icon = "https://hoyolab.com/community/avatar.png"
        fetch = AsyncMock(return_value={
            "ok": True,
            "json": {
                "retcode": 0,
                "data": {
                    "role": {
                        "nickname": "In-game name",
                        "region": "os_usa",
                        "level": 57,
                        "AvatarUrl": community_icon,
                        "game_head_icon": in_game_icon,
                    },
                    "stats": {"achievement_number": 100},
                },
            },
        })

        summary = await fetch_account_summary(
            object(), {"role_id": "700000001", "server": "os_usa"}, fetch,
        )

        self.assertEqual(summary, {
            "uid": "700000001",
            "server": "os_usa",
            "nickname": "In-game name",
            "world_level": None,
            "adventure_rank": 57,
            "avatar_url": in_game_icon,
        })
        fetch.assert_awaited_once()
        requested_url = fetch.await_args.args[1]
        self.assertEqual(urlsplit(requested_url).scheme, "https")
        self.assertEqual(urlsplit(requested_url)._replace(query="").geturl(), GENSHIN_INDEX_URL)
        self.assertEqual(parse_qs(urlsplit(requested_url).query), {
            "role_id": ["700000001"], "server": ["os_usa"],
        })

    async def test_missing_optional_fields_stay_empty_and_avatarurl_is_not_used(self) -> None:
        fetch = AsyncMock(return_value={
            "ok": True,
            "json": {
                "retcode": 0,
                "data": {"role": {"region": "os_euro", "AvatarUrl": "https://hoyolab.com/community.png"}},
            },
        })

        summary = await fetch_account_summary(
            object(), {"role_id": 123456789, "server": "os_euro"}, fetch,
        )

        self.assertIsNone(summary["nickname"])
        self.assertIsNone(summary["world_level"])
        self.assertIsNone(summary["adventure_rank"])
        self.assertIsNone(summary["avatar_url"])

    async def test_rejects_missing_binding_before_request(self) -> None:
        fetch = AsyncMock()
        with self.assertRaisesRegex(AccountSummaryError, "verified HoYoLAB UID and server"):
            await fetch_account_summary(object(), {"role_id": "123"}, fetch)
        fetch.assert_not_awaited()

    async def test_rejects_response_for_different_server(self) -> None:
        fetch = AsyncMock(return_value={
            "ok": True,
            "json": {"retcode": 0, "data": {"role": {"region": "os_asia"}}},
        })
        with self.assertRaisesRegex(AccountSummaryError, "different server"):
            await fetch_account_summary(
                object(), {"role_id": "700000001", "server": "os_usa"}, fetch,
            )

    async def test_http_or_api_failure_is_sanitized(self) -> None:
        for response in (
            {"ok": False, "json": {"retcode": 0}},
            {"ok": True, "json": {"retcode": -1, "message": "fixture detail"}},
            {"ok": True, "json": {"retcode": 0, "data": {}}},
        ):
            with self.subTest(response=response):
                with self.assertRaises(AccountSummaryError) as caught:
                    await fetch_account_summary(
                        object(), {"role_id": "700000001", "server": "os_usa"},
                        AsyncMock(return_value=response),
                    )
                self.assertNotIn("fixture detail", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
