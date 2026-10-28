import argparse
import asyncio
import gc
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hoyolab_export.auth import AuthStatus, get_auth_status
from hoyolab_export.hoyolab_exporter import HOYOLAB_URL, HoyolabExporter, close_export_context
from hoyolab_export.paths import HOYOLAB_DEBUG_DIR, HOYOLAB_PROFILE_DIR


CAPTURE_KEYWORDS = (
    "game_record",
    "genshin/api",
    "character",
    "avatar",
    "reliquary",
    "reliquaries",
    "artifact",
    "equip",
)

ARTIFACT_FIELD_HINTS = {
    "reliquaries",
    "reliquary",
    "artifact",
    "artifacts",
    "main_stat",
    "main_property",
    "sub_stats",
    "sub_property",
    "append_props",
    "pos_name",
    "set",
    "affix",
}


def safe_name(url: str, index: int) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "__")
    path = re.sub(r"[^a-zA-Z0-9_.-]+", "_", path)
    if not path:
        path = "response"
    return f"{index:03}_{path[:140]}.json"


def json_preview_keys(payload: Any) -> Any:
    if isinstance(payload, dict):
        return sorted(str(key) for key in payload.keys())[:50]
    if isinstance(payload, list):
        return {
            "type": "list",
            "len": len(payload),
            "first_keys": json_preview_keys(payload[0]) if payload else [],
        }
    return type(payload).__name__


def find_key_paths(payload: Any, wanted: set[str], prefix: str = "") -> list[str]:
    hits: list[str] = []

    if isinstance(payload, dict):
        for key, value in payload.items():
            key_str = str(key)
            path = f"{prefix}.{key_str}" if prefix else key_str

            if key_str in wanted:
                hits.append(path)

            hits.extend(find_key_paths(value, wanted, path))

    elif isinstance(payload, list):
        for i, value in enumerate(payload[:20]):
            path = f"{prefix}[{i}]"
            hits.extend(find_key_paths(value, wanted, path))

    return hits


