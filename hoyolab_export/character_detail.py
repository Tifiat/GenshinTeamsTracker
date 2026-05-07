from __future__ import annotations

import time
from typing import Any


DETAIL_URL = "https://sg-public-api.hoyolab.com/event/game_record/genshin/api/character/detail"
ROLES_URL = "https://api-account-os.hoyolab.com/binding/api/getUserGameRolesByCookie?game_biz=hk4e_global"
IGNORED_CHARACTER_IDS = {
    10000118,
    10000117,
}


def real_character_ids(characters: list[dict[str, Any]] | list[int]) -> list[int]:
    ids: list[int] = []

    for character in characters:
        if isinstance(character, int):
            character_id = character
        elif isinstance(character, dict):
            character_id = character.get("id")
        else:
            continue

        if not isinstance(character_id, int):
            continue
        if character_id in IGNORED_CHARACTER_IDS:
            continue
        ids.append(character_id)

    return ids


def pick_genshin_role(payload: dict[str, Any]) -> tuple[str, str]:
    data = payload.get("data") or {}
    roles = data.get("list") or []

    for role in roles:
        if not isinstance(role, dict):
            continue
        if role.get("game_biz") != "hk4e_global":
            continue

        role_id = role.get("game_uid") or role.get("game_role_id") or role.get("role_id")
        server = role.get("region") or role.get("server")
        if role_id and server:
            return str(role_id), str(server)

    raise RuntimeError("Could not detect Genshin role_id/server from HoYoLAB roles response.")


async def browser_fetch_json(
    page,
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return await page.evaluate(
        """
        async ({ url, method, body }) => {
            function readCookie(name) {
                const prefix = name + "=";
                const parts = document.cookie.split(";");

                for (const part of parts) {
                    const trimmed = part.trim();
                    if (trimmed.startsWith(prefix)) {
                        return decodeURIComponent(trimmed.slice(prefix.length));
                    }
                }

                return "";
            }

            function normalizeLanguage(value) {
                if (!value) {
                    return "";
                }

                return String(value)
                    .trim()
                    .replace("_", "-")
                    .toLowerCase();
            }

            function acceptLanguageHeader(lang) {
                if (!lang) {
                    return "en-US,en;q=0.9";
                }

                const parts = lang.split("-");
                const primary = parts[0] || "en";
                const region = parts[1] || primary;
                const browserLang = primary + "-" + region.toUpperCase();

                return `${browserLang},${primary};q=0.9,en;q=0.8`;
            }

            const detectedLanguage =
                normalizeLanguage(readCookie("mi18nLang")) ||
                normalizeLanguage(localStorage.getItem("mi18nLang")) ||
                normalizeLanguage(document.documentElement.lang) ||
                normalizeLanguage(navigator.language) ||
                "en-us";

            const options = {
                method,
                credentials: "include",
                headers: {
                    "content-type": "application/json",
                    "accept": "application/json, text/plain, */*",
                    "x-rpc-language": detectedLanguage,
                    "accept-language": acceptLanguageHeader(detectedLanguage)
                }
            };

            if (body !== null) {
                options.body = JSON.stringify(body);
            }

            const response = await fetch(url, options);
            const text = await response.text();

            let json = null;
            try {
                json = JSON.parse(text);
            } catch (e) {}

            return {
                ok: response.ok,
                status: response.status,
                statusText: response.statusText,
                url: response.url,
                detectedLanguage,
                json,
                textPreview: json === null ? text.slice(0, 1000) : null
            };
        }
        """,
        {
            "url": url,
            "method": method,
            "body": body,
        },
    )


async def fetch_character_details_batch(
    page,
    character_ids: list[int] | list[dict[str, Any]],
) -> dict[str, Any]:
    ids = real_character_ids(character_ids)
    if not ids:
        raise RuntimeError("No real character ids found for HoYoLAB character/detail request.")

    roles_result = await browser_fetch_json(page, ROLES_URL)
    role_id, server = pick_genshin_role(roles_result.get("json") or {})

    result = await browser_fetch_json(
        page,
        DETAIL_URL,
        method="POST",
        body={
            "server": server,
            "role_id": role_id,
            "character_ids": ids,
        },
    )

    payload = result.get("json") or {}
    data = payload.get("data") or {}
    items = data.get("list") or []

    result["source"] = "character/detail"
    result["capturedAt"] = int(time.time() * 1000)
    result["charactersRequested"] = len(ids)
    result["charactersReturned"] = len(items) if isinstance(items, list) else None
    return result
