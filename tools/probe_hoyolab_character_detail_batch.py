import argparse
import asyncio
import gc
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hoyolab_export.auth import AuthStatus, get_auth_status
from hoyolab_export.hoyolab_exporter import HOYOLAB_URL, HoyolabExporter, close_export_context
from hoyolab_export.paths import HOYOLAB_DATA_DIR, HOYOLAB_DEBUG_DIR, HOYOLAB_PROFILE_DIR


DETAIL_URL = "https://sg-public-api.hoyolab.com/event/game_record/genshin/api/character/detail"
ROLES_URL = "https://api-account-os.hoyolab.com/binding/api/getUserGameRolesByCookie?game_biz=hk4e_global"

IGNORED_CHARACTER_IDS = {
    10000118,
    10000117,
}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_character_ids(limit: int) -> list[int]:
    path = HOYOLAB_DATA_DIR / "account_characters.json"
    if not path.exists():
        raise FileNotFoundError(f"Run HoYoLAB import first, missing: {path}")

    characters = read_json(path)

    ids = []
    for character in characters:
        character_id = character.get("id")
        if not isinstance(character_id, int):
            continue
        if character_id in IGNORED_CHARACTER_IDS:
            continue

        ids.append(character_id)

    if limit > 0:
        ids = ids[:limit]

    return ids


def pick_genshin_role(payload: dict[str, Any]) -> tuple[str, str]:
    data = payload.get("data") or {}
    roles = data.get("list") or []

    for role in roles:
        if role.get("game_biz") == "hk4e_global":
            role_id = role.get("game_uid") or role.get("game_role_id") or role.get("role_id")
            server = role.get("region") or role.get("server")
            if role_id and server:
                return str(role_id), str(server)

    raise RuntimeError("Could not detect Genshin role_id/server from HoYoLAB roles response.")


async def browser_fetch_json(page, url: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
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


async def main_async(limit: int) -> None:
    if get_auth_status(HOYOLAB_PROFILE_DIR) != AuthStatus.LOGGED_IN:
        raise SystemExit("HoYoLAB profile is not logged in. Run login setup first.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = HOYOLAB_DEBUG_DIR / "character_detail_batch_probe" / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    character_ids = load_character_ids(limit)

    exporter = HoyolabExporter(
        profile_dir=HOYOLAB_PROFILE_DIR,
        download_dir=out_dir,
        scale=4,
        fixed_container_width=500,
        browser_window_width=1280,
        browser_window_height=900,
        image_format="png",
    )

    context = await exporter._create_context()
    page = context.pages[0] if context.pages else await context.new_page()

    try:
        print("[batch-probe] Opening HoYoLAB...")
        await page.goto(HOYOLAB_URL, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(2500)

        print("[batch-probe] Fetching role info...")
        roles_result = await browser_fetch_json(page, ROLES_URL)
        write_json(out_dir / "roles_result.json", roles_result)

        role_id, server = pick_genshin_role(roles_result.get("json") or {})

        body = {
            "server": server,
            "role_id": role_id,
            "character_ids": character_ids,
        }

        print("[batch-probe] Request:")
        print("  server:", server)
        print("  role_id:", role_id)
        print("  character_ids:", character_ids)

        result = await browser_fetch_json(
            page,
            DETAIL_URL,
            method="POST",
            body=body,
        )

        write_json(out_dir / "character_detail_batch_result.json", result)

        payload = result.get("json") or {}
        data = payload.get("data") or {}
        items = data.get("list") or []

        print()
        print("[batch-probe] Result:")
        print("  http ok:", result.get("ok"))
        print("  http status:", result.get("status"))
        print("  retcode:", payload.get("retcode"))
        print("  message:", payload.get("message"))
        print("  requested:", len(character_ids))
        print("  returned:", len(items) if isinstance(items, list) else "not-list")

        if isinstance(items, list):
            for item in items[:10]:
                base = item.get("base") or {}
                relics = item.get("relics") or []
                with_stats = [
                    relic for relic in relics
                    if relic.get("main_property") or relic.get("sub_property_list")
                ]
                print(
                    " ",
                    base.get("id"),
                    base.get("name"),
                    "relics:",
                    len(relics),
                    "with_stats:",
                    len(with_stats),
                )

        print()
        print("[batch-probe] Output:", out_dir)

    finally:
        await close_export_context(context)


def run_async(coro):
    loop = asyncio.new_event_loop()

    try:
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(coro)
        loop.run_until_complete(asyncio.sleep(0.5))
        gc.collect()
        return result
    finally:
        pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
        for task in pending:
            task.cancel()

        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.run_until_complete(asyncio.sleep(0))
        gc.collect()
        asyncio.set_event_loop(None)
        loop.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="How many character ids to request. Use 0 for all.",
    )
    args = parser.parse_args()

    run_async(main_async(limit=args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())