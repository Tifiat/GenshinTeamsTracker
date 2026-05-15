import asyncio
import json
import time
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page, Response

try:
    from .hoyolab_exporter import HOYOLAB_URL, HoyolabExporter, close_export_context
except ImportError:
    from hoyolab_exporter import HOYOLAB_URL, HoyolabExporter, close_export_context


BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "profile"
OUTPUT_DIR = BASE_DIR / "debug_data"

CHARACTERS_FILE = OUTPUT_DIR / "account_characters.json"
WEAPONS_FILE = OUTPUT_DIR / "account_weapons.json"

WEAPON_TYPE_NAMES = {
    1: "sword",
    10: "catalyst",
    11: "claymore",
    12: "bow",
    13: "polearm",
}

DEFAULT_LANGUAGE_HEADERS = {
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "x-rpc-language": "ru-ru",
}


async def create_context(
    *,
    profile_dir: str | Path = PROFILE_DIR,
    download_dir: str | Path = OUTPUT_DIR,
) -> BrowserContext:
    exporter = HoyolabExporter(
        profile_dir=profile_dir,
        download_dir=download_dir,
        browser_window_width=1280,
        browser_window_height=900,
    )
    return await exporter._create_context()


async def is_login_open(page: Page) -> bool:
    if await page.locator("iframe#hyv-account-frame").count() > 0:
        return True

    return any(
        "account.hoyolab.com/login-platform" in frame.url for frame in page.frames
    )


async def wait_until_ready_or_login(page: Page, timeout_ms: int = 5 * 60_000) -> None:
    deadline = time.time() + timeout_ms / 1000

    while time.time() < deadline:
        if await is_login_open(page):
            raise RuntimeError(
                "HoYoLAB session is not active. Authorize HoYoLAB from the app, "
                "check that the account is visible on the HoYoLAB page, close the "
                "browser window, and run this script again."
            )

        if await page.locator(".block-title-right").count() > 0:
            try:
                if await page.locator(".block-title-right").first.is_visible(timeout=500):
                    return
            except Exception:
                pass

        await page.wait_for_timeout(500)

    raise RuntimeError("HoYoLAB page did not become ready: character button not found.")


async def open_character_list(page: Page) -> None:
    locator = page.locator(".block-title-right").first
    await locator.wait_for(state="visible", timeout=30_000)
    await locator.evaluate("(el) => el.click()")
    await page.wait_for_timeout(2500)


def normalize_character(item: dict[str, Any]) -> dict[str, Any]:
    weapon_type = item.get("weapon_type")

    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "rarity": item.get("rarity"),
        "element": item.get("element"),
        "level": item.get("level"),
        "constellation": item.get("actived_constellation_num"),
        "weapon_type": weapon_type,
        "weapon_type_name": WEAPON_TYPE_NAMES.get(weapon_type, str(weapon_type)),
        "icon": item.get("icon"),
        "side_icon": item.get("side_icon"),
    }


def normalize_weapon(item: dict[str, Any]) -> dict[str, Any] | None:
    weapon = item.get("weapon")
    if not isinstance(weapon, dict):
        return None

    weapon_type = weapon.get("type", item.get("weapon_type"))

    return {
        "id": weapon.get("id"),
        "name": weapon.get("name"),
        "rarity": weapon.get("rarity"),
        "type": weapon_type,
        "type_name": WEAPON_TYPE_NAMES.get(weapon_type, str(weapon_type)),
        "level": weapon.get("level"),
        "refinement": weapon.get("affix_level"),
        "icon": weapon.get("icon"),
        "equipped_by": {
            "id": item.get("id"),
            "name": item.get("name"),
        },
    }


def build_inventory(
    character_list: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build normalized inventory in the original HoYoLAB API order.

    Do not sort here. The API order currently matches the visual card order.
    UI sorting should happen later in the UI layer.
    """
    characters = [normalize_character(item) for item in character_list]

    weapons = []
    for item in character_list:
        weapon = normalize_weapon(item)
        if weapon is not None:
            weapons.append(weapon)

    return characters, weapons


def write_inventory(
    characters: list[dict[str, Any]],
    weapons: list[dict[str, Any]],
    output_dir: str | Path,
) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    characters_path = output_dir / "account_characters.json"
    weapons_path = output_dir / "account_weapons.json"

    characters_path.write_text(
        json.dumps(characters, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    weapons_path.write_text(
        json.dumps(weapons, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return characters_path, weapons_path


async def wait_for_character_list_response(
    page: Page,
    *,
    timeout_sec: int = 60,
) -> asyncio.Future[list[dict[str, Any]]]:
    character_list_future: asyncio.Future[list[dict[str, Any]]] = asyncio.Future()

    async def on_response(response: Response) -> None:
        if "/event/game_record/genshin/api/character/list" not in response.url:
            return

        try:
            payload = await response.json()
            items = payload.get("data", {}).get("list", [])
            if not isinstance(items, list):
                raise RuntimeError("character/list response has no data.list array")
            if not character_list_future.done():
                character_list_future.set_result(items)
                print(f"[HoYoLAB Inventory] Captured character/list: {len(items)} characters")
        except Exception as exc:
            if not character_list_future.done():
                character_list_future.set_exception(exc)

    page.on("response", lambda response: asyncio.create_task(on_response(response)))
    return character_list_future


async def collect_character_list(
    page: Page,
    character_list_future: asyncio.Future[list[dict[str, Any]]],
    *,
    timeout_sec: int = 60,
) -> list[dict[str, Any]]:
    print("[HoYoLAB Inventory] Opening character list...")
    await open_character_list(page)

    return await asyncio.wait_for(character_list_future, timeout=timeout_sec)


async def collect_inventory_from_page(
    page: Page,
    *,
    output_dir: str | Path | None = None,
    goto_hoyolab: bool = True,
    language_headers: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    await page.set_extra_http_headers(language_headers or DEFAULT_LANGUAGE_HEADERS)

    # Важно: listener должен быть установлен ДО page.goto(),
    # иначе можно поймать другой character/list response с другим порядком.
    character_list_future = await wait_for_character_list_response(page)

    if goto_hoyolab:
        print("[HoYoLAB Inventory] Opening HoYoLAB...")
        await page.goto(HOYOLAB_URL, wait_until="domcontentloaded", timeout=60_000)

    await wait_until_ready_or_login(page)

    character_list = await collect_character_list(page, character_list_future)
    characters, weapons = build_inventory(character_list)

    if output_dir is not None:
        characters_path, weapons_path = write_inventory(characters, weapons, output_dir)
        print(f"[HoYoLAB Inventory] Characters saved: {characters_path}")
        print(f"[HoYoLAB Inventory] Weapons saved: {weapons_path}")

    print(f"[HoYoLAB Inventory] Character count: {len(characters)}")
    print(f"[HoYoLAB Inventory] Equipped weapon count: {len(weapons)}")

    return characters, weapons


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    context = await create_context(profile_dir=PROFILE_DIR, download_dir=OUTPUT_DIR)
    page = context.pages[0] if context.pages else await context.new_page()

    try:
        await collect_inventory_from_page(
            page,
            output_dir=OUTPUT_DIR,
            goto_hoyolab=True,
        )
    finally:
        try:
            await page.close()
        except Exception:
            pass

        await close_export_context(context)


if __name__ == "__main__":
    asyncio.run(main())
