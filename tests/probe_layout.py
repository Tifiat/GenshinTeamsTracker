import asyncio
import argparse
import json
import gc
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hoyolab_export.hoyolab_exporter import HOYOLAB_URL, HoyolabExporter, close_export_context


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = BASE_DIR / "probe_layout_output"
DEFAULT_PROFILE_DIR = PROJECT_ROOT / "hoyolab_export" / "profile"
DEFAULT_DEBUG_PORT = None


def timestamp_dir() -> Path:
    return OUTPUT_ROOT / time.strftime("%Y%m%d_%H%M%S")


async def collect_layout_probe(page, exporter: HoyolabExporter) -> dict[str, Any]:
    return await page.evaluate(
        """
        ({scale, fixedContainerWidth}) => {
            const round = (value) => Math.round(value * 100) / 100;
            const boxOf = (el) => {
                const r = el.getBoundingClientRect();
                return {
                    x: round(r.x),
                    y: round(r.y),
                    left: round(r.left),
                    top: round(r.top),
                    right: round(r.right),
                    bottom: round(r.bottom),
                    width: round(r.width),
                    height: round(r.height),
                };
            };
            const visible = (el) => {
                const r = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                return r.width > 0
                    && r.height > 0
                    && style.display !== "none"
                    && style.visibility !== "hidden"
                    && Number(style.opacity || 1) > 0;
            };
            const rootProbe = window.__genshin_export_root_probe__ || null;
            const rootRect = rootProbe && rootProbe.rootRect ? rootProbe.rootRect : null;
            const relativeToRoot = (box) => {
                if (!rootRect) return null;
                return {
                    left: round(box.left - rootRect.left),
                    top: round(box.top - rootRect.top),
                    right: round(box.right - rootRect.left),
                    bottom: round(box.bottom - rootRect.top),
                    width: box.width,
                    height: box.height,
                };
            };
            const textLooksUseful = (text) => {
                return /(Lv\\.|Ур\\.|Pair|C\\d|Rank|精炼|命之座|等级)/i.test(text);
            };

            const selectors = [
                ".all-role *",
                "[class*='all-role'] *",
                "[class*='role']",
                "[class*='avatar']",
                "[class*='card']",
                "li",
                "section",
                "div",
            ];
            const seen = new Set();
            const candidates = [];

            for (const selector of selectors) {
                for (const el of document.querySelectorAll(selector)) {
                    if (seen.has(el) || !visible(el)) continue;
                    seen.add(el);

                    const box = boxOf(el);
                    if (box.width < 40 || box.height < 30 || box.width > 700 || box.height > 320) {
                        continue;
                    }

                    const text = (el.innerText || "").replace(/\\s+/g, " ").trim();
                    const images = Array.from(el.querySelectorAll("img")).filter(visible);
                    if (images.length < 1) continue;
                    if (images.length < 2 && !textLooksUseful(text)) continue;

                    const imageInfo = images.map((img, imageIndex) => {
                        const imageBox = boxOf(img);
                        return {
                            imageIndex,
                            src: img.currentSrc || img.src || "",
                            alt: img.alt || "",
                            className: String(img.className || ""),
                            box: imageBox,
                            rootRelativeBox: relativeToRoot(imageBox),
                        };
                    });

                    candidates.push({
                        candidateIndex: candidates.length,
                        tagName: el.tagName,
                        className: String(el.className || ""),
                        text,
                        box,
                        rootRelativeBox: relativeToRoot(box),
                        images: imageInfo,
                    });
                }
            }

            candidates.sort((a, b) => {
                const dy = a.box.top - b.box.top;
                if (Math.abs(dy) > 8) return dy;
                return a.box.left - b.box.left;
            });

            const deduped = [];
            for (const item of candidates) {
                const duplicate = deduped.some((prev) => {
                    return Math.abs(prev.box.left - item.box.left) < 3
                        && Math.abs(prev.box.top - item.box.top) < 3
                        && Math.abs(prev.box.width - item.box.width) < 3
                        && Math.abs(prev.box.height - item.box.height) < 3;
                });
                if (!duplicate) {
                    item.candidateIndex = deduped.length;
                    deduped.push(item);
                }
            }

            return {
                sourceUrl: location.href,
                capturedAt: Date.now(),
                exporter: {
                    scale,
                    fixedContainerWidth,
                    expectedImageWidth: scale * fixedContainerWidth,
                },
                page: {
                    devicePixelRatio: window.devicePixelRatio,
                    scrollX: window.scrollX,
                    scrollY: window.scrollY,
                    viewport: {
                        width: window.innerWidth,
                        height: window.innerHeight,
                    },
                },
                html2canvasRootProbe: rootProbe,
                candidateCount: deduped.length,
                candidates: deduped,
            };
        }
        """,
        {
            "scale": exporter.scale,
            "fixedContainerWidth": exporter.fixed_container_width,
        },
    )


async def run_probe(debug_port: int | None = DEFAULT_DEBUG_PORT, profile_dir: Path = DEFAULT_PROFILE_DIR) -> Path:
    output_dir = timestamp_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    exporter = HoyolabExporter(
        profile_dir=profile_dir,
        download_dir=output_dir,
        scale=4,
        fixed_container_width=500,
        browser_window_width=1280,
        browser_window_height=900,
        image_format="png",
        remote_debugging_port=debug_port,
        keep_browser_open=debug_port is not None,
    )

    context = await exporter._create_context()

    try:
        page = context.pages[0] if context.pages else await context.new_page()
        await exporter._prepare_export_page(page)
        await page.goto(HOYOLAB_URL, wait_until="domcontentloaded", timeout=60_000)

        download = await exporter._run_export_flow(page)
        suggested_name = download.suggested_filename or "image.png"
        if not suggested_name.lower().endswith(".png"):
            suggested_name = Path(suggested_name).stem + ".png"
        image_path = output_dir / suggested_name
        await download.save_as(str(image_path))
        exporter._validate_image(image_path)

        await page.wait_for_timeout(1000)
        probe = await collect_layout_probe(page, exporter)
        probe["downloadedImage"] = image_path.name

        (output_dir / "layout_probe.json").write_text(
            json.dumps(probe, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        await page.screenshot(path=str(output_dir / "page_screenshot.png"), full_page=True)

        print(f"[Probe] Saved bundle: {output_dir}")
        print(f"[Probe] Candidates: {probe.get('candidateCount')}")
        print(f"[Probe] Root probe present: {bool(probe.get('html2canvasRootProbe'))}")
        return output_dir

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--debug-port",
        type=int,
        default=DEFAULT_DEBUG_PORT,
        help="Optional CDP port to attach to or launch. Omit or use 0 for browser-assigned port.",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
        help="Chrome user-data-dir for the probe browser.",
    )
    args = parser.parse_args()
    port = args.debug_port if args.debug_port != 0 else None
    run_async(run_probe(debug_port=port, profile_dir=args.profile_dir))
