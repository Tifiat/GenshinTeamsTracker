from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from run_workspace.abyss.source_data_runtime import (
    CachedAbyssPeriodRef,
    read_cached_hoyolab_abyss_period,
)
from run_workspace.pvp.period_admission import (
    evaluate_pvp_period_admission,
    validate_current_official_period,
)


START = "2026-05-16"
END = "2026-06-16"
PERIOD_ID = f"{START}/{END}"
SOURCE_PATH = "$.data.schedule.period"


def _official_ref(**changes) -> CachedAbyssPeriodRef:
    values = {
        "start_date": START,
        "end_date": END,
        "raw_period": "2026/05/16-2026/06/16",
        "source_path": SOURCE_PATH,
        "source": "hoyolab_spiral_abyss_overview",
        "fallback": False,
        "warnings": (),
    }
    values.update(changes)
    return CachedAbyssPeriodRef(**values)


class PvpPeriodAdmissionTest(unittest.TestCase):
    def test_valid_official_period_returns_canonical_id(self) -> None:
        ref = _official_ref()

        decision = validate_current_official_period(
            ref,
            today=date(2026, 5, 16),
        )

        self.assertTrue(decision.ready)
        self.assertEqual(decision.status, "ready")
        self.assertEqual(decision.period_id, PERIOD_ID)
        self.assertIs(decision.ref, ref)

    def test_period_date_boundaries_are_start_inclusive_and_end_exclusive(self) -> None:
        for today, expected_ready in (
            (date(2026, 5, 15), False),
            (date(2026, 5, 16), True),
            (date(2026, 6, 15), True),
            (date(2026, 6, 16), False),
        ):
            with self.subTest(today=today):
                decision = validate_current_official_period(
                    _official_ref(),
                    today=today,
                )
                self.assertEqual(decision.ready, expected_ready)
                if not expected_ready:
                    self.assertEqual(decision.status, "period_not_current")

    def test_untrusted_provenance_and_invalid_periods_fail_closed(self) -> None:
        cases = (
            (_official_ref(source="fandom_latest_fallback"), "period_source_untrusted"),
            (_official_ref(fallback=True), "period_fallback_untrusted"),
            (_official_ref(fallback=None), "period_fallback_untrusted"),
            (_official_ref(source_path=""), "period_source_path_missing"),
            (_official_ref(warnings=("refresh warning",)), "period_has_warnings"),
            (_official_ref(start_date="2026-5-16"), "period_dates_invalid"),
            (_official_ref(start_date="2026-02-30"), "period_dates_invalid"),
            (_official_ref(end_date="2026-06-16 extra"), "period_dates_invalid"),
            (_official_ref(end_date=START), "period_dates_invalid"),
            (_official_ref(end_date="2026-05-15"), "period_dates_invalid"),
        )
        for ref, expected_status in cases:
            with self.subTest(expected_status=expected_status, ref=ref):
                decision = validate_current_official_period(
                    ref,
                    today=date(2026, 5, 20),
                )
                self.assertFalse(decision.ready)
                self.assertEqual(decision.status, expected_status)

        self.assertEqual(
            validate_current_official_period(None, today=date(2026, 5, 20)).status,
            "period_missing",
        )

    def test_both_profile_ids_must_match_current_period(self) -> None:
        ref = _official_ref()
        today = date(2026, 5, 20)

        accepted = evaluate_pvp_period_admission(
            ref,
            today=today,
            profile_period_ids=(PERIOD_ID, PERIOD_ID),
        )
        self.assertTrue(accepted.ready)
        self.assertEqual(accepted.period_id, PERIOD_ID)

        cases = (
            ((PERIOD_ID,), "profile_period_ids_missing"),
            ((PERIOD_ID, ""), "profile_period_id_missing"),
            ((PERIOD_ID, None), "profile_period_id_missing"),
            ((PERIOD_ID, "2026-04-16/2026-05-16"), "profile_period_id_mismatch"),
            ((PERIOD_ID, PERIOD_ID, PERIOD_ID), "profile_period_ids_missing"),
        )
        for profile_ids, expected_status in cases:
            with self.subTest(profile_ids=profile_ids):
                decision = evaluate_pvp_period_admission(
                    ref,
                    today=today,
                    profile_period_ids=profile_ids,
                )
                self.assertFalse(decision.ready)
                self.assertEqual(decision.status, expected_status)

    def test_unreadable_period_does_not_admit_profiles(self) -> None:
        decision = evaluate_pvp_period_admission(
            None,
            today=date(2026, 5, 20),
            profile_period_ids=(PERIOD_ID, PERIOD_ID),
        )

        self.assertFalse(decision.ready)
        self.assertEqual(decision.status, "period_missing")

    def test_period_reader_preserves_authority_and_invalid_types_stay_untrusted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "spiral_abyss_period.json"
            path.write_text(
                json.dumps(
                    {
                        "rawPeriod": "2026/05/16-2026/06/16",
                        "startDate": START,
                        "endDate": END,
                        "sourcePath": SOURCE_PATH,
                        "source": "hoyolab_spiral_abyss_overview",
                        "fallback": False,
                        "warnings": [],
                    }
                ),
                encoding="utf-8",
            )

            ref = read_cached_hoyolab_abyss_period(path)

        self.assertIsNotNone(ref)
        assert ref is not None
        self.assertEqual(ref.source, "hoyolab_spiral_abyss_overview")
        self.assertIs(ref.fallback, False)
        self.assertEqual(ref.warnings, ())
        self.assertTrue(
            validate_current_official_period(
                ref,
                today=date(2026, 5, 20),
            ).ready
        )

        malformed_fields = (
            ("source", 4),
            ("fallback", 0),
            ("sourcePath", 4),
            ("warnings", "none"),
        )
        for key, value in malformed_fields:
            with self.subTest(key=key):
                with tempfile.TemporaryDirectory() as temporary:
                    path = Path(temporary) / "spiral_abyss_period.json"
                    payload = {
                        "startDate": START,
                        "endDate": END,
                        "sourcePath": SOURCE_PATH,
                        "source": "hoyolab_spiral_abyss_overview",
                        "fallback": False,
                        "warnings": [],
                    }
                    payload[key] = value
                    if key == "sourcePath":
                        payload["source_path"] = SOURCE_PATH
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    malformed_ref = read_cached_hoyolab_abyss_period(path)

                self.assertIsNotNone(malformed_ref)
                assert malformed_ref is not None
                decision = validate_current_official_period(
                    malformed_ref,
                    today=date(2026, 5, 20),
                )
                self.assertFalse(decision.ready)

        self.assertEqual(
            validate_current_official_period(
                {"start_date": START},  # type: ignore[arg-type]
                today=date(2026, 5, 20),
            ).status,
            "period_untrusted",
        )

    def test_period_reader_keeps_backward_compatible_defaults_untrusted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "spiral_abyss_period.json"
            path.write_text(
                json.dumps({"startDate": START, "endDate": END}),
                encoding="utf-8",
            )
            ref = read_cached_hoyolab_abyss_period(path)

        self.assertIsNotNone(ref)
        assert ref is not None
        self.assertEqual(ref.source, "")
        self.assertIsNone(ref.fallback)
        self.assertEqual(ref.warnings, ())
        decision = validate_current_official_period(
            ref,
            today=date(2026, 5, 20),
        )
        self.assertFalse(decision.ready)
        self.assertEqual(decision.status, "period_source_untrusted")


if __name__ == "__main__":
    unittest.main()
