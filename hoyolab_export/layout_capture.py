import time
from typing import Any

from playwright.async_api import Page

from .hoyolab_exporter import HoyolabExporter


async def _read_frame_layout(frame, exporter: HoyolabExporter) -> dict[str, Any]:
    return await frame.evaluate(
        """
        (routeStatus) => {
            const cloneProbe = window.__genshin_export_clone_probe__ || null;
            const rootProbe = window.__genshin_export_root_probe__ || null;
            const currentStatus = window.__genshin_html2canvas_patch_status__ || {};

            const patchStatus = {
                ...routeStatus,
                ...currentStatus,
                attempted: Boolean(routeStatus.attempted || currentStatus.attempted),
                matched: Boolean(routeStatus.matched || currentStatus.matched),
                strategy: currentStatus.strategy || routeStatus.strategy || null,
                calls: [
                    ...(Array.isArray(routeStatus.calls) ? routeStatus.calls : []),
                    ...(Array.isArray(currentStatus.calls) ? currentStatus.calls : []),
                ],
                cloneCalls: [
                    ...(Array.isArray(routeStatus.cloneCalls) ? routeStatus.cloneCalls : []),
                    ...(Array.isArray(currentStatus.cloneCalls) ? currentStatus.cloneCalls : []),
                ],
                errors: [
                    ...(Array.isArray(routeStatus.errors) ? routeStatus.errors : []),
                    ...(Array.isArray(currentStatus.errors) ? currentStatus.errors : []),
                ],
                routeMatches: routeStatus.routeMatches || currentStatus.routeMatches || [],
                routeMisses: routeStatus.routeMisses || currentStatus.routeMisses || [],
            };

            return {
                sourceUrl: window.location.href,
                capturedAt: Date.now(),
                exporter: {
                    scale: null,
                    fixedContainerWidth: null,
                    expectedImageWidth: null,
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
                rootSource: cloneProbe ? "html2canvas_clone" : (rootProbe ? "html2canvas_root" : "none"),
                rootDiscovery: cloneProbe && cloneProbe.rootDiscovery
                    ? cloneProbe.rootDiscovery
                    : {
                        totalElementsInsideRoot: 0,
                        imageLike: [],
                    },
            };
        }
        """,
        exporter.html2canvas_patch_status,
    )


async def collect_layout(page: Page, exporter: HoyolabExporter) -> dict[str, Any]:
    """Collect HoYoLAB export layout metadata from the frame that has html2canvas probe data."""

    best_layout: dict[str, Any] | None = None
    frame_checks = []

    for frame_index, frame in enumerate(page.frames):
        try:
            layout = await _read_frame_layout(frame, exporter)
            image_like_count = len((layout.get("rootDiscovery") or {}).get("imageLike") or [])

            frame_checks.append(
                {
                    "frameIndex": frame_index,
                    "url": frame.url,
                    "rootSource": layout.get("rootSource"),
                    "imageLikeCount": image_like_count,
                    "hasCloneProbe": bool(layout.get("html2canvasCloneProbe")),
                    "hasRootProbe": bool(layout.get("html2canvasRootProbe")),
                }
            )

            if best_layout is None:
                best_layout = layout
            else:
                best_count = len((best_layout.get("rootDiscovery") or {}).get("imageLike") or [])
                if image_like_count > best_count:
                    best_layout = layout

        except Exception as exc:
            frame_checks.append(
                {
                    "frameIndex": frame_index,
                    "url": frame.url,
                    "error": str(exc),
                }
            )

    if best_layout is None:
        best_layout = {
            "sourceUrl": page.url,
            "capturedAt": int(time.time() * 1000),
            "html2canvasPatchStatus": {
                "attempted": False,
                "matched": False,
                "strategy": None,
                "calls": [],
                "cloneCalls": [],
                "errors": ["No readable frame layout was found"],
            },
            "html2canvasRootProbe": None,
            "html2canvasCloneProbe": None,
            "rootSource": "none",
            "rootDiscovery": {
                "totalElementsInsideRoot": 0,
                "imageLike": [],
            },
        }

    best_layout["exporter"] = {
        "scale": exporter.scale,
        "fixedContainerWidth": exporter.fixed_container_width,
        "expectedImageWidth": exporter.scale * exporter.fixed_container_width,
    }
    best_layout["frameChecks"] = frame_checks
    best_layout["selectedFrameUrl"] = best_layout.get("sourceUrl") or page.url

    return best_layout