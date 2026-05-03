import argparse
import asyncio
import gc
import json
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
    target_frame = page.main_frame
    frame_checks = []

    for frame_index, frame in enumerate(page.frames):
        try:
            check = await frame.evaluate(
                """
                () => {
                    const rootProbe = window.__genshin_export_root_probe__ || null;
                    const patchStatus = window.__genshin_html2canvas_patch_status__ || null;
                    return {
                        hasRootProbe: Boolean(rootProbe),
                        calls: patchStatus && Array.isArray(patchStatus.calls) ? patchStatus.calls.length : 0,
                        url: window.location.href,
                    };
                }
                """
            )
            check["frameIndex"] = frame_index
            frame_checks.append(check)
            if check.get("hasRootProbe"):
                target_frame = frame
        except Exception as exc:
            frame_checks.append(
                {
                    "frameIndex": frame_index,
                    "url": frame.url,
                    "error": str(exc),
                }
            )

    await target_frame.evaluate(
        """
        (routeStatus) => {
            const current = window.__genshin_html2canvas_patch_status__ || {};
            window.__genshin_html2canvas_patch_status__ = {
                ...routeStatus,
                ...current,
                attempted: Boolean(routeStatus.attempted || current.attempted),
                matched: Boolean(routeStatus.matched || current.matched),
                strategy: current.strategy || routeStatus.strategy || null,
                calls: [
                    ...(Array.isArray(routeStatus.calls) ? routeStatus.calls : []),
                    ...(Array.isArray(current.calls) ? current.calls : []),
                ],
                errors: [
                    ...(Array.isArray(routeStatus.errors) ? routeStatus.errors : []),
                    ...(Array.isArray(current.errors) ? current.errors : []),
                ],
                routeMatches: routeStatus.routeMatches || current.routeMatches || [],
                routeMisses: routeStatus.routeMisses || current.routeMisses || [],
            };
        }
        """,
        exporter.html2canvas_patch_status,
    )

    probe = await target_frame.evaluate(
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
                if (!el || !el.getBoundingClientRect) return false;
                const r = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                return r.width > 0
                    && r.height > 0
                    && style.display !== "none"
                    && style.visibility !== "hidden"
                    && Number(style.opacity || 1) > 0;
            };
            const normalizeText = (text, limit) => String(text || "").replace(/\\s+/g, " ").trim().slice(0, limit);
            const relativeBox = (box, rootRect) => {
                if (!box || !rootRect) return null;
                return {
                    left: round(box.left - rootRect.left),
                    top: round(box.top - rootRect.top),
                    right: round(box.right - rootRect.left),
                    bottom: round(box.bottom - rootRect.top),
                    width: box.width,
                    height: box.height,
                };
            };
            const imageInfoOf = (img, rootRect, imageIndex = 0) => {
                const imageBox = boxOf(img);
                return {
                    imageIndex,
                    src: img.src || "",
                    currentSrc: img.currentSrc || "",
                    alt: img.alt || "",
                    className: String(img.className || ""),
                    rect_viewport: imageBox,
                    rect_root_relative: relativeBox(imageBox, rootRect),
                };
            };
            const compactEl = (el) => el ? {
                tag: el.tagName || null,
                id: el.id || "",
                className: String(el.className || "").slice(0, 240),
            } : null;
            const parentChainOf = (el) => {
                const chain = [];
                let current = el ? el.parentElement : null;
                while (current && chain.length < 5) {
                    chain.push(compactEl(current));
                    current = current.parentElement;
                }
                return chain;
            };
            const rootProbe = window.__genshin_export_root_probe__ || null;
            const cloneProbe = window.__genshin_export_clone_probe__ || null;
            const patchStatus = window.__genshin_html2canvas_patch_status__ || {
                attempted: false,
                matched: false,
                strategy: null,
                calls: [],
                errors: ["window.__genshin_html2canvas_patch_status__ was not found"],
            };
            const probeOfRoot = (root, source) => {
                if (!root) return null;
                const style = getComputedStyle(root);
                const rootBox = boxOf(root);
                const bgCount = Array.from(root.querySelectorAll("*")).filter((el) => {
                    const bg = getComputedStyle(el).backgroundImage;
                    return bg && bg !== "none";
                }).length;
                return {
                    source,
                    tag: root.tagName || null,
                    id: root.id || "",
                    className: String(root.className || ""),
                    textPreview: normalizeText(root.innerText || root.textContent, 300),
                    rect: rootBox,
                    rootRect: rootBox,
                    rect_viewport: rootBox,
                    imageCount: root.querySelectorAll("img").length,
                    backgroundImageCount: bgCount,
                    backgroundImage: style.backgroundImage && style.backgroundImage !== "none" ? style.backgroundImage : "",
                };
            };
            const fallbackCandidateScore = (root) => {
                const rect = root.getBoundingClientRect();
                const descendants = Array.from(root.querySelectorAll("*"));
                const imgCount = root.querySelectorAll("img").length;
                const bgCount = descendants.filter((el) => {
                    const bg = getComputedStyle(el).backgroundImage;
                    return bg && bg !== "none";
                }).length;
                return {
                    root,
                    rect: boxOf(root),
                    imgCount,
                    bgCount,
                    totalLike: imgCount + bgCount,
                    widthDistance: Math.abs(rect.width - fixedContainerWidth),
                };
            };
            const findFallbackRoot = () => {
                const candidates = Array.from(document.querySelectorAll("div,section,main"))
                    .filter(visible)
                    .map(fallbackCandidateScore)
                    .filter((item) => item.rect.width >= 300
                        && item.rect.width <= 900
                        && item.rect.height >= 300
                        && (item.imgCount >= 3 || item.bgCount >= 3))
                    .sort((a, b) => {
                        if (a.widthDistance !== b.widthDistance) return a.widthDistance - b.widthDistance;
                        if (a.totalLike !== b.totalLike) return b.totalLike - a.totalLike;
                        return b.rect.height - a.rect.height;
                    });
                return candidates[0] ? candidates[0].root : null;
            };

            let rootSource = "none";
            let selectedRoot = null;
            if (rootProbe && rootProbe.rootRect) {
                rootSource = "html2canvas_patch";
                selectedRoot = document.querySelector('[data-gtt-export-root="1"]');
            }
            if (!selectedRoot) {
                const markedRoot = document.querySelector('[data-gtt-export-root="1"]');
                if (markedRoot) {
                    selectedRoot = markedRoot;
                    rootSource = "marked_root";
                }
            }
            if (!selectedRoot) {
                const fallbackRoot = findFallbackRoot();
                if (fallbackRoot) {
                    fallbackRoot.setAttribute("data-gtt-export-root-fallback", "1");
                    selectedRoot = fallbackRoot;
                    rootSource = "fallback_candidate";
                }
            }

            const selectedRootRect = selectedRoot ? boxOf(selectedRoot) : (rootProbe ? rootProbe.rootRect : null);
            const fallbackRootProbe = rootSource === "fallback_candidate" || rootSource === "marked_root"
                ? probeOfRoot(selectedRoot, rootSource)
                : null;
            const relativeToRoot = (box) => relativeBox(box, selectedRootRect);
            const textLooksUseful = (text) => /(Lv\\.|Pair|C\\d|Rank|Ур\\.)/i.test(text);

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

                    const text = normalizeText(el.innerText || el.textContent, 500);
                    const images = Array.from(el.querySelectorAll("img")).filter(visible);
                    if (images.length < 1) continue;
                    if (images.length < 2 && !textLooksUseful(text)) continue;

                    candidates.push({
                        candidateIndex: candidates.length,
                        tagName: el.tagName,
                        className: String(el.className || ""),
                        text,
                        box,
                        rootRelativeBox: relativeToRoot(box),
                        images: images.map((img, imageIndex) => imageInfoOf(img, selectedRootRect, imageIndex)),
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

            const imageLike = [];
            if (selectedRoot) {
                const inside = Array.from(selectedRoot.querySelectorAll("*"));
                for (const el of inside) {
                    if (!visible(el)) continue;
                    const style = getComputedStyle(el);
                    const backgroundImage = style.backgroundImage && style.backgroundImage !== "none" ? style.backgroundImage : "";
                    const images = Array.from(el.querySelectorAll("img")).filter(visible);
                    const isImageLike = el.tagName === "IMG" || Boolean(backgroundImage) || images.length > 0;
                    if (!isImageLike) continue;
                    const rect = boxOf(el);
                    imageLike.push({
                        index: imageLike.length,
                        tag: el.tagName,
                        id: el.id || "",
                        className: String(el.className || ""),
                        textPreview: normalizeText(el.innerText || el.textContent, 120),
                        rect_viewport: rect,
                        rect_root_relative: relativeBox(rect, selectedRootRect),
                        backgroundImage,
                        images: el.tagName === "IMG"
                            ? [imageInfoOf(el, selectedRootRect, 0)]
                            : images.map((img, imageIndex) => imageInfoOf(img, selectedRootRect, imageIndex)),
                        parentChain: parentChainOf(el),
                    });
                    if (imageLike.length >= 300) break;
                }
            }

            const rootDiscovery = selectedRoot ? {
                totalElementsInsideRoot: selectedRoot.querySelectorAll("*").length,
                imageLike,
            } : {
                totalElementsInsideRoot: 0,
                imageLike: [],
            };

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
                html2canvasPatchStatus: patchStatus,
                html2canvasRootProbe: rootProbe,
                html2canvasCloneProbe: cloneProbe,
                fallbackRootProbe,
                rootSource: cloneProbe ? "html2canvas_clone" : rootSource,
                rootDiscovery: cloneProbe && cloneProbe.rootDiscovery ? cloneProbe.rootDiscovery : rootDiscovery,
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

    probe["frameChecks"] = frame_checks
    probe["selectedFrameUrl"] = target_frame.url
    return probe


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
        try:
            probe = await collect_layout_probe(page, exporter)
        except Exception as exc:
            probe = {
                "sourceUrl": page.url,
                "capturedAt": int(time.time() * 1000),
                "exporter": {
                    "scale": exporter.scale,
                    "fixedContainerWidth": exporter.fixed_container_width,
                    "expectedImageWidth": exporter.scale * exporter.fixed_container_width,
                },
                "html2canvasPatchStatus": {
                    "attempted": False,
                    "matched": False,
                    "strategy": None,
                    "calls": [],
                    "errors": [f"collect_layout_probe failed: {exc!r}"],
                },
                "html2canvasRootProbe": None,
                "fallbackRootProbe": None,
                "rootSource": "none",
                "rootDiscovery": {
                    "totalElementsInsideRoot": 0,
                    "imageLike": [],
                },
                "candidateCount": 0,
                "candidates": [],
            }
        probe["downloadedImage"] = image_path.name

        frame_probes = []
        for frame_index, frame in enumerate(page.frames):
            try:
                frame_probe = await frame.evaluate(
                    """
                    () => {
                        const rootProbe = window.__genshin_export_root_probe__ || null;
                        const patchStatus = window.__genshin_html2canvas_patch_status__ || null;
                        const markedRoot = document.querySelector('[data-gtt-export-root="1"]');
                        const markedRect = markedRoot ? markedRoot.getBoundingClientRect() : null;

                        return {
                            url: window.location.href,
                            hasRootProbe: Boolean(rootProbe),
                            rootProbe,
                            hasPatchStatus: Boolean(patchStatus),
                            patchStatus,
                            markedRoot: markedRoot ? {
                                tag: markedRoot.tagName || null,
                                id: markedRoot.id || "",
                                className: typeof markedRoot.className === "string" ? markedRoot.className : "",
                                rect: markedRect ? {
                                    x: markedRect.x,
                                    y: markedRect.y,
                                    left: markedRect.left,
                                    top: markedRect.top,
                                    right: markedRect.right,
                                    bottom: markedRect.bottom,
                                    width: markedRect.width,
                                    height: markedRect.height
                                } : null
                            } : null
                        };
                    }
                    """
                )
                frame_probe["frameIndex"] = frame_index
                frame_probes.append(frame_probe)
            except Exception as exc:
                frame_probes.append(
                    {
                        "frameIndex": frame_index,
                        "url": frame.url,
                        "error": str(exc),
                    }
                )

        probe["frameProbes"] = frame_probes

        (output_dir / "layout_probe.json").write_text(
            json.dumps(probe, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        await page.screenshot(path=str(output_dir / "page_screenshot.png"), full_page=True)

        patch_status = probe.get("html2canvasPatchStatus") or {}
        root_discovery = probe.get("rootDiscovery") or {}
        image_like = root_discovery.get("imageLike") or []
        print(f"[Probe] Saved bundle: {output_dir}")
        print(f"[Probe] html2canvas patch matched: {bool(patch_status.get('matched'))}")
        print(f"[Probe] html2canvas root probe: {'yes' if probe.get('html2canvasRootProbe') else 'no'}")
        print(f"[Probe] root source: {probe.get('rootSource')}")
        print(f"[Probe] image-like elements: {len(image_like)}")
        print(f"[Probe] Candidates: {probe.get('candidateCount')}")
        print(f"[Probe] frames: {len(probe.get('frameProbes') or [])}")
        for fp in probe.get("frameProbes") or []:
            frame_patch_status = fp.get("patchStatus") or {}
            frame_calls = len(frame_patch_status.get("calls") or [])
            print(
                f"[Probe] frame {fp.get('frameIndex')} "
                f"rootProbe: {'yes' if fp.get('hasRootProbe') else 'no'} "
                f"calls: {frame_calls} "
                f"url: {fp.get('url')}"
            )
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
