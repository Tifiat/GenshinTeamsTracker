"""Run deterministic tooltip contracts and a read-only imported-catalog witness."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import unittest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, help="Optional existing account artifacts.db; never created or modified")
    parser.add_argument("-v", "--verbose", action="store_true", help="List individual cases")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    if args.db is not None:
        if not args.db.is_file():
            parser.error("--db must name an existing database")
        os.environ["GTT_TOOLTIP_DB"] = str(args.db.resolve())
    suite = unittest.defaultTestLoader.discover(
        str(root / "tests" / "ui" / "tooltips"), top_level_dir=str(root),
    )
    # Shared surfaces also retain their focused freshness/image/position bugs.
    suite.addTests(unittest.defaultTestLoader.loadTestsFromNames((
        "tests.ui.right_panel.live_run.test_mini_set_tooltips",
        "tests.ui.right_panel.live_run.test_fact_dps_tooltip_icons",
        "tests.ui.right_panel.live_run.test_right_panel_bonus_icons",
        "tests.ui.right_panel.history.test_history_cards.HistoryCardsTest.test_scrolled_enemy_tooltip_follows_visible_hover_and_stays_on_screen",
        "tests.ui.right_panel.history.test_history_cards.HistoryCardsTest.test_scrolling_dismisses_character_popup_and_pending_hover",
        "tests.ui.right_panel.test_gcsim_optimizer_settings.GcsimOptimizerSettingsUiTests.test_fast_mode_help_is_adjacent_and_uses_localized_custom_tooltip",
    )))
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
