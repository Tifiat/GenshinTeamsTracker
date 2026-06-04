from __future__ import annotations

import unittest

from run_workspace.abyss.fandom_enemy_hp_fallback import (
    HP_FALLBACK_MODE_AUTO,
    HP_FALLBACK_MODE_FANDOM_ONLY,
    HP_FALLBACK_MODE_NANOKA_ONLY,
    EnemyPage,
    apply_fandom_enemy_page_hp_fallback,
)
from run_workspace.abyss.source_data import (
    HP_SOURCE_FANDOM_ENEMY_PAGE_FALLBACK,
    HP_SOURCE_NANOKA_RESOLVED,
    HP_SOURCE_UNAVAILABLE,
    load_abyss_floor12_source_data,
)
from run_workspace.abyss.source_data_fetchers import _parse_fragment

from tests.abyss.test_source_data import (
    composition_report,
    fandom_row,
    nanoka_report,
    nanoka_row,
)


def _enemy_page(url: str, html: str) -> EnemyPage:
    return EnemyPage(
        requested_url=url,
        resolved_url=url,
        requested_title="Enemy",
        resolved_title="Enemy",
        html_root=_parse_fragment(html),
    )


def _stats_html(raw_hp: str = "1,000") -> str:
    return f"""
    <h2><span class="mw-headline" id="Stats">Stats</span></h2>
    <table class="article-table">
      <tr><th>Level</th><th>HP</th></tr>
      <tr><td>95</td><td>{raw_hp}</td></tr>
    </table>
    """


