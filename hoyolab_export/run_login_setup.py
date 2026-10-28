import time
from pathlib import Path

try:
    from .auth import open_login_browser
except ImportError:
    from auth import open_login_browser


BASE_DIR = Path(__file__).resolve().parent


def main() -> None:
    process = open_login_browser(BASE_DIR / "profile", width=1280, height=900)
    print("[HoYoLAB Login] Browser opened.")
    print("[HoYoLAB Login] Authorize HoYoLAB, then close the browser window.")
    while process.poll() is None:
        time.sleep(1)
    print("[HoYoLAB Login] Browser closed.")


if __name__ == "__main__":
    main()
