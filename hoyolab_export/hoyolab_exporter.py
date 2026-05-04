import asyncio
import re
import subprocess
import time
from pathlib import Path
from typing import Awaitable, Callable, Optional

from PIL import Image
from playwright.async_api import async_playwright, Route, Request, BrowserContext, Page

try:
    from .auth import AuthStatus, find_browser_exe, get_auth_status, mark_profile_clean
except ImportError:
    from auth import AuthStatus, find_browser_exe, get_auth_status, mark_profile_clean


HOYOLAB_URL = "https://act.hoyolab.com/app/community-game-records-sea/index.html"
def wait_for_devtools_port(profile_dir: Path, process: subprocess.Popen, timeout_sec: int = 15) -> int:
    devtools_file = profile_dir / "DevToolsActivePort"
    deadline = time.time() + timeout_sec

    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Browser closed before the CDP port became available.")

        if devtools_file.exists():
            lines = devtools_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            if lines:
                return int(lines[0])

        time.sleep(0.2)

    raise RuntimeError("Timed out waiting for the browser CDP port.")

async def close_export_context(context: BrowserContext) -> None:
    try:
        attached_debug_port = getattr(context, "_attached_debug_port", None)
        if attached_debug_port is None:
            pages = list(context.pages)
            for page in pages:
                try:
                    if not page.is_closed():
                        await page.close()
                except Exception:
                    pass
    finally:
        playwright = getattr(context, "_playwright_instance", None)
        if playwright:
            await playwright.stop()

        process = getattr(context, "_browser_process", None)
        keep_browser_open = bool(getattr(context, "_keep_browser_open", False))
        if process and process.poll() is None and not keep_browser_open:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

        process_profile = getattr(context, "_browser_profile_dir", None)
        if process_profile:
            mark_profile_clean(process_profile)

        await asyncio.sleep(0.2)


class LoginRequiredError(RuntimeError):
    pass


