import json
import shutil
import sqlite3
import subprocess
from enum import StrEnum
from pathlib import Path


HOYOLAB_URL = "https://act.hoyolab.com/app/community-game-records-sea/index.html"
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
EDGE_PATHS = [
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]
AUTH_COOKIE_DOMAINS = (
    "hoyolab.com",
    "hoyoverse.com",
    "mihoyo.com",
)
SESSION_COOKIE_NAMES = {
    "cookie_token",
    "cookie_token_v2",
    "ltoken",
    "ltoken_v2",
}
ACCOUNT_COOKIE_NAMES = {
    "account_id",
    "account_id_v2",
    "ltuid",
    "ltuid_v2",
}

class AuthStatus(StrEnum):
    LOGGED_IN = "logged_in"
    NOT_LOGGED_IN = "not_logged_in"
    PROFILE_LOCKED = "profile_locked"


def find_browser_exe() -> str:
    for path in CHROME_PATHS:
        if Path(path).exists():
            return path

    for path in EDGE_PATHS:
        if Path(path).exists():
            return path

    raise FileNotFoundError(
        "Google Chrome or Microsoft Edge was not found. "
        "Install one of these browsers."
    )


def mark_profile_clean(profile_dir: str | Path) -> None:
    profile_dir = Path(profile_dir)
    for prefs_path in (profile_dir / "Default" / "Preferences", profile_dir / "Local State"):
        if not prefs_path.exists():
            continue

        try:
            data = json.loads(prefs_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if prefs_path.name == "Preferences":
            data.setdefault("profile", {})["exit_type"] = "Normal"
            data.setdefault("profile", {})["exited_cleanly"] = True
        data.setdefault("session", {})["exited_cleanly"] = True

        try:
            prefs_path.write_text(
                json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
        except Exception:
            pass


def open_login_browser(
    profile_dir: str | Path,
    width: int = 1280,
    height: int = 900,
) -> subprocess.Popen:
    profile_dir = Path(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    mark_profile_clean(profile_dir)
    browser_exe = find_browser_exe()

    return subprocess.Popen([
        browser_exe,
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--disable-features=InfiniteSessionRestore",
        f"--window-size={width},{height}",
        HOYOLAB_URL,
    ])


def get_auth_status(profile_dir: str | Path) -> AuthStatus:
    profile_marker = Path(profile_dir) / "Default" / "Network" / "Cookies"
    try:
        if not profile_marker.exists() or profile_marker.stat().st_size == 0:
            return AuthStatus.NOT_LOGGED_IN
    except OSError:
        return AuthStatus.PROFILE_LOCKED

    cookie_names = SESSION_COOKIE_NAMES | ACCOUNT_COOKIE_NAMES
    placeholders = ",".join("?" for _ in cookie_names)
    query = (
        "select host_key, name from cookies "
        f"where name in ({placeholders})"
    )

    try:
        connection = sqlite3.connect(
            f"file:{profile_marker.as_posix()}?mode=ro",
            uri=True,
            timeout=1,
        )
        try:
            rows = connection.execute(query, tuple(cookie_names)).fetchall()
        finally:
            connection.close()
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower():
            return AuthStatus.PROFILE_LOCKED
        return AuthStatus.NOT_LOGGED_IN
    except OSError:
        return AuthStatus.PROFILE_LOCKED

    matched_names = {
        name
        for host_key, name in rows
        if any(domain in (host_key or "") for domain in AUTH_COOKIE_DOMAINS)
    }
    if matched_names & SESSION_COOKIE_NAMES and matched_names & ACCOUNT_COOKIE_NAMES:
        return AuthStatus.LOGGED_IN

    return AuthStatus.NOT_LOGGED_IN


def reset_profile(profile_dir: str | Path, expected_parent: str | Path) -> bool:
    profile_dir = Path(profile_dir)
    if not profile_dir.exists():
        return False

    resolved_profile = profile_dir.resolve()
    resolved_parent = Path(expected_parent).resolve()
    if resolved_profile.parent != resolved_parent or resolved_profile.name != "profile":
        raise RuntimeError(f"Refusing to remove unexpected path: {resolved_profile}")

    shutil.rmtree(resolved_profile)
    return True