def looks_interesting_url(url: str) -> bool:
    lower = url.lower()
    return any(keyword in lower for keyword in CAPTURE_KEYWORDS)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def browser_fetch_json(page, url: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
    return await page.evaluate(
        """
        async ({ url, method, body }) => {
            const options = {
                method,
                credentials: "include",
                headers: {
                    "content-type": "application/json",
                    "accept": "application/json, text/plain, */*"
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


def pick_genshin_role(roles_payload: dict[str, Any]) -> dict[str, Any] | None:
    data = roles_payload.get("json", {}).get("data") if isinstance(roles_payload.get("json"), dict) else None
    roles = data.get("list") if isinstance(data, dict) else None

    if not isinstance(roles, list):
        return None

    for role in roles:
        if not isinstance(role, dict):
            continue
        if role.get("game_biz") == "hk4e_global":
            return role

    for role in roles:
        if isinstance(role, dict) and ("region" in role or "region_name" in role):
            return role

    return None


async def try_known_artifact_endpoints(page, out_dir: Path) -> list[dict[str, Any]]:
    results = []

    roles_url = "https://api-account-os.hoyolab.com/binding/api/getUserGameRolesByCookie?game_biz=hk4e_global"

    print("[capture] Trying game roles endpoint...")
    roles_result = await browser_fetch_json(page, roles_url)
    write_json(out_dir / "active_fetch__game_roles.json", roles_result)

    role = pick_genshin_role(roles_result)
    if not role:
        print("[capture] Could not detect Genshin role from game roles response.")
        return results

    role_id = role.get("game_uid") or role.get("game_role_id") or role.get("role_id")
    server = role.get("region") or role.get("server")

    print(f"[capture] Detected role: role_id={role_id}, server={server}")

    if not role_id or not server:
        print("[capture] Role does not contain role_id/server.")
        return results

    candidates = [
        {
            "name": "bbs_character_post",
            "url": "https://bbs-api-os.hoyolab.com/game_record/genshin/api/character",
            "method": "POST",
            "body": {
                "role_id": str(role_id),
                "server": server,
            },
        },
        {
            "name": "bbs_index_get",
            "url": f"https://bbs-api-os.hoyolab.com/game_record/genshin/api/index?role_id={role_id}&server={server}",
            "method": "GET",
            "body": None,
        },
        {
            "name": "bbs_avatar_basic_get",
            "url": f"https://bbs-api-os.hoyolab.com/game_record/genshin/api/avatarBasicInfo?role_id={role_id}&server={server}",
            "method": "GET",
            "body": None,
        },
        {
            "name": "sg_public_character_post",
            "url": "https://sg-public-api.hoyolab.com/game_record/genshin/api/character",
            "method": "POST",
            "body": {
                "role_id": str(role_id),
                "server": server,
            },
        },
    ]

    for candidate in candidates:
        print(f"[capture] Trying active fetch: {candidate['name']}")
        try:
            result = await browser_fetch_json(
                page,
                candidate["url"],
                method=candidate["method"],
                body=candidate["body"],
            )
        except Exception as exc:
            result = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "candidate": candidate,
            }

        artifact_hits = find_key_paths(result.get("json"), ARTIFACT_FIELD_HINTS)
        result["artifactFieldHits"] = artifact_hits
        result["candidate"] = candidate

        write_json(out_dir / f"active_fetch__{candidate['name']}.json", result)

        results.append(
            {
                "name": candidate["name"],
                "ok": result.get("ok"),
                "status": result.get("status"),
                "retcode": (result.get("json") or {}).get("retcode") if isinstance(result.get("json"), dict) else None,
                "message": (result.get("json") or {}).get("message") if isinstance(result.get("json"), dict) else None,
                "artifactFieldHits": artifact_hits[:30],
            }
        )

    return results


async def main_async(seconds: int, auto_open_character_list: bool, active_fetch: bool) -> None:
    if get_auth_status(HOYOLAB_PROFILE_DIR) != AuthStatus.LOGGED_IN:
        raise SystemExit("HoYoLAB profile is not logged in. Authorize first.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = HOYOLAB_DEBUG_DIR / "endpoint_capture" / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

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

    captured: list[dict[str, Any]] = []
    counter = 0

    async def handle_response(response) -> None:
        nonlocal counter

        url = response.url
        if not looks_interesting_url(url):
            return

        content_type = response.headers.get("content-type", "")
        if "json" not in content_type.lower():
            return

        try:
            payload = await response.json()
        except Exception:
            return

        counter += 1
        filename = safe_name(url, counter)
        payload_path = out_dir / "responses" / filename

        artifact_hits = find_key_paths(payload, ARTIFACT_FIELD_HINTS)

        item = {
            "index": counter,
            "url": url,
            "status": response.status,
            "contentType": content_type,
            "savedAs": str(payload_path.relative_to(out_dir)).replace("\\", "/"),
            "topLevelKeys": json_preview_keys(payload),
            "artifactFieldHits": artifact_hits[:50],
            "hasArtifactHints": bool(artifact_hits),
        }

        captured.append(item)
        write_json(payload_path, payload)

        marker = " ARTIFACT?" if artifact_hits else ""
        print(f"[capture] {counter:03} {response.status} {url}{marker}")

    page.on("response", lambda response: asyncio.create_task(handle_response(response)))

    try:
        print("[capture] Opening HoYoLAB...")
        await page.goto(HOYOLAB_URL, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(3000)

        if auto_open_character_list:
            print("[capture] Trying to open character list...")
            try:
                locator = page.locator(".block-title-right").first
                await locator.wait_for(state="visible", timeout=20_000)
                await locator.evaluate("(el) => el.click()")
                await page.wait_for_timeout(3000)
            except Exception as exc:
                print(f"[capture] Could not auto-open character list: {type(exc).__name__}: {exc}")

        active_results = []
        if active_fetch:
            active_results = await try_known_artifact_endpoints(page, out_dir)

        print()
        print("[capture] Manual capture window is active.")
        print("[capture] In the browser, open character details/artifacts and scroll/click a few characters.")
        print(f"[capture] Waiting {seconds} seconds...")

        started = time.time()
        while time.time() - started < seconds:
            await page.wait_for_timeout(1000)

        summary = {
            "createdAt": timestamp,
            "outputDir": str(out_dir),
            "capturedCount": len(captured),
            "activeFetchResults": active_results,
            "responses": captured,
            "artifactLikelyResponses": [
                item for item in captured
                if item.get("hasArtifactHints")
            ],
        }

        write_json(out_dir / "summary.json", summary)

        print()
        print("[capture] Done.")
        print(f"[capture] Output: {out_dir}")
        print(f"[capture] Responses: {len(captured)}")
        print(f"[capture] Artifact-like responses: {len(summary['artifactLikelyResponses'])}")
        print("[capture] Open summary.json first.")

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
    parser.add_argument("--seconds", type=int, default=90)
    parser.add_argument("--no-auto-open", action="store_true")
    parser.add_argument("--no-active-fetch", action="store_true")
    args = parser.parse_args()

    run_async(
        main_async(
            seconds=args.seconds,
            auto_open_character_list=not args.no_auto_open,
            active_fetch=not args.no_active_fetch,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())