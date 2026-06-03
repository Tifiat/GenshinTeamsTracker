from __future__ import annotations

import unittest

from run_workspace.abyss.source_data_fetchers import (
    NanokaTowerPeriodAmbiguous,
    NanokaTowerPeriodNotFound,
    resolve_nanoka_tower_id_for_period,
)


def _manifest(*summaries: dict) -> dict:
    return {"tower": list(summaries)}


def _summary(
    tower_id: str,
    *,
    begin: str = "2026-05-16 04:00:00",
    end: str = "2026-06-16 03:59:59",
) -> dict:
    return {
        "id": tower_id,
        "begin": begin,
        "end": end,
        "live_begin": begin,
        "live_end": end,
    }


class NanokaPeriodLookupTest(unittest.TestCase):
    def test_exact_period_resolves_tower_id(self) -> None:
        tower_id = resolve_nanoka_tower_id_for_period(
            _manifest(
                _summary("118", begin="2026-04-16 04:00:00"),
                _summary("119"),
            ),
            period_start="2026-05-16",
        )

        self.assertEqual(tower_id, "119")

    def test_period_end_can_narrow_lookup(self) -> None:
        tower_id = resolve_nanoka_tower_id_for_period(
            _manifest(
                _summary("119", begin="2026-05-16 04:00:00", end="2026-06-16 03:59:59"),
            ),
            period_start="2026-05-16",
            period_end="2026-06-16",
        )

        self.assertEqual(tower_id, "119")

    def test_missing_period_raises_controlled_not_found(self) -> None:
        with self.assertRaises(NanokaTowerPeriodNotFound):
            resolve_nanoka_tower_id_for_period(
                _manifest(_summary("119")),
                period_start="2026-02-16",
            )

    def test_duplicate_period_raises_controlled_ambiguity(self) -> None:
        with self.assertRaises(NanokaTowerPeriodAmbiguous):
            resolve_nanoka_tower_id_for_period(
                _manifest(_summary("119"), _summary("119b")),
                period_start="2026-05-16",
            )


if __name__ == "__main__":
    unittest.main()
