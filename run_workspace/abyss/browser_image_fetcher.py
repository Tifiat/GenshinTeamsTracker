"""Optional public-image fetch through an ordinary browser context.

This is a bounded fallback for image URLs already present in source data. It
can use a caller-owned context or a fresh transient browser. It never opens
the account browser profile or transfers browser session state.
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

from PIL import Image
from playwright.async_api import BrowserContext, async_playwright

from hoyolab_export.auth import find_browser_exe


MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_CONCURRENCY = 2


class BrowserImageFetchError(RuntimeError):
    """An isolated browser could not be started or used."""


@dataclass(slots=True)
class BrowserImageFetchResult:
    images: dict[str, bytes] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    period_error: str | None = None


def fetch_public_fandom_images(
    image_urls: list[str] | tuple[str, ...],
    *,
    period_url: str | None = None,
    max_concurrency: int = MAX_CONCURRENCY,
    individual_timeout_s: float = 15.0,
    total_timeout_s: float = 60.0,
) -> BrowserImageFetchResult:
    """Fetch exact Fandom image URLs from a transient headed browser.

    A challenge is reported for the affected URL; the caller may keep source
    data and retry later. This synchronous entry point must run outside an
    already-running event loop, such as in the importer's worker thread.
    """

    _validate_limits(max_concurrency, individual_timeout_s, total_timeout_s)
    return asyncio.run(
        _fetch_public_fandom_images(
            image_urls,
            period_url=period_url,
            max_concurrency=max_concurrency,
            individual_timeout_s=individual_timeout_s,
            total_timeout_s=total_timeout_s,
        )
    )


async def fetch_public_fandom_images_in_context(
    context: BrowserContext,
    image_urls: list[str] | tuple[str, ...],
    *,
    period_url: str | None = None,
    max_concurrency: int = MAX_CONCURRENCY,
    individual_timeout_s: float = 15.0,
    total_timeout_s: float = 60.0,
) -> BrowserImageFetchResult:
    """Use a caller-owned context on its existing event loop.

    Only pages opened by this helper are closed. The context and its browser
    remain the caller's responsibility, including when a timeout occurs.
    """

    _validate_limits(max_concurrency, individual_timeout_s, total_timeout_s)
    result, valid_urls = _prepare_urls(image_urls, period_url)
    if not valid_urls:
        return result
    try:
        await asyncio.wait_for(
            _fetch_with_context(
                context, result, valid_urls, period_url=period_url,
                max_concurrency=max_concurrency,
                individual_timeout_s=individual_timeout_s,
            ),
            timeout=total_timeout_s,
        )
    except asyncio.TimeoutError:
        _mark_batch_timeout(result, valid_urls)
    return result


async def _fetch_public_fandom_images(
    image_urls: list[str] | tuple[str, ...],
    *,
    period_url: str | None,
    max_concurrency: int,
    individual_timeout_s: float,
    total_timeout_s: float,
) -> BrowserImageFetchResult:
    result, valid_urls = _prepare_urls(image_urls, period_url)
    if not valid_urls:
        return result

    try:
        browser_exe = find_browser_exe()
    except FileNotFoundError as exc:
        raise BrowserImageFetchError("Chrome or Edge executable was not found") from exc
    if not Path(browser_exe).is_file():
        raise BrowserImageFetchError("Discovered browser executable does not exist")

    async def run_batch() -> None:
        playwright = None
        browser = None
        context = None
        try:
            playwright = await async_playwright().start()
            try:
                browser = await playwright.chromium.launch(
                    executable_path=browser_exe,
                    headless=False,
                    timeout=int(min(individual_timeout_s, total_timeout_s) * 1000),
                )
                context = await browser.new_context()
            except Exception as exc:
                raise BrowserImageFetchError(f"Isolated browser launch failed: {type(exc).__name__}") from exc
            await _fetch_with_context(
                context, result, valid_urls, period_url=period_url,
                max_concurrency=max_concurrency,
                individual_timeout_s=individual_timeout_s,
            )
        finally:
            if context is not None:
                await _close_quietly(context)
            if browser is not None:
                await _close_quietly(browser)
            if playwright is not None:
                await _close_quietly(playwright, method="stop")

    try:
        await asyncio.wait_for(run_batch(), timeout=total_timeout_s)
    except asyncio.TimeoutError:
        _mark_batch_timeout(result, valid_urls)
    return result


def _validate_limits(max_concurrency: int, individual_timeout_s: float, total_timeout_s: float) -> None:
    if not isinstance(max_concurrency, int) or max_concurrency < 1 or max_concurrency > MAX_CONCURRENCY:
        raise ValueError(f"max_concurrency must be between 1 and {MAX_CONCURRENCY}")
    if individual_timeout_s <= 0 or total_timeout_s <= 0:
        raise ValueError("Browser image timeouts must be positive")


def _prepare_urls(
    image_urls: list[str] | tuple[str, ...], period_url: str | None,
) -> tuple[BrowserImageFetchResult, list[str]]:
    result = BrowserImageFetchResult()
    urls = list(dict.fromkeys(image_urls))
    valid_urls = []
    for url in urls:
        if not _is_supported_image_url(url):
            result.errors[url] = "unsupported_image_url"
        else:
            valid_urls.append(url)
    if period_url is not None and not _is_supported_period_url(period_url):
        raise ValueError("period_url must be a Genshin Impact Fandom period HTTPS page")
    return result, valid_urls


def _is_supported_image_url(url: str) -> bool:
    return _is_public_url(url, "static.wikia.nocookie.net", "/gensin-impact/images/")


def _is_supported_period_url(url: str) -> bool:
    return _is_public_url(
        url, "genshin-impact.fandom.com", "/wiki/Spiral_Abyss/Floors",
        allow_exact_prefix=True,
    )


def _is_public_url(
    url: str, hostname: str, path_prefix: str, *, allow_exact_prefix: bool = False,
) -> bool:
    try:
        parsed = urlparse(url)
        path = unquote(parsed.path)
        segments = path.split("/")
        return (
            parsed.scheme == "https"
            and parsed.hostname == hostname
            and parsed.username is None
            and parsed.password is None
            and parsed.port is None
            and (
                (allow_exact_prefix and path == path_prefix)
                or (path.startswith(path_prefix) and len(path) > len(path_prefix)
                    and (path_prefix.endswith("/") or path[len(path_prefix)] == "/"))
            )
            and not any(segment in {".", ".."} for segment in segments)
            and "\\" not in path
        )
    except (TypeError, ValueError):
        return False


async def _fetch_with_context(
    context: BrowserContext,
    result: BrowserImageFetchResult,
    valid_urls: list[str],
    *,
    period_url: str | None,
    max_concurrency: int,
    individual_timeout_s: float,
) -> None:
    if period_url is not None:
        page = await context.new_page()
        try:
            async def visit_period() -> str | None:
                response = await page.goto(
                    period_url, wait_until="domcontentloaded",
                    timeout=int(individual_timeout_s * 1000),
                )
                return await _response_error(response, prefix="period_", period=True)

            error = await asyncio.wait_for(visit_period(), timeout=individual_timeout_s)
        except Exception as exc:
            error = "period_navigation_timeout" if isinstance(exc, asyncio.TimeoutError) else "period_navigation_failed"
        finally:
            await _close_quietly(page)
        if error:
            # A period-page refusal applies to that page alone. Exact
            # public image URLs may still be visited independently.
            result.period_error = error

    semaphore = asyncio.Semaphore(max_concurrency)

    async def fetch_one(url: str) -> None:
        async with semaphore:
            page = None
            try:
                async def load_image() -> None:
                    nonlocal page
                    page = await context.new_page()
                    response = await page.goto(
                        url, wait_until="commit",
                        timeout=int(individual_timeout_s * 1000),
                    )
                    error = await _response_error(response)
                    if error:
                        result.errors[url] = error
                        return
                    body = await response.body()
                    if len(body) > MAX_IMAGE_BYTES:
                        result.errors[url] = "image_too_large"
                        return
                    try:
                        with Image.open(io.BytesIO(body)) as image:
                            image.verify()
                    except (OSError, ValueError):
                        result.errors[url] = "invalid_image"
                        return
                    result.images[url] = body

                await asyncio.wait_for(load_image(), timeout=individual_timeout_s)
            except asyncio.TimeoutError:
                result.errors[url] = "navigation_timeout"
            except Exception as exc:
                result.errors[url] = f"navigation_failed:{type(exc).__name__}"
            finally:
                if page is not None:
                    await _close_quietly(page)

    await asyncio.gather(*(fetch_one(url) for url in valid_urls))


def _mark_batch_timeout(result: BrowserImageFetchResult, valid_urls: list[str]) -> None:
    for url in valid_urls:
        if url not in result.images and url not in result.errors:
            result.errors[url] = "batch_timeout"


async def _response_error(response, *, prefix: str = "", period: bool = False) -> str | None:
    if response is None:
        return f"{prefix}no_response"
    headers = await response.all_headers()
    if str(headers.get("cf-mitigated", "")).casefold() == "challenge":
        return f"{prefix}browser_verification_required"
    allowed = _is_supported_period_url if period else _is_supported_image_url
    if not allowed(response.url):
        return f"{prefix}redirected_to_unsupported_url"
    if not 200 <= int(response.status) < 300:
        return f"{prefix}http_{response.status}"
    return None


async def _close_quietly(resource, *, method: str = "close") -> None:
    try:
        await asyncio.wait_for(getattr(resource, method)(), timeout=5.0)
    except Exception:
        # The caller receives per-URL failure, and each enclosing owner still
        # attempts to close its own browser resource.
        pass
