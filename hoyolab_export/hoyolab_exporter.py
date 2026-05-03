import asyncio
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

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

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)

        if self.image_format not in {"png", "jpeg", "jpg"}:
            raise ValueError("image_format must be png or jpeg")

    async def _patch_api_language_route(self, route: Route, request: Request):
        url = request.url

        # JS files are handled by the export-page patch route.
        if url.endswith(".js"):
            await route.continue_()
            return

        headers = dict(request.headers)
        headers["accept-language"] = "zh-CN,zh;q=0.9,en;q=0.8"
        headers["x-rpc-language"] = "zh-cn"

        await route.continue_(headers=headers)

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

    async def _patch_js_route(self, route: Route, request: Request):
        url = request.url

        try:
            response = await route.fetch()
            body = await response.text()
        except Exception as exc:
            print(f"[HoYoLAB Exporter] Could not read JS for patching: {exc}")
            await route.continue_()
            return

        original_body = body

        body = re.sub(r"scale\s*:\s*2", f"scale:{self.scale}", body)
        body = re.sub(
            r"r=\{useCORS:!0,backgroundColor:null,scale:(\d+)\}",
            f"r={{useCORS:!0,backgroundColor:null,scale:\\1,width:{self.fixed_container_width},windowWidth:{self.fixed_container_width}}}",
            body,
        )
        body = body.replace(
            ",n.next=5,f()(t,r);case 5:",
            (
                ",t&&t.style&&(t.style.setProperty('width','"
                f"{self.fixed_container_width}px','important'),"
                "t.style.setProperty('min-width','"
                f"{self.fixed_container_width}px','important'),"
                "t.style.setProperty('max-width','"
                f"{self.fixed_container_width}px','important')),"
                "t&&t.getBoundingClientRect&&(window.__genshin_export_root_probe__={"
                "capturedAt:Date.now(),"
                "scale:"
                f"{self.scale},"
                "fixedContainerWidth:"
                f"{self.fixed_container_width},"
                "devicePixelRatio:window.devicePixelRatio,"
                "scrollX:window.scrollX,"
                "scrollY:window.scrollY,"
                "viewport:{width:window.innerWidth,height:window.innerHeight},"
                "rootRect:(()=>{const e=t.getBoundingClientRect();return{x:e.x,y:e.y,left:e.left,top:e.top,right:e.right,bottom:e.bottom,width:e.width,height:e.height}})()"
                "}),"
                "n.next=5,f()(t,r);case 5:"
            ),
        )

        if self.image_format == "png":
            body = body.replace('toDataURL("image/jpeg")', 'toDataURL("image/png")')
            body = body.replace("toDataURL('image/jpeg')", "toDataURL('image/png')")

        if original_body != body:
            print(f"[HoYoLAB Exporter] JS patched: {url}")
        else:
            print(f"[HoYoLAB Exporter] JS found, but no target strings were replaced: {url}")

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

    async def _run_export_flow(self, page: Page):
        await page.wait_for_load_state("domcontentloaded")
        await self._dismiss_known_popups(page)
        await self._wait_until_ready_or_login(page)

        await self._block_user_input(page)

        try:
            await self._click_with_popup_retry(page, ".block-title-right")
            await page.wait_for_timeout(2500)

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

        # Export tab only: force API language headers.
        await page.route("**/game_record/**", self._patch_api_language_route)
        await page.route("**/event/game_record/**", self._patch_api_language_route)

        # Headers for this export page only.
        await page.set_extra_http_headers({
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "x-rpc-language": "zh-cn",
        })



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

