from __future__ import annotations

import json

from run_workspace.abyss.source_data_runtime import (
    DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH,
    load_current_cached_abyss_floor_source_data,
    read_cached_hoyolab_abyss_period,
)
from ui.app_shell import AppShellController


def build_smoke_report() -> dict[str, object]:
    period = read_cached_hoyolab_abyss_period()
    source_data = load_current_cached_abyss_floor_source_data()
    controller = AppShellController.empty()
    controller.set_abyss_timer_seconds(0, 1, 540)
    model = controller.right_panel_model()
    first_row = model.chamber_rows[0]
    return {
        "period_path": str(DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH),
        "period": None
        if period is None
        else {
            "start_date": period.start_date,
            "end_date": period.end_date,
            "raw_period": period.raw_period,
        },
        "source_data": None
        if source_data is None
        else {
            "period_start": source_data.period.start_date,
            "rows": len(source_data.enemy_rows),
            "matched": source_data.matched_count,
            "c1_side1_solo_target_hp": source_data.side_summary(1, 1).solo_target_hp,
        },
        "c1_t1_left_seconds": 540,
        "c1_t1_elapsed_seconds": first_row.team1_seconds,
        "c1_t1_fact_dps": first_row.factual_team1,
        "c1_t2_elapsed_seconds": first_row.team2_seconds,
        "c1_t2_fact_dps": first_row.factual_team2,
    }


def main() -> int:
    print(json.dumps(build_smoke_report(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
