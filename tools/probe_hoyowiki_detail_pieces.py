from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUT_DIR = PROJECT_ROOT / "debug" / "hoyowiki_detail_pieces_probe"
OUT_JSON = OUT_DIR / "summary.json"
OUT_TXT = OUT_DIR / "summary.txt"

API_BASE = "https://sg-wiki-api.hoyolab.com/hoyowiki/wapi"

# Проверяем конкретно сет, где заметили проблему.
TARGET_ENTRY_IDS = {
    "8520": "Night of the Sky's Unveiling",
}

LANGUAGES = ["en-us", "ru-ru"]

ENDPOINTS = [
    "entry_page",
    "get_entry_page",
    "entry_page_detail",
    "get_entry_page_detail",
]

BODY_VARIANTS = [
    lambda entry_id: {"entry_page_id": entry_id},
    lambda entry_id: {"id": entry_id},
    lambda entry_id: {"page_id": entry_id},
]


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


SLOT_WORDS = [
    "flower",
    "plume",
    "sands",
    "goblet",
    "circlet",
    "цветок",
    "перо",
    "пески",
    "кубок",
    "корона",
    "life",
    "death",
    "eon",
    "eonothem",
    "logos",
]


def request_json(
    *,
    method: str,
    url: str,
    language: str,
    body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://wiki.hoyolab.com",
        "x-rpc-language": language,
        "Accept": "application/json, text/plain, */*",
    }

    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read()
        status = response.status

    text = raw.decode("utf-8", errors="replace")

    try:
        return status, json.loads(text)
    except json.JSONDecodeError:
        return status, {"__raw_text": text[:5000]}


def looks_success(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False

    if payload.get("retcode") == 0 and payload.get("data") not in (None, {}, [], ""):
        return True

    if payload.get("data") not in (None, {}, [], ""):
        return True

    return False


def compact(value: Any, max_len: int = 180) -> str:
    text = json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def walk(value: Any, path: str = "$"):
    yield path, value

    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{path}[{index}]")


def list_item_score(item: Any) -> int:
    if not isinstance(item, dict):
        return 0

    text = json.dumps(item, ensure_ascii=False).casefold()
    score = 0

    if "icon" in text or "icon_url" in text:
        score += 3

    if "name" in text:
        score += 1

    for word in SLOT_WORDS:
        if word in text:
            score += 2

    return score


def find_piece_like_lists(payload: Any) -> list[dict[str, Any]]:
    found = []

    for path, value in walk(payload):
        if not isinstance(value, list):
            continue

        dict_items = [item for item in value if isinstance(item, dict)]
        if len(dict_items) < 3:
            continue

        scores = [list_item_score(item) for item in dict_items]
        total_score = sum(scores)

        if total_score < 10:
            continue

        found.append(
            {
                "path": path,
                "items_count": len(dict_items),
                "total_score": total_score,
                "sample_items": dict_items[:8],
            }
        )

    return sorted(found, key=lambda item: item["total_score"], reverse=True)


def find_icon_fields(payload: Any) -> list[dict[str, str]]:
    found = []

    for path, value in walk(payload):
        if not isinstance(value, str):
            continue

        low_path = path.casefold()
        low_value = value.casefold()

        if "icon" in low_path or "icon" in low_value or ".png" in low_value or ".webp" in low_value:
            found.append(
                {
                    "path": path,
                    "value": value,
                }
            )

    return found[:200]


def probe_one(entry_id: str, language: str) -> list[dict[str, Any]]:
    results = []

    for endpoint in ENDPOINTS:
        base_url = f"{API_BASE}/{endpoint}"

        for body_func in BODY_VARIANTS:
            body = body_func(entry_id)
            try:
                status, payload = request_json(
                    method="POST",
                    url=base_url,
                    language=language,
                    body=body,
                )
                success = looks_success(payload)

                results.append(
                    {
                        "language": language,
                        "endpoint": endpoint,
                        "method": "POST",
                        "body": body,
                        "http_status": status,
                        "success": success,
                        "payload": payload if success else None,
                        "error": None,
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "language": language,
                        "endpoint": endpoint,
                        "method": "POST",
                        "body": body,
                        "http_status": None,
                        "success": False,
                        "payload": None,
                        "error": str(exc),
                    }
                )

        query = urllib.parse.urlencode({"entry_page_id": entry_id})
        try:
            status, payload = request_json(
                method="GET",
                url=f"{base_url}?{query}",
                language=language,
                body=None,
            )
            success = looks_success(payload)

            results.append(
                {
                    "language": language,
                    "endpoint": endpoint,
                    "method": "GET",
                    "query": {"entry_page_id": entry_id},
                    "http_status": status,
                    "success": success,
                    "payload": payload if success else None,
                    "error": None,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "language": language,
                    "endpoint": endpoint,
                    "method": "GET",
                    "query": {"entry_page_id": entry_id},
                    "http_status": None,
                    "success": False,
                    "payload": None,
                    "error": str(exc),
                }
            )

    return results


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "targets": TARGET_ENTRY_IDS,
        "responses": [],
    }

    lines: list[str] = []
    lines.append("HoYoWiki detail pieces probe")
    lines.append("=" * 100)

    for entry_id, name in TARGET_ENTRY_IDS.items():
        lines.append("")
        lines.append(f"TARGET entry_page_id={entry_id} name={name}")
        lines.append("-" * 100)

        for language in LANGUAGES:
            results = probe_one(entry_id, language)
            successful = [item for item in results if item["success"]]

            lines.append(f"{language}: successful responses = {len(successful)}")

            for index, item in enumerate(successful, start=1):
                payload = item["payload"]

                response_path = OUT_DIR / f"{entry_id}_{language}_{index}_{item['endpoint']}_{item['method']}.json"
                response_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                piece_lists = find_piece_like_lists(payload)
                icon_fields = find_icon_fields(payload)

                response_summary = {
                    "entry_page_id": entry_id,
                    "name": name,
                    "language": language,
                    "endpoint": item["endpoint"],
                    "method": item["method"],
                    "body": item.get("body"),
                    "query": item.get("query"),
                    "response_path": response_path.relative_to(PROJECT_ROOT).as_posix(),
                    "piece_like_lists": piece_lists[:10],
                    "icon_fields": icon_fields[:80],
                }
                summary["responses"].append(response_summary)

                lines.append("")
                lines.append(
                    f"  SUCCESS {index}: {language} {item['method']} /{item['endpoint']} "
                    f"-> {response_path.relative_to(PROJECT_ROOT).as_posix()}"
                )

                lines.append("  Piece-like lists:")
                if piece_lists:
                    for candidate in piece_lists[:5]:
                        lines.append(
                            f"    path={candidate['path']} "
                            f"items={candidate['items_count']} "
                            f"score={candidate['total_score']}"
                        )
                        for sample in candidate["sample_items"][:5]:
                            lines.append(f"      {compact(sample)}")
                else:
                    lines.append("    none")

                lines.append("  Icon fields sample:")
                if icon_fields:
                    for field in icon_fields[:20]:
                        lines.append(f"    {field['path']} = {field['value']}")
                else:
                    lines.append("    none")

    OUT_JSON.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")

    print(f"written txt: {OUT_TXT}")
    print(f"written json: {OUT_JSON}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())