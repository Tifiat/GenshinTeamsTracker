"""Manual/automated PvP site research sandbox.

Temporary research helper for the PvP planning contract. It keeps browser
profiles and captures under tools/experiments/pvp_site_audit/ so login/session
state and screenshots do not spread into the main project.

Usage:
  .\.venv\Scripts\python.exe tools\experiments\pvp_site_audit\pvp_site_probe.py --site abyss --headed
  .\.venv\Scripts\python.exe tools\experiments\pvp_site_audit\pvp_site_probe.py --site gentor --headed
  .\.venv\Scripts\python.exe tools\experiments\pvp_site_audit\pvp_site_probe.py --site all
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from playwright.sync_api import BrowserContext, Page, sync_playwright


ROOT = Path(__file__).resolve().parent
CAPTURES = ROOT / "captures"
PROFILES = ROOT / "profiles"

SITES = {
    "abyss": [
        "https://abyss.darte.gg/",
        "https://abyss.darte.gg/drafts",
        "https://abyss.darte.gg/draft-systems",
        "https://abyss.darte.gg/rooms",
    ],
    "gentor": [
        "https://gentor.vercel.app/",
        "https://gentor.vercel.app/planilhas",
        "https://gentor.vercel.app/salas",
        "https://gentor.vercel.app/partidas",
    ],
}

CHROME_CANDIDATES = (
    Path(os.environ.get("ProgramFiles", "")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("ProgramFiles(x86)", "")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
)

KEYWORDS = (
    "draft",
    "ban",
    "pick",
    "preban",
    "immune",
    "mirror",
    "deck",
    "room",
    "lobby",
    "ready",
    "timer",
    "judge",
    "spectator",
    "weapon",
    "character",
    "player",
    "ruleset",
    "planilha",
    "sala",
    "partida",
    "jogador",
    "arma",
    "personagem",
)


@dataclass
class PageSummary:
    site: str
    requested_url: str
    final_url: str
    title: str
    text_sample: str
    links: list[str]
    buttons: list[str]
    keyword_counts: dict[str, int]
    network_urls: list[str]
    screenshot: str


def _safe_name(value: str) -> str:
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_")
    return value[:120] or "page"


def _visible_strings(page: Page, selector: str) -> list[str]:
    try:
        values = page.locator(selector).evaluate_all(
            """nodes => nodes
                .map(node => (node.innerText || node.textContent || node.getAttribute('aria-label') || '').trim())
                .filter(Boolean)
                .slice(0, 80)"""
        )
    except Exception:
        return []
    return [str(item) for item in values]


def _keyword_counts(text: str) -> dict[str, int]:
    folded = text.casefold()
    return {
        keyword: folded.count(keyword.casefold())
        for keyword in KEYWORDS
        if folded.count(keyword.casefold())
    }


def _probe_page(context: BrowserContext, site: str, url: str, wait_ms: int) -> PageSummary:
    network_urls: list[str] = []
    page = context.new_page()
    page.on("request", lambda request: network_urls.append(request.url))
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_timeout(wait_ms)
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass

    title = page.title()
    text = page.locator("body").inner_text(timeout=10_000) if page.locator("body").count() else ""
    links = _visible_strings(page, "a")
    buttons = _visible_strings(page, "button,[role=button]")
    screenshot_path = CAPTURES / f"{site}_{_safe_name(url)}.png"
    page.screenshot(path=screenshot_path, full_page=True)

    return PageSummary(
        site=site,
        requested_url=url,
        final_url=page.url,
        title=title,
        text_sample=text[:4000],
        links=links,
        buttons=buttons,
        keyword_counts=_keyword_counts(text + "\n" + "\n".join(links + buttons)),
        network_urls=sorted(set(network_urls))[:300],
        screenshot=str(screenshot_path.relative_to(ROOT)),
    )


def _urls_for(site: str) -> Iterable[tuple[str, str]]:
    if site == "all":
        for name, urls in SITES.items():
            for url in urls:
                yield name, url
        return
    for url in SITES[site]:
        yield site, url


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe PvP reference sites.")
    parser.add_argument("--site", choices=["all", *SITES.keys()], default="all")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--executable-path", default="")
    parser.add_argument("--wait-ms", type=int, default=3500)
    args = parser.parse_args()

    CAPTURES.mkdir(parents=True, exist_ok=True)
    PROFILES.mkdir(parents=True, exist_ok=True)

    results: list[PageSummary] = []
    with sync_playwright() as playwright:
        executable_path = args.executable_path or next(
            (str(path) for path in CHROME_CANDIDATES if path and path.exists()),
            None,
        )
        for site, url in _urls_for(args.site):
            profile_dir = PROFILES / site
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=not args.headed,
                executable_path=executable_path,
                viewport={"width": 1440, "height": 1000},
                locale="en-US",
            )
            try:
                results.append(_probe_page(context, site, url, args.wait_ms))
            finally:
                context.close()

    output = CAPTURES / "summary.json"
    output.write_text(
        json.dumps([asdict(item) for item in results], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