class HoyolabExporter:
    def __init__(
        self,
        profile_dir: str | Path,
        download_dir: str | Path,
        scale: int = 4,
        fixed_container_width: int = 376,
        browser_window_width: int = 1280,
        browser_window_height: int = 900,
        image_format: str = "png",
        remote_debugging_port: int | None = None,
        keep_browser_open: bool = False,
    ):
        self.profile_dir = Path(profile_dir)
        self.download_dir = Path(download_dir)
        self.scale = scale
        self.fixed_container_width = fixed_container_width
        self.browser_window_width = browser_window_width
        self.browser_window_height = browser_window_height
        self.image_format = image_format.lower()
        self.remote_debugging_port = remote_debugging_port
        self.keep_browser_open = keep_browser_open
        self.html2canvas_patch_status = {
            "attempted": False,
            "matched": False,
            "strategy": None,
            "calls": [],
            "errors": [],
            "routeMatches": [],
            "routeMisses": [],
        }

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)

        if self.image_format not in {"png", "jpeg", "jpg"}:
            raise ValueError("image_format must be png or jpeg")

    async def _is_login_open(self, page: Page) -> bool:
        if await page.locator("iframe#hyv-account-frame").count() > 0:
            return True

        for frame in page.frames:
            if "account.hoyolab.com/login-platform" in frame.url:
                return True

        return False

    async def _wait_for_login_if_needed(self, page: Page, timeout_ms: int = 5 * 60_000):
        if not await self._is_login_open(page):
            return

        raise LoginRequiredError(
            "HoYoLAB session is not active. Authorize HoYoLAB from the app, "
            "check that the account is visible on the HoYoLAB page, close the "
            "browser window, and run export again."
        )

    def _has_hoyolab_login_cookie(self) -> bool:
        return get_auth_status(self.profile_dir) == AuthStatus.LOGGED_IN

    async def _block_user_input(self, page: Page):
        await page.evaluate("""
                            () => {
                                if (document.getElementById('__abyss_tracker_blocker__')) return;

                                const blocker = document.createElement('div');
                                blocker.id = '__abyss_tracker_blocker__';
                                blocker.style.position = 'fixed';
                                blocker.style.inset = '0';
                                blocker.style.zIndex = '2147483647';
                                blocker.style.background = 'rgba(0,0,0,0)';
                                blocker.style.cursor = 'wait';
                                blocker.style.pointerEvents = 'auto';

                                document.body.appendChild(blocker);
                                document.body.style.overflow = 'hidden';
                            }
                            """)

    async def _unblock_user_input(self, page: Page):
        await page.evaluate("""
                            () => {
                                const blocker = document.getElementById('__abyss_tracker_blocker__');
                                if (blocker) blocker.remove();
                                document.body.style.overflow = '';
                            }
                            """)

    def _html2canvas_patch_status_init_js(self) -> str:
        return r"""
    (function(){
      const p = window.__genshin_html2canvas_patch_status__;
      window.__genshin_html2canvas_patch_status__ = p || {
        attempted: true,
        matched: false,
        strategy: null,
        calls: [],
        cloneCalls: [],
        errors: []
      };

      const round = (value) => Math.round(Number(value || 0) * 100) / 100;

      const boxOf = (el) => {
        if (!el || !el.getBoundingClientRect) return null;
        const r = el.getBoundingClientRect();
        return {
          x: round(r.x),
          y: round(r.y),
          left: round(r.left),
          top: round(r.top),
          right: round(r.right),
          bottom: round(r.bottom),
          width: round(r.width),
          height: round(r.height)
        };
      };

      const relativeBox = (box, rootRect) => {
        if (!box || !rootRect) return null;
        return {
          left: round(box.left - rootRect.left),
          top: round(box.top - rootRect.top),
          right: round(box.right - rootRect.left),
          bottom: round(box.bottom - rootRect.top),
          width: box.width,
          height: box.height
        };
      };

      const normalizeText = (value, limit) => String(value || "")
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, limit);

      const styleOf = (view, el) => {
        try {
          return view.getComputedStyle(el);
        } catch (_) {
          return window.getComputedStyle(el);
        }
      };

      const visible = (view, el) => {
        if (!el || !el.getBoundingClientRect) return false;
        const rect = el.getBoundingClientRect();
        const style = styleOf(view, el);
        return rect.width > 0
          && rect.height > 0
          && style.display !== "none"
          && style.visibility !== "hidden"
          && Number(style.opacity || 1) > 0;
      };

      const imageInfoOf = (view, img, rootRect, imageIndex) => {
        const rect = boxOf(img);
        return {
          imageIndex,
          src: img.src || "",
          currentSrc: img.currentSrc || "",
          alt: img.alt || "",
          className: String(img.className || ""),
          rect_viewport: rect,
          rect_root_relative: relativeBox(rect, rootRect)
        };
      };

      const parentChainOf = (el) => {
        const chain = [];
        let current = el ? el.parentElement : null;
        while (current && chain.length < 5) {
          chain.push({
            tag: current.tagName || null,
            id: current.id || "",
            className: String(current.className || "").slice(0, 240)
          });
          current = current.parentElement;
        }
        return chain;
      };

      const collectRootDiscovery = (root, view) => {
        const rootRect = boxOf(root);
        const imageLike = [];

        if (!root || !rootRect) {
          return {
            totalElementsInsideRoot: 0,
            imageLike: []
          };
        }

        const inside = Array.from(root.querySelectorAll("*"));

        for (const el of inside) {
          if (!visible(view, el)) continue;

          const style = styleOf(view, el);
          const backgroundImage = style.backgroundImage && style.backgroundImage !== "none"
            ? style.backgroundImage
            : "";

          const images = Array.from(el.querySelectorAll("img")).filter((img) => visible(view, img));
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
            rect_root_relative: relativeBox(rect, rootRect),
            backgroundImage,
            images: el.tagName === "IMG"
              ? [imageInfoOf(view, el, rootRect, 0)]
              : images.map((img, imageIndex) => imageInfoOf(view, img, rootRect, imageIndex)),
            parentChain: parentChainOf(el)
          });

          if (imageLike.length >= 3500) break;
        }

        return {
          totalElementsInsideRoot: inside.length,
          imageLike
        };
      };

      window.__gtt_capture_html2canvas_root__ = function(t, r, strategy) {
        const s = window.__genshin_html2canvas_patch_status__ ||
          (window.__genshin_html2canvas_patch_status__ = {
            attempted: true,
            matched: false,
            strategy: null,
            calls: [],
            cloneCalls: [],
            errors: []
          });

        try {
          if (t && t.setAttribute) {
            t.setAttribute("data-gtt-export-root", "1");
          }

          const rootRect = boxOf(t);

          const probe = {
            capturedAt: "before_html2canvas_runtime_wrapper",
            strategy: strategy || null,
            rootRect,
            rootTag: t && t.tagName ? t.tagName : null,
            rootId: t && typeof t.id === "string" ? t.id : null,
            rootClassName: t && typeof t.className === "string" ? t.className : null,
            rootTextPreview: t && t.innerText ? normalizeText(t.innerText, 300) : "",
            html2canvasOptions: {
              scale: r && r.scale !== undefined ? r.scale : null,
              width: r && r.width !== undefined ? r.width : null,
              height: r && r.height !== undefined ? r.height : null,
              windowWidth: r && r.windowWidth !== undefined ? r.windowWidth : null,
              windowHeight: r && r.windowHeight !== undefined ? r.windowHeight : null
            },
            devicePixelRatio: window.devicePixelRatio,
            scrollX: window.scrollX,
            scrollY: window.scrollY,
            viewport: {
              width: window.innerWidth,
              height: window.innerHeight
            }
          };

          window.__genshin_export_root_probe__ = probe;

          s.calls.push({
            ok: true,
            capturedAt: probe.capturedAt,
            strategy: probe.strategy,
            rootTag: probe.rootTag,
            rootId: probe.rootId,
            rootClassName: probe.rootClassName,
            rootRect: probe.rootRect,
            html2canvasOptions: probe.html2canvasOptions
          });

          s.matched = true;
          s.strategy = strategy || s.strategy || "runtime_wrapper";

          if (r && !r.__gtt_clone_probe_wrapped) {
            const previousOnclone = r.onclone;
            r.__gtt_clone_probe_wrapped = true;

            r.onclone = function(clonedDoc, clonedElement) {
              const captureClone = () => {
                try {
                  const view = clonedDoc && clonedDoc.defaultView ? clonedDoc.defaultView : window;
                  const cloneRoot =
                    clonedElement
                    || (clonedDoc && clonedDoc.querySelector
                      ? clonedDoc.querySelector("[data-gtt-export-root='1']")
                      : null);

                  if (cloneRoot && cloneRoot.setAttribute) {
                    cloneRoot.setAttribute("data-gtt-export-root-clone", "1");
                  }

                  const cloneRootRect = boxOf(cloneRoot);
                  const cloneProbe = {
                    capturedAt: "html2canvas_onclone",
                    strategy: strategy || null,
                    cloneRootRect,
                    rootRect: cloneRootRect,
                    rootTag: cloneRoot && cloneRoot.tagName ? cloneRoot.tagName : null,
                    rootId: cloneRoot && typeof cloneRoot.id === "string" ? cloneRoot.id : null,
                    rootClassName: cloneRoot && typeof cloneRoot.className === "string" ? cloneRoot.className : null,
                    rootTextPreview: cloneRoot && cloneRoot.innerText ? normalizeText(cloneRoot.innerText, 300) : "",
                    html2canvasOptions: {
                      scale: r && r.scale !== undefined ? r.scale : null,
                      width: r && r.width !== undefined ? r.width : null,
                      height: r && r.height !== undefined ? r.height : null,
                      windowWidth: r && r.windowWidth !== undefined ? r.windowWidth : null,
                      windowHeight: r && r.windowHeight !== undefined ? r.windowHeight : null
                    },
                    viewport: {
                      width: view.innerWidth,
                      height: view.innerHeight
                    },
                    rootDiscovery: collectRootDiscovery(cloneRoot, view)
                  };

                  window.__genshin_export_clone_probe__ = cloneProbe;

                  s.cloneCalls.push({
                    ok: true,
                    capturedAt: cloneProbe.capturedAt,
                    strategy: cloneProbe.strategy,
                    rootTag: cloneProbe.rootTag,
                    rootId: cloneProbe.rootId,
                    rootClassName: cloneProbe.rootClassName,
                    cloneRootRect: cloneProbe.cloneRootRect,
                    imageLikeCount: cloneProbe.rootDiscovery.imageLike.length,
                    html2canvasOptions: cloneProbe.html2canvasOptions
                  });
                } catch (e) {
                  const err = {
                    ok: false,
                    capturedAt: Date.now(),
                    strategy: strategy || null,
                    message: String(e && e.message || e),
                    stack: e && e.stack ? String(e.stack).slice(0, 1000) : null
                  };
                  s.cloneCalls.push(err);
                  s.errors.push(err);
                }
              };

              let previousResult;
              try {
                if (typeof previousOnclone === "function") {
                  previousResult = previousOnclone.apply(this, arguments);
                }
              } catch (e) {
                const err = {
                  ok: false,
                  capturedAt: Date.now(),
                  strategy: strategy || null,
                  message: "previous onclone failed: " + String(e && e.message || e),
                  stack: e && e.stack ? String(e.stack).slice(0, 1000) : null
                };
                s.cloneCalls.push(err);
                s.errors.push(err);
              }

              if (previousResult && typeof previousResult.then === "function") {
                return previousResult.then((value) => {
                  captureClone();
                  return value;
                });
              }

              captureClone();
              return previousResult;
            };
          }
        } catch (e) {
          s.calls.push({
            ok: false,
            strategy: strategy || null,
            error: String(e)
          });
          s.errors.push(String(e));
        }
      };
    })();
    """

    def _html2canvas_root_probe_js(self, strategy: str) -> str:
        text_limit = 300
        strategy_json = repr(strategy)
        return (
            "(()=>{"
            "const s=window.__genshin_html2canvas_patch_status__"
            "||(window.__genshin_html2canvas_patch_status__={attempted:true,matched:false,strategy:null,calls:[],errors:[]});"
            "try{"
            "s.matched=true;"
            f"s.strategy={strategy_json};"
            "const root=t;"
            "if(root&&root.setAttribute)root.setAttribute('data-gtt-export-root','1');"
            "const rect=root&&root.getBoundingClientRect?root.getBoundingClientRect():null;"
            "const rootRect=rect?{x:rect.x,y:rect.y,left:rect.left,top:rect.top,right:rect.right,bottom:rect.bottom,width:rect.width,height:rect.height}:null;"
            "const text=(root&&root.innerText?String(root.innerText):'').replace(/\\s+/g,' ').trim().slice(0,"
            f"{text_limit}"
            ");"
            "const probe={"
            "capturedAt:Date.now(),"
            f"strategy:{strategy_json},"
            "rootRect,"
            "rootTag:root&&root.tagName?root.tagName:null,"
            "rootId:root&&root.id?root.id:null,"
            "rootClassName:root&&root.className?String(root.className):null,"
            "rootTextPreview:text,"
            "html2canvasOptions:{"
            "scale:r&&Object.prototype.hasOwnProperty.call(r,'scale')?r.scale:null,"
            "width:r&&Object.prototype.hasOwnProperty.call(r,'width')?r.width:null,"
            "height:r&&Object.prototype.hasOwnProperty.call(r,'height')?r.height:null,"
            "windowWidth:r&&Object.prototype.hasOwnProperty.call(r,'windowWidth')?r.windowWidth:null,"
            "windowHeight:r&&Object.prototype.hasOwnProperty.call(r,'windowHeight')?r.windowHeight:null"
            "},"
            f"fixedContainerWidth:{self.fixed_container_width if self.fixed_container_width is not None else 'null'},"
            "devicePixelRatio:window.devicePixelRatio,"
            "scrollX:window.scrollX,"
            "scrollY:window.scrollY,"
            "viewport:{width:window.innerWidth,height:window.innerHeight}"
            "};"
            "window.__genshin_export_root_probe__=probe;"
            "s.calls.push({ok:true,capturedAt:probe.capturedAt,strategy:probe.strategy,rootTag:probe.rootTag,rootId:probe.rootId,rootClassName:probe.rootClassName,rootRect:probe.rootRect,html2canvasOptions:probe.html2canvasOptions});"
            "}catch(e){"
            "const err={ok:false,capturedAt:Date.now(),strategy:"
            f"{strategy_json}"
            ",message:String(e&&e.message||e),stack:e&&e.stack?String(e.stack).slice(0,1000):null};"
            "s.calls.push(err);s.errors.push(err);"
            "}"
            "})(),"
        )

    async def _patch_js_route(self, route: Route, request: Request):
        url = request.url

        last_exc = None

        for _ in range(2):
            try:
                response = await route.fetch()
                body = await response.text()
                break
            except Exception as exc:
                last_exc = exc
                await asyncio.sleep(0.4)
        else:
            safe_exc = str(last_exc).encode("ascii", errors="replace").decode("ascii")
            print(f"[HoYoLAB Exporter] Could not read JS for patching: {type(last_exc).__name__}: {safe_exc}")

            try:
                await route.continue_()
            except Exception as exc:
                safe_continue_exc = str(exc).encode("ascii", errors="replace").decode("ascii")
                print(
                    "[HoYoLAB Exporter] Could not continue JS route: "
                    f"{type(exc).__name__}: {safe_continue_exc}"
                )

            return

        original_body = body

        body = self._html2canvas_patch_status_init_js() + body

        body = re.sub(r"scale\s*:\s*2", f"scale:{self.scale}", body)
        body = re.sub(
            r"r=\{useCORS:!0,backgroundColor:null,scale:(\d+)\}",
            f"r={{useCORS:!0,backgroundColor:null,scale:\\1,width:{self.fixed_container_width},windowWidth:{self.fixed_container_width}}}",
            body,
        )
        html2canvas_strategy = "all_f_t_r_calls_runtime_wrapper"
        html2canvas_target = "f()(t,r)"
        html2canvas_match_count = body.count(html2canvas_target)
        html2canvas_matched = html2canvas_match_count > 0

        self.html2canvas_patch_status["attempted"] = True

        if html2canvas_matched:
            self.html2canvas_patch_status["matched"] = True
            self.html2canvas_patch_status["strategy"] = html2canvas_strategy
            self.html2canvas_patch_status["routeMatches"].append(url)
            self.html2canvas_patch_status["matchCount"] = html2canvas_match_count

            body = body.replace(
                html2canvas_target,
                (
                    "(window.__gtt_capture_html2canvas_root__&&"
                    f"window.__gtt_capture_html2canvas_root__(t,r,{html2canvas_strategy!r}),"
                    "f()(t,r))"
                ),
            )
        else:
            self.html2canvas_patch_status["routeMisses"].append(url)
            self.html2canvas_patch_status["errors"].append(
                f"html2canvas runtime wrapper did not find {html2canvas_target!r} in route: {url}"
            )
            print(f"[HoYoLAB Exporter] html2canvas runtime wrapper did not match: {url}")

        if html2canvas_matched:
            print(
                "[HoYoLAB Exporter] html2canvas runtime wrapper matched "
                f"({html2canvas_strategy}, count={html2canvas_match_count}): {url}"
            )
        else:
            print(f"[HoYoLAB Exporter] JS patched without html2canvas runtime wrapper match: {url}")

        headers = dict(response.headers)
        headers["content-type"] = "application/javascript"

        await route.fulfill(
            status=response.status,
            headers=headers,
            body=body,
        )

    async def _wait_until_ready_or_login(self, page: Page, timeout_ms: int = 5 * 60_000):
        deadline = time.time() + timeout_ms / 1000

        while time.time() < deadline:
            if await self._is_login_open(page):
                await self._wait_for_login_if_needed(page, timeout_ms=timeout_ms)

            if await page.locator(".block-title-right").count() > 0:
                try:
                    if await page.locator(".block-title-right").first.is_visible(timeout=500):
                        return
                except Exception:
                    pass

            await page.wait_for_timeout(500)

        raise RuntimeError("HoYoLAB page did not become ready: login window and character button were not found.")

    async def _js_click(self, page: Page, selector: str, timeout: int = 30_000):
        locator = page.locator(selector).first
        await locator.wait_for(state="visible", timeout=timeout)
        await locator.evaluate("(el) => el.click()")

    async def _dismiss_known_popups(self, page: Page, *, press_escape: bool = True) -> bool:
        dismissed = False

        for _ in range(5):
            clicked = await page.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        const style = getComputedStyle(el);
                        return rect.width > 0
                            && rect.height > 0
                            && style.display !== "none"
                            && style.visibility !== "hidden"
                            && Number(style.opacity || 1) > 0;
                    };
                    const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                    const textPattern = /^(ok|got it|confirm|close|continue|skip|later|not now|i know|i got it|accept|agree|cancel|知道了|我知道了|确定|确认|关闭|跳过|稍后|取消|继续|同意|好的|Понятно|ОК|Ок|Закрыть|Продолжить|Позже|Отмена)$/i;
                    const popupClassPattern = /(dialog|modal|popup|guide|update|notice|toast|mask|overlay)/i;
                    const closeIconPattern = /(close|cancel|cross|delete)/i;
                    const hasPopupAncestor = (el) => {
                        let current = el;
                        while (current && current !== document.body) {
                            const className = normalize(current.className);
                            const role = normalize(current.getAttribute("role"));
                            if (popupClassPattern.test(className) || role === "dialog" || role === "alertdialog") {
                                return true;
                            }
                            current = current.parentElement;
                        }
                        return false;
                    };

                    const candidates = Array.from(document.querySelectorAll([
                        "button",
                        "[role='button']",
                        "[aria-label*='close' i]",
                        "[aria-label*='закры' i]",
                        "[class*='close' i]",
                        "[class*='cancel' i]",
                        "[class*='dialog' i] button",
                        "[class*='modal' i] button",
                        "[class*='popup' i] button",
                        "[class*='guide' i] button",
                        "[class*='update' i] button",
                        "[class*='notice' i] button"
                    ].join(",")));

                    for (const el of candidates) {
                        if (!visible(el)) continue;

                        const text = normalize(el.innerText || el.textContent);
                        const className = normalize(el.className);
                        const aria = normalize(el.getAttribute("aria-label"));
                        const title = normalize(el.getAttribute("title"));
                        const popupAncestor = hasPopupAncestor(el);
                        const closeLike = closeIconPattern.test(className)
                            || closeIconPattern.test(aria)
                            || closeIconPattern.test(title);

                        if (
                            closeLike
                            || (popupAncestor && textPattern.test(text))
                        ) {
                            el.click();
                            return { clicked: true, text, className, aria, title };
                        }
                    }

                    return { clicked: false };
                }
                """
            )

            if not clicked.get("clicked"):
                break

            dismissed = True
            label = clicked.get("text") or clicked.get("aria") or clicked.get("title") or clicked.get("className")
            print(f"[HoYoLAB Exporter] Dismissed popup: {label}")
            await page.wait_for_timeout(400)

        if press_escape:
            try:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(200)
            except Exception:
                pass

        return dismissed

    async def _click_with_popup_retry(self, page: Page, selector: str, *, timeout: int = 30_000):
        last_error: Exception | None = None

        for attempt in range(3):
            await self._dismiss_known_popups(page, press_escape=False)
            try:
                await self._js_click(page, selector, timeout=timeout)
                return
            except Exception as exc:
                last_error = exc
                print(f"[HoYoLAB Exporter] Click retry {attempt + 1} failed for {selector}: {exc}")
                await self._dismiss_known_popups(page, press_escape=True)
                await page.wait_for_timeout(800)

        if last_error is not None:
            raise last_error

    async def _debug_visible_blockers(self, page: Page):
        blockers = await page.evaluate(
            """
            () => {
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    return rect.width > 0
                        && rect.height > 0
                        && style.display !== "none"
                        && style.visibility !== "hidden"
                        && Number(style.opacity || 1) > 0;
                };
                return Array.from(document.querySelectorAll("body *"))
                    .filter(visible)
                    .map((el) => {
                        const rect = el.getBoundingClientRect();
                        const style = getComputedStyle(el);
                        return {
                            tag: el.tagName,
                            className: String(el.className || "").slice(0, 160),
                            text: String(el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim().slice(0, 160),
                            zIndex: style.zIndex,
                            position: style.position,
                            box: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
                        };
                    })
                    .filter((item) => {
                        const z = Number(item.zIndex);
                        return item.position === "fixed"
                            || item.position === "absolute"
                            || (!Number.isNaN(z) && z >= 100);
                    })
                    .slice(-12);
            }
            """
        )
        print(f"[HoYoLAB Exporter] Visible blockers debug: {blockers}")

    async def _run_export_flow(
            self,
            page: Page,
            after_character_list_open: Optional[Callable[[], Awaitable[None]]] = None,
    ):
        await page.wait_for_load_state("domcontentloaded")
        await self._dismiss_known_popups(page)
        await self._wait_until_ready_or_login(page)

        await self._block_user_input(page)

        try:
            await self._click_with_popup_retry(page, ".block-title-right")
            await page.wait_for_timeout(2500)

            if after_character_list_open is not None:
                await after_character_list_open()

            await self._click_with_popup_retry(page, ".me-share__btn")
            await page.wait_for_timeout(2500)

            async with page.expect_download(timeout=90_000) as download_info:
                try:
                    await self._click_with_popup_retry(
                        page,
                        '.me-share-popover__item:has(img[src*="35b0742f6ed3b58d65f1491ca1bf94e2"])',
                        timeout=30_000,
                    )
                except Exception:
                    await self._debug_visible_blockers(page)
                    raise

            return await download_info.value

        finally:
            await self._unblock_user_input(page)

    async def _prepare_export_page(self, page: Page):
        # Export tab only: patch html2canvas scale and width.
        await page.route("**/*role_combat_tarot*.js", self._patch_js_route)



    async def _create_context(self) -> BrowserContext:
        playwright = await async_playwright().start()

        browser_exe = find_browser_exe()
        fixed_port = self.remote_debugging_port

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        mark_profile_clean(self.profile_dir)
        devtools_file = self.profile_dir / "DevToolsActivePort"
        if devtools_file.exists():
            try:
                devtools_file.unlink()
            except OSError:
                pass

        if fixed_port is not None:
            try:
                browser = await playwright.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{fixed_port}",
                    timeout=3000,
                )
                context = browser.contexts[0]
                context._playwright_instance = playwright  # type: ignore[attr-defined]
                context._attached_debug_port = fixed_port  # type: ignore[attr-defined]
                return context
            except Exception:
                pass

        process = subprocess.Popen([
            browser_exe,
            f"--remote-debugging-port={fixed_port or 0}",
            f"--user-data-dir={self.profile_dir}",
            f"--window-size={self.browser_window_width},{self.browser_window_height}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-session-crashed-bubble",
            "about:blank",
        ])

        debug_port = fixed_port or wait_for_devtools_port(self.profile_dir, process)

        browser = await playwright.chromium.connect_over_cdp(
            f"http://127.0.0.1:{debug_port}"
        )

        context = browser.contexts[0]

        context._playwright_instance = playwright  # type: ignore[attr-defined]
        context._browser_process = process  # type: ignore[attr-defined]
        context._browser_profile_dir = self.profile_dir  # type: ignore[attr-defined]
        context._keep_browser_open = self.keep_browser_open  # type: ignore[attr-defined]
        return context

    async def export_manual(self) -> Optional[Path]:
        if get_auth_status(self.profile_dir) != AuthStatus.LOGGED_IN:
            raise LoginRequiredError(
                "HoYoLAB profile is not ready. Authorize in the app first, "
                "then close the browser window and run export again."
            )

        context: BrowserContext | None = await self._create_context()

        try:
            export_page = context.pages[0] if context.pages else await context.new_page()

            await self._prepare_export_page(export_page)
            await export_page.goto(HOYOLAB_URL, wait_until="domcontentloaded", timeout=60_000)

            print()
            print("Page opened. Starting automatic export...")
            print()

            download = await self._run_export_flow(export_page)

            suggested_name = download.suggested_filename or "hoyolab_export"

            if self.image_format == "png" and not suggested_name.lower().endswith(".png"):
                suggested_name = Path(suggested_name).stem + ".png"

            save_path = self.download_dir / suggested_name
            await download.save_as(str(save_path))

            print(f"[HoYoLAB Exporter] File saved: {save_path}")

            self._validate_image(save_path)

            return save_path

        except LoginRequiredError as exc:
            print(f"[HoYoLAB Exporter] {exc}")
            raise

        except Exception as exc:
            print(f"[HoYoLAB Exporter] Export error: {exc}")
            raise



        finally:

            if context is not None:
                await close_export_context(context)

    def _validate_image(self, path: Path):
        try:
            with Image.open(path) as img:
                width, height = img.size
                print(f"[HoYoLAB Exporter] Image size: {width} x {height}")

                expected_width = self.fixed_container_width * self.scale
                if width < expected_width * 0.9:
                    print(
                        "[HoYoLAB Exporter] Warning: "
                        f"image width {width}px is below expected {expected_width}px. "
                        "Scale or fixed_container_width may not have applied."
                    )

        except Exception as exc:
            print(f"[HoYoLAB Exporter] Could not validate image: {exc}")

