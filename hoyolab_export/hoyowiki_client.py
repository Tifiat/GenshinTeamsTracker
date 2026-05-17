from __future__ import annotations

import json
import urllib.request
from typing import Any, Iterable
from urllib.parse import quote


HOYOWIKI_ENTRY_PAGE_LIST_URL = (
    "https://sg-wiki-api.hoyolab.com/hoyowiki/wapi/get_entry_page_list"
)
HOYOWIKI_ENTRY_PAGE_URL = "https://sg-wiki-api.hoyolab.com/hoyowiki/wapi/entry_page"
HOYOWIKI_USER_AGENT = "GenshinTeamsTracker/1.0"
DEFAULT_HOYOWIKI_LANGUAGE = "en-us"


class HoYoWikiError(RuntimeError):
    pass


def normalize_hoyowiki_language(language: str | None) -> str:
    value = str(language or "").strip().replace("_", "-").lower()
    if not value or value == "en":
        return DEFAULT_HOYOWIKI_LANGUAGE
    return value


def _request_headers(language: str) -> dict[str, str]:
    return {
        "User-Agent": HOYOWIKI_USER_AGENT,
        "Referer": "https://wiki.hoyolab.com",
        "x-rpc-language": normalize_hoyowiki_language(language),
        "Accept": "application/json, text/plain, */*",
    }


def _request_json(
    url: str,
    *,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    headers = _request_headers(language)
    data = None

    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(payload, dict):
        raise HoYoWikiError(f"HoYoWiki response is not a JSON object: {url}")

    if payload.get("retcode") != 0:
        raise HoYoWikiError(
            f"HoYoWiki retcode={payload.get('retcode')} "
            f"message={payload.get('message')}"
        )

    return payload


def fetch_hoyowiki_entry_page(
    entry_page_id: str | int,
    *,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
    timeout: float = 30.0,
) -> dict[str, Any]:
    entry_page_id = str(entry_page_id or "").strip()
    if not entry_page_id:
        raise HoYoWikiError("empty HoYoWiki entry_page_id")

    payload = _request_json(
        f"{HOYOWIKI_ENTRY_PAGE_URL}?entry_page_id={quote(entry_page_id)}",
        language=language,
        timeout=timeout,
    )
    page = (payload.get("data") or {}).get("page") or {}
    if not isinstance(page, dict):
        raise HoYoWikiError(f"HoYoWiki entry_page has no page object: {entry_page_id}")
    return page


def fetch_hoyowiki_entry_page_list(
    menu_id: str | int,
    *,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
    filters: list[dict[str, Any]] | None = None,
    page_size: int = 30,
    use_es: bool = True,
    max_pages: int | None = None,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    menu_id = str(menu_id or "").strip()
    if not menu_id:
        raise HoYoWikiError("empty HoYoWiki menu_id")

    result: list[dict[str, Any]] = []
    page_num = 1

    while True:
        payload = _request_json(
            HOYOWIKI_ENTRY_PAGE_LIST_URL,
            language=language,
            method="POST",
            timeout=timeout,
            body={
                "filters": filters or [],
                "menu_id": menu_id,
                "page_num": page_num,
                "page_size": int(page_size),
                "use_es": use_es,
            },
        )

        data = payload.get("data") or {}
        items = data.get("list") or []
        if not isinstance(items, list):
            raise HoYoWikiError(f"HoYoWiki entry list has no data.list: {menu_id}")

        result.extend(item for item in items if isinstance(item, dict))

        total = int(data.get("total") or len(result))
        if len(result) >= total or not items:
            break
        if max_pages is not None and page_num >= max_pages:
            break

        page_num += 1

    return result


def iter_hoyowiki_components(page: dict[str, Any]) -> Iterable[dict[str, Any]]:
    modules = page.get("modules") or []
    if not isinstance(modules, list):
        return

    for module in modules:
        if not isinstance(module, dict):
            continue
        components = module.get("components") or []
        if not isinstance(components, list):
            continue
        for component in components:
            if isinstance(component, dict):
                yield component


def find_hoyowiki_components(
    page: dict[str, Any],
    component_id: str,
) -> list[dict[str, Any]]:
    component_id = str(component_id or "").strip()
    if not component_id:
        return []

    return [
        component
        for component in iter_hoyowiki_components(page)
        if component.get("component_id") == component_id
    ]


def find_first_hoyowiki_component(
    page: dict[str, Any],
    component_id: str,
) -> dict[str, Any] | None:
    components = find_hoyowiki_components(page, component_id)
    return components[0] if components else None


def parse_hoyowiki_component_data(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return None

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None
