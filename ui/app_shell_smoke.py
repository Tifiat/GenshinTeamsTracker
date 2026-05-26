from __future__ import annotations

import argparse
import os
import sys

from ui.app_shell import launch_app_shell


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Launch the separate AppShell prototype. The legacy main.py entrypoint "
            "is not changed."
        )
    )
    parser.add_argument(
        "--perf-log",
        action="store_true",
        help="Print opt-in AppShell timing logs for click/filter profiling.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.perf_log:
        os.environ["GTT_PERF_LOG"] = "1"
    return launch_app_shell()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
