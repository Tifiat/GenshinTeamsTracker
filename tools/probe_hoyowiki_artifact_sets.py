from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTISCAN_PATH = PROJECT_ROOT / "artifacts_artiscan.json"

API_URL = "https://sg-wiki-api.hoyolab.com/hoyowiki/wapi/get_entry_page_list"

HEADERS_BASE = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://wiki.hoyolab.com",
}


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def fetch_artifact_sets(language: str) -> list[dict]:
    all_items: list[dict] = []
    page_num = 1
    page_size = 30

    while True:
        body = json.dumps(
            {
                "filters": [],
                "menu_id": "5",
                "page_num": page_num,
                "page_size": page_size,
                "use_es": True,
            },
            ensure_ascii=False,
        ).encode("utf-8")

        headers = dict(HEADERS_BASE)
        headers["x-rpc-language"] = language

        request = urllib.request.Request(
            API_URL,
            data=body,
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if payload.get("retcode") != 0:
            raise RuntimeError(
                f"HoYoWiki retcode={payload.get('retcode')} message={payload.get('message')}"
            )

        data = payload.get("data") or {}
        items = data.get("list") or []
        all_items.extend(items)

        total = int(data.get("total") or len(all_items))
        if len(all_items) >= total or not items:
            break

        page_num += 1

    return all_items


def load_artiscan_set_keys() -> set[str]:
    if not ARTISCAN_PATH.exists():
        return set()

    payload = json.loads(ARTISCAN_PATH.read_text(encoding="utf-8"))
    return {
        str(item.get("setKey") or "")
        for item in payload.get("artifacts") or []
        if item.get("setKey")
    }


def main() -> int:
    out_dir = PROJECT_ROOT / "debug" / "artifact_sets_probe"
    out_dir.mkdir(parents=True, exist_ok=True)

    en_items = fetch_artifact_sets("en-us")
    ru_items = fetch_artifact_sets("ru-ru")

    (out_dir / "hoyowiki_artifacts_en.json").write_text(
        json.dumps(en_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "hoyowiki_artifacts_ru.json").write_text(
        json.dumps(ru_items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"HoYoWiki EN sets: {len(en_items)}")
    print(f"HoYoWiki RU sets: {len(ru_items)}")
    print()

    print("Sample EN items:")
    for item in en_items[:5]:
        display = item.get("display_field") or {}
        print(
            "-",
            item.get("entry_page_id"),
            item.get("name"),
            "flower:",
            bool(display.get("flower_of_life_icon_url")),
        )

    print()

    artiscan_keys = load_artiscan_set_keys()
    if not artiscan_keys:
        print("artifacts_artiscan.json не найден или в нём нет setKey — матчинг пропущен.")
        return 0

    hoyowiki_by_normalized_name = {
        normalize_key(str(item.get("name") or "")): item
        for item in en_items
    }

    matched = []
    unmatched = []

    for key in sorted(artiscan_keys):
        normalized = normalize_key(key)
        item = hoyowiki_by_normalized_name.get(normalized)

        if item:
            matched.append((key, item.get("entry_page_id"), item.get("name")))
        else:
            unmatched.append(key)

    print(f"Artiscan unique setKey: {len(artiscan_keys)}")
    print(f"Matched by normalized English name: {len(matched)}")
    print(f"Unmatched: {len(unmatched)}")
    print()

    if matched:
        print("Matched sample:")
        for row in matched[:20]:
            print(" ", row)

    if unmatched:
        print()
        print("Unmatched:")
        for key in unmatched:
            print(" ", key)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())