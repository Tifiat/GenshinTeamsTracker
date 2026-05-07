import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

HOYOLAB_EXPORT_DIR = PROJECT_ROOT / "hoyolab_export"
HOYOLAB_PROFILE_DIR = HOYOLAB_EXPORT_DIR / "profile"

HOYOLAB_DATA_DIR = PROJECT_ROOT / "data" / "hoyolab"
HOYOLAB_ASSETS_DIR = PROJECT_ROOT / "assets" / "hoyolab"
HOYOLAB_CHARACTER_ASSETS_DIR = HOYOLAB_ASSETS_DIR / "characters"
HOYOLAB_WEAPON_ASSETS_DIR = HOYOLAB_ASSETS_DIR / "weapons"
HOYOLAB_ARTIFACT_ASSETS_DIR = HOYOLAB_ASSETS_DIR / "artifacts"
HOYOLAB_DEBUG_DIR = PROJECT_ROOT / "debug" / "hoyolab"


def ensure_hoyolab_dirs() -> None:
    """Create all current HoYoLAB import folders."""
    for folder in (
        HOYOLAB_DATA_DIR,
        HOYOLAB_CHARACTER_ASSETS_DIR,
        HOYOLAB_WEAPON_ASSETS_DIR,
        HOYOLAB_ARTIFACT_ASSETS_DIR,
        HOYOLAB_DEBUG_DIR,
    ):
        folder.mkdir(parents=True, exist_ok=True)


def clear_folder_contents(folder: Path) -> None:
    """Remove all children inside folder, but keep the folder itself."""
    folder.mkdir(parents=True, exist_ok=True)

    for child in folder.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except FileNotFoundError:
                pass


def clear_hoyolab_current_data() -> None:
    """Clear current HoYoLAB import data/assets/debug.

    This intentionally does NOT touch:
    - hoyolab_export/profile
    - runs_history.json
    - future history assets
    """
    clear_folder_contents(HOYOLAB_DATA_DIR)
    clear_folder_contents(HOYOLAB_ASSETS_DIR)
    clear_folder_contents(HOYOLAB_DEBUG_DIR)

    ensure_hoyolab_dirs()