class FandomEnemyHpFallbackTest(unittest.TestCase):
    def test_auto_fills_missing_nanoka_hp_from_enemy_page(self) -> None:
        data = load_abyss_floor12_source_data(
            "2026-05-16",
            "119",
            composition_report=composition_report(
                "2026-05-16",
                [fandom_row("Fallback Enemy", chamber=1, side=1, wave=1, level=95)],
            ),
        )
        url = data.enemy_rows[0].fandom_enemy_page_url
        assert url is not None

        result = apply_fandom_enemy_page_hp_fallback(
            data,
            hp_multiplier=3.75,
            mode=HP_FALLBACK_MODE_AUTO,
            enemy_page_fetcher=lambda _url: _enemy_page(url, _stats_html()),
        )

        row = result.data.enemy_rows[0]
        self.assertEqual(result.attempted, 1)
        self.assertEqual(result.resolved, 1)
        self.assertEqual(row.nanoka_hp, 3750)
        self.assertEqual(row.hp_source, HP_SOURCE_FANDOM_ENEMY_PAGE_FALLBACK)
        self.assertEqual(result.data.side_summary(1, 1).solo_target_hp, 3750)
        self.assertIn("fandom_enemy_page_hp_fallback_used", row.warnings)

    def test_auto_does_not_override_existing_nanoka_hp(self) -> None:
        data = load_abyss_floor12_source_data(
            "2026-05-16",
            "119",
            composition_report=composition_report(
                "2026-05-16",
                [fandom_row("Enemy", chamber=1, side=1, wave=1, level=95)],
            ),
            nanoka_report=nanoka_report(
                "119",
                [nanoka_row("Enemy", chamber=1, side=1, hp=1234, monster_id="enemy")],
            ),
        )

        result = apply_fandom_enemy_page_hp_fallback(
            data,
            mode=HP_FALLBACK_MODE_AUTO,
            enemy_page_fetcher=lambda _url: self.fail("fallback should not fetch"),
        )

        row = result.data.enemy_rows[0]
        self.assertEqual(result.attempted, 0)
        self.assertEqual(row.nanoka_hp, 1234)
        self.assertEqual(row.hp_source, HP_SOURCE_NANOKA_RESOLVED)

    def test_fandom_only_overrides_nanoka_hp_for_debug_import(self) -> None:
        data = load_abyss_floor12_source_data(
            "2026-05-16",
            "119",
            composition_report=composition_report(
                "2026-05-16",
                [fandom_row("Enemy", chamber=1, side=1, wave=1, level=95)],
            ),
            nanoka_report=nanoka_report(
                "119",
                [nanoka_row("Enemy", chamber=1, side=1, hp=1234, monster_id="enemy")],
            ),
        )
        url = data.enemy_rows[0].fandom_enemy_page_url
        assert url is not None

        result = apply_fandom_enemy_page_hp_fallback(
            data,
            hp_multiplier=3.75,
            mode=HP_FALLBACK_MODE_FANDOM_ONLY,
            enemy_page_fetcher=lambda _url: _enemy_page(url, _stats_html("2,000")),
        )

        row = result.data.enemy_rows[0]
        self.assertEqual(result.attempted, 1)
        self.assertEqual(row.nanoka_hp, 7500)
        self.assertEqual(row.hp_source, HP_SOURCE_FANDOM_ENEMY_PAGE_FALLBACK)
        self.assertIn("nanoka_hp_overridden_by_forced_fandom_fallback", row.warnings)

    def test_nanoka_only_leaves_unavailable_hp_unchanged(self) -> None:
        data = load_abyss_floor12_source_data(
            "2026-05-16",
            "119",
            composition_report=composition_report(
                "2026-05-16",
                [fandom_row("Fallback Enemy", chamber=1, side=1, wave=1, level=95)],
            ),
        )

        result = apply_fandom_enemy_page_hp_fallback(
            data,
            mode=HP_FALLBACK_MODE_NANOKA_ONLY,
            enemy_page_fetcher=lambda _url: self.fail("fallback should not fetch"),
        )

        row = result.data.enemy_rows[0]
        self.assertEqual(result.attempted, 0)
        self.assertIsNone(row.nanoka_hp)
        self.assertEqual(row.hp_source, HP_SOURCE_UNAVAILABLE)

    def test_parallel_prefetch_fetches_unique_enemy_pages_once(self) -> None:
        data = load_abyss_floor12_source_data(
            "2026-05-16",
            "119",
            composition_report=composition_report(
                "2026-05-16",
                [
                    fandom_row("Shared Enemy", chamber=1, side=1, wave=1, level=95),
                    fandom_row("Shared Enemy", chamber=1, side=1, wave=2, level=95),
                    fandom_row("Other Enemy", chamber=1, side=1, wave=3, level=95),
                ],
            ),
        )
        calls: list[str] = []

        def fetcher(url: str) -> EnemyPage:
            calls.append(url)
            return _enemy_page(url, _stats_html("2,000"))

        result = apply_fandom_enemy_page_hp_fallback(
            data,
            hp_multiplier=3.75,
            mode=HP_FALLBACK_MODE_AUTO,
            enemy_page_fetcher=fetcher,
            enemy_page_workers=5,
        )

        self.assertEqual(result.attempted, 3)
        self.assertEqual(result.resolved, 3)
        self.assertEqual(result.page_fetches, 2)
        self.assertEqual(result.page_cache_hits, 1)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(row.nanoka_hp == 7500 for row in result.data.enemy_rows))

    def test_specific_heading_wins_over_generic_stats(self) -> None:
        data = load_abyss_floor12_source_data(
            "2026-05-16",
            "119",
            composition_report=composition_report(
                "2026-05-16",
                [
                    fandom_row(
                        "Battle-Scarred Rock Crab",
                        chamber=1,
                        side=1,
                        wave=1,
                        level=100,
                    )
                ],
            ),
        )
        url = data.enemy_rows[0].fandom_enemy_page_url
        assert url is not None
        html = """
        <h2><span class="mw-headline" id="Stats">Stats</span></h2>
        <table class="article-table">
          <tr><th>Level</th><th>HP</th></tr>
          <tr><td>100</td><td>999</td></tr>
        </table>
        <h2><span class="mw-headline" id="Battle-Scarred">Battle-Scarred</span></h2>
        <table class="article-table">
          <tr><th>Level</th><th>HP</th></tr>
          <tr><td>100</td><td>1,175,752</td></tr>
        </table>
        """

        result = apply_fandom_enemy_page_hp_fallback(
            data,
            hp_multiplier=3.75,
            mode=HP_FALLBACK_MODE_AUTO,
            enemy_page_fetcher=lambda _url: _enemy_page(url, html),
        )

        row = result.data.enemy_rows[0]
        self.assertEqual(row.nanoka_hp, 4_409_070)
        self.assertIn("fandom_enemy_page_hp_table_method:heading_exact_match", row.warnings)


if __name__ == "__main__":
    unittest.main()
