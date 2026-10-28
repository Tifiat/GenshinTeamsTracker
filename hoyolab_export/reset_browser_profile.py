from pathlib import Path

try:
    from .auth import reset_profile
except ImportError:
    from auth import reset_profile


BASE_DIR = Path(__file__).resolve().parent
PROFILE_DIR = BASE_DIR / "profile"


def main() -> None:
    removed = reset_profile(PROFILE_DIR, BASE_DIR)
    if not removed:
        print(f"[HoYoLAB Profile Reset] Profile does not exist: {PROFILE_DIR}")
        return
    print(f"[HoYoLAB Profile Reset] Removed browser profile: {PROFILE_DIR.resolve()}")
    print("[HoYoLAB Profile Reset] Next login setup will behave like a fresh user profile.")


if __name__ == "__main__":
    main()
