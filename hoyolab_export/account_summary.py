"""Fetch a small, account-bound Genshin profile summary from HoYoLAB.

The Chronicle ``index`` endpoint is used by the maintained ``genshin.py``
client for partial/full Genshin user data. Its ``role`` maps ``nickname``,
``region``, ``level`` and ``game_head_icon``; that client explicitly models
``AvatarUrl`` separately from ``in_game_avatar`` (``game_head_icon``). This
module only uses the latter for ``avatar_url``.

Schema references (reviewed 2026-10-04):
* https://github.com/seriaati/genshin.py/blob/master/genshin/client/components/chronicle/genshin.py#L57-L70
* https://github.com/seriaati/genshin.py/blob/master/genshin/models/hoyolab/record.py#L54-L62
* https://github.com/seriaati/genshin.py/blob/master/genshin/client/routes.py#L134-L147

The maintained HoYoLAB model does not expose World Level. Enka's separate
public-UID API documents ``playerInfo.worldLevel`` and
``playerInfo.profilePicture.avatarId``; this helper deliberately makes no
Enka request and returns ``world_level=None`` until that source is separately
approved and integrated:
https://github.com/EnkaNetwork/API-docs/blob/master/docs/gi/api.md
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from urllib.parse import urlencode, urlsplit


GENSHIN_INDEX_URL = "https://sg-public-api.hoyolab.com/event/game_record/genshin/api/index"

JsonFetcher = Callable[..., Awaitable[dict[str, Any]]]


class AccountSummaryError(RuntimeError):
    """A safe, non-sensitive error while fetching bound game profile metadata."""


async def fetch_account_summary(
    page: Any,
    account_context: Mapping[str, Any],
    json_fetcher: JsonFetcher,
) -> dict[str, Any]:
    """Fetch allowlisted in-game summary fields for one verified UID/server.

    The UID and server come from the import's already-selected HoYoLAB role;
    the request never chooses a role itself. Missing optional response fields
    remain ``None``. A response explicitly naming a different server is
    rejected so summary data cannot cross an account boundary.
    """
    uid = _text(account_context.get("role_id"))
    server = _text(account_context.get("server"))
    if not uid or not server:
        raise AccountSummaryError("A verified HoYoLAB UID and server are required")

    url = f"{GENSHIN_INDEX_URL}?{urlencode({'role_id': uid, 'server': server})}"
    try:
        response = await json_fetcher(page, url)
    except Exception as exc:
        raise AccountSummaryError("HoYoLAB Genshin profile summary request failed") from exc

    payload = response.get("json") if isinstance(response, Mapping) else None
    if (not isinstance(response, Mapping) or not response.get("ok")
            or not isinstance(payload, Mapping) or payload.get("retcode") != 0):
        raise AccountSummaryError("HoYoLAB Genshin profile summary was unavailable")

    data = payload.get("data")
    role = data.get("role") if isinstance(data, Mapping) else None
    if not isinstance(role, Mapping):
        raise AccountSummaryError("HoYoLAB Genshin profile summary had no role data")

    response_server = _text(role.get("region"))
    if response_server and response_server != server:
        raise AccountSummaryError("HoYoLAB returned profile data for a different server")

    return {
        "uid": uid,
        "server": server,
        "nickname": _optional_string(role.get("nickname")),
        # Chronicle's typed model does not expose World Level; do not infer it
        # from Adventure Rank or consume undocumented aliases.
        "world_level": None,
        "adventure_rank": _positive_int(role.get("level")),
        # UserInfo.in_game_avatar aliases game_head_icon. AvatarUrl is a
        # separate HoYoLAB avatar field and intentionally is not a fallback.
        "avatar_url": _https_game_icon(role.get("game_head_icon")),
    }


def _text(value: Any) -> str:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return ""
    return str(value).strip()


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        number = int(value.strip())
    else:
        return None
    return number if number >= 0 else None


def _optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _https_game_icon(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    url = value.strip()
    if not url:
        return None
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    trusted_host = any(
        host == domain or host.endswith(f".{domain}")
        for domain in ("hoyolab.com", "hoyoverse.com", "mihoyo.com")
    )
    if parts.scheme != "https" or not trusted_host:
        return None
    return url
