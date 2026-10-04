"""Independent login browser owner for managed account profiles."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from run_workspace.profile_control import profile_operation_lock


def _coordinate_login(profile_dir: Path, width: int, height: int,
                      x: int | None, y: int | None) -> int:
    # The lease precedes bootstrap so migration, browser launch, and the whole
    # browser lifetime cannot race a profile switch or deletion.
    with profile_operation_lock():
        from run_workspace.profile_context import bootstrap_profile
        from .auth import _open_login_browser_direct

        root = bootstrap_profile()
        expected = root / "hoyolab_export" / "profile"
        if profile_dir.resolve() != expected.resolve():
            raise RuntimeError("Login browser profile differs from the selected account")
        browser = _open_login_browser_direct(
            expected, width, height, x, y, quiet=True,
        )
        try:
            print(json.dumps({"ready": True}), flush=True)
        except BrokenPipeError:
            # The UI may have crashed after launch; retain the lease until the
            # independently running browser actually exits.
            pass
        return browser.wait()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 5:
        print(json.dumps({"ready": False, "error": "Invalid login browser request"}), flush=True)
        return 1
    try:
        profile_dir = Path(args[0])
        width, height = int(args[1]), int(args[2])
        x = None if args[3] == "none" else int(args[3])
        y = None if args[4] == "none" else int(args[4])
        if width <= 0 or height <= 0:
            raise ValueError("Invalid login browser geometry")
        return _coordinate_login(profile_dir, width, height, x, y)
    except Exception as exc:
        print(json.dumps({"ready": False, "error": str(exc)[:300]}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
