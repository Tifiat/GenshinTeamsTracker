import asyncio
import time
from pathlib import Path

try:
    from .auth import AuthStatus, get_auth_status, open_login_browser
    from .hoyolab_exporter import HoyolabExporter
except ImportError:
    from auth import AuthStatus, get_auth_status, open_login_browser
    from hoyolab_exporter import HoyolabExporter


BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "profile"
DOWNLOAD_DIR = BASE_DIR / "downloads"


def ensure_authorized() -> bool:
    if get_auth_status(PROFILE_DIR) == AuthStatus.LOGGED_IN:
        return True

    process = open_login_browser(PROFILE_DIR, width=1280, height=900)
    print("[HoYoLAB Manual Export] Browser opened.")
    print("[HoYoLAB Manual Export] Authorize HoYoLAB, then close the browser window.")

    while process.poll() is None:
        time.sleep(1)

    if get_auth_status(PROFILE_DIR) == AuthStatus.LOGGED_IN:
        return True

    print("[HoYoLAB Manual Export] HoYoLAB authorization was not detected. Export cancelled.")
    return False


async def main() -> None:
    if not ensure_authorized():
        return

    exporter = HoyolabExporter(
        profile_dir=PROFILE_DIR,
        download_dir=DOWNLOAD_DIR,
        # Final width is approximately fixed_container_width * scale.
        # Example: 500 * 4 = 2000 px.
        scale=4,
        fixed_container_width=500,
        browser_window_width=1280,
        browser_window_height=900,
        image_format="png",
    )
    await exporter.export_manual()


if __name__ == "__main__":
    asyncio.run(main())
