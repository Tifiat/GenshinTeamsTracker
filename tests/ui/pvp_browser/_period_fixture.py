from __future__ import annotations

from datetime import date

from run_workspace.abyss.source_data_runtime import CachedAbyssPeriodRef
from run_workspace.pvp.profile_package import PvpProfilePackageOptions


PERIOD_START_DATE = "2026-10-01"
PERIOD_END_DATE = "2026-11-01"
PERIOD_ID = f"{PERIOD_START_DATE}/{PERIOD_END_DATE}"
PERIOD_TODAY = date(2026, 10, 4)
_DEFAULT_REF = object()


def fixture_period_ref(**changes: object) -> CachedAbyssPeriodRef:
    values: dict[str, object] = {
        "start_date": PERIOD_START_DATE,
        "end_date": PERIOD_END_DATE,
        "raw_period": "2026/10/01-2026/11/01",
        "source_path": "$.data.schedule.period",
        "source": "hoyolab_spiral_abyss_overview",
        "fallback": False,
        "warnings": (),
    }
    values.update(changes)
    return CachedAbyssPeriodRef(**values)  # type: ignore[arg-type]


def fixture_period_provider_kwargs(
    ref: CachedAbyssPeriodRef | None | object = _DEFAULT_REF,
    *,
    today: date = PERIOD_TODAY,
) -> dict[str, object]:
    frozen_ref = fixture_period_ref() if ref is _DEFAULT_REF else ref
    return {
        "abyss_period_provider": lambda: frozen_ref,
        "today_provider": lambda: today,
    }


def fixture_profile_options(period_id: str = PERIOD_ID) -> PvpProfilePackageOptions:
    return PvpProfilePackageOptions(abyss_period_id=period_id)
