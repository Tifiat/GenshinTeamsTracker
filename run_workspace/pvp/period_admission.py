"""Pure admission checks for a PvP match's official Abyss period."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from run_workspace.abyss.source_data_runtime import CachedAbyssPeriodRef


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
OFFICIAL_HOYOLAB_PERIOD_SOURCE = "hoyolab_spiral_abyss_overview"


@dataclass(frozen=True, slots=True)
class PvpPeriodAdmissionDecision:
    ready: bool
    status: str
    period_id: str | None
    ref: CachedAbyssPeriodRef | None


def validate_current_official_period(
    ref: CachedAbyssPeriodRef | None,
    *,
    today: date,
) -> PvpPeriodAdmissionDecision:
    """Validate provenance and date bounds without reading a clock.

    The canonical period ID is ``start_date/end_date``. The explicit end date
    is exclusive, so dates alone fail closed at the period's boundary.
    """

    if ref is None:
        return _decision(False, "period_missing", None, None)
    if not isinstance(ref, CachedAbyssPeriodRef):
        return _decision(False, "period_untrusted", None, None)
    if type(today) is not date:
        return _decision(False, "invalid_today", None, ref)
    if type(ref.source) is not str or ref.source != OFFICIAL_HOYOLAB_PERIOD_SOURCE:
        return _decision(False, "period_source_untrusted", None, ref)
    if type(ref.fallback) is not bool or ref.fallback is not False:
        return _decision(False, "period_fallback_untrusted", None, ref)
    if type(ref.source_path) is not str or not ref.source_path.strip():
        return _decision(False, "period_source_path_missing", None, ref)
    if type(ref.warnings) is not tuple or ref.warnings:
        return _decision(False, "period_has_warnings", None, ref)

    start = _strict_iso_date(ref.start_date)
    end = _strict_iso_date(ref.end_date)
    if start is None or end is None or end <= start:
        return _decision(False, "period_dates_invalid", None, ref)

    period_id = f"{start.isoformat()}/{end.isoformat()}"
    if not start <= today < end:
        return _decision(False, "period_not_current", period_id, ref)
    return _decision(True, "ready", period_id, ref)


def evaluate_pvp_period_admission(
    ref: CachedAbyssPeriodRef | None,
    *,
    today: date,
    profile_period_ids: Iterable[str],
) -> PvpPeriodAdmissionDecision:
    """Require both PvP profiles to target the same current official period."""

    period = validate_current_official_period(ref, today=today)
    if not period.ready:
        return period

    try:
        profile_ids = tuple(profile_period_ids)
    except TypeError:
        return _decision(False, "profile_period_ids_missing", period.period_id, ref)
    if len(profile_ids) != 2:
        return _decision(False, "profile_period_ids_missing", period.period_id, ref)
    if any(
        type(profile_id) is not str or not profile_id.strip()
        for profile_id in profile_ids
    ):
        return _decision(False, "profile_period_id_missing", period.period_id, ref)
    if any(profile_id != period.period_id for profile_id in profile_ids):
        return _decision(False, "profile_period_id_mismatch", period.period_id, ref)
    return period


def _strict_iso_date(value: object) -> date | None:
    if type(value) is not str or not _ISO_DATE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _decision(
    ready: bool,
    status: str,
    period_id: str | None,
    ref: CachedAbyssPeriodRef | None,
) -> PvpPeriodAdmissionDecision:
    return PvpPeriodAdmissionDecision(
        ready=ready,
        status=status,
        period_id=period_id,
        ref=ref,
    )
