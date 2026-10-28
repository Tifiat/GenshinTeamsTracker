"""Offscreen Theory presentation tests using saved synthetic witnesses only."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale()

from PySide6.QtWidgets import QApplication

from localization import available_languages, get_language, set_language, tr
from run_workspace.gcsim.optimizer_theory_presentation import (
    THEORY_STAT_KEYS, noncrit_upgrades, theory_score_display,
)
from tests.run_workspace.gcsim.theory_output_fixture import (
    EXPECTED_GROUP_TUPLES, EXPECTED_PENDING_TUPLES,
    family_row, output_snapshot, refresh_measurement_identity, snapshot_with_rows,
)
from ui.gcsim_browser.optimizer_result import (
    CompactOptimizerArtifactCard, OptimizerResultBuildsWidget,
)
from ui.gcsim_browser.theory_result import TheoryResultPages, build_theory_page, theory_stat_label
from ui.utils.tooltips import CustomTooltipController
from ui.utils.ui_palette import UI_STATE_CAUTION, UI_STATE_DANGER, UI_STATE_SUCCESS


_APP = QApplication.instance() or QApplication([])


class TheoryPresentationUiTests(unittest.TestCase):
    def _widget(self, pages) -> OptimizerResultBuildsWidget:
        widget = OptimizerResultBuildsWidget()
        self.addCleanup(widget.deleteLater)
        self.addCleanup(widget.close)
        widget.set_pages(pages)
        return widget

    def _joint_variant_snapshot(self) -> dict:
        baseline = family_row("joint", 1000.0, 0.0)
        alternative = deepcopy(baseline)
        alternative["formula_dps"] = 1500.0
        alternative["measurement"]["formula_dps"] = 1500.0
        alternative["measurement"]["measured_dps"] = 980.0
        alternative["aliases"][0]["tuple_key"] = "choice-joint-alt"

        # Two linked main changes belong to one already-scored four-wearer
        # witness. Keep its saved lines and package links exactly as published.
        for actor, slot_index, new_main in (
            (0, 2, "def_percent"),
            (1, 3, "geo_damage_bonus"),
        ):
            slot = ("flower", "plume", "sands", "goblet", "circlet")[slot_index]
            alternative["witness45"]["Mains"][actor][slot_index] = new_main
            alternative["allocations"][actor]["main_stats"][slot] = new_main
        refresh_measurement_identity(alternative)
        return snapshot_with_rows([baseline, alternative])

    def test_index_keeps_every_alias_in_source_order_and_accepts_pending_witnesses(self) -> None:
        snapshot = output_snapshot()
        pages = TheoryResultPages(snapshot)

        expected = EXPECTED_GROUP_TUPLES + EXPECTED_PENDING_TUPLES
        self.assertEqual(
            tuple(entry.alias["tuple_key"] for entry in pages.index), expected,
        )
        self.assertGreater(len(pages), 5)
        edge_pending = next(
            entry for entry in pages.index
            if entry.alias["tuple_key"] == "choice-outside-3-0"
        )
        self.assertEqual(edge_pending.refinement_level, 0)
        self.assertLess(edge_pending.score, 970.0)
        self.assertTrue(all("unavailable-choice" not in key for key in expected))
        self.assertEqual(pages.index.reference, 1000.0)

    def test_unavailable_incomplete_and_malformed_rows_are_not_builds(self) -> None:
        snapshot = output_snapshot()
        snapshot["co_leaders"][0]["complete"] = False
        malformed = snapshot["co_leaders"][1]
        lines = malformed["witness45"]["Lines"][0][0]
        lines[1] = lines[0]

        pages = TheoryResultPages(snapshot)
        aliases = tuple(entry.alias["tuple_key"] for entry in pages.index)
        self.assertEqual(aliases, EXPECTED_GROUP_TUPLES[2:] + EXPECTED_PENDING_TUPLES)
        self.assertNotIn("choice-edge-3-0", aliases)
        self.assertNotIn("choice-reference-0", aliases)
        self.assertTrue(set(snapshot["unavailable"][i]["tuple_key"] for i in range(2)).isdisjoint(aliases))

    def test_page_objects_are_lazy_cached_and_limited_to_current_twenty_cards(self) -> None:
        with patch(
            "ui.gcsim_browser.theory_result.build_theory_page",
            wraps=build_theory_page,
        ) as build_page:
            pages = TheoryResultPages(output_snapshot())
            self.assertEqual(len(pages), 9)
            build_page.assert_not_called()

            first = pages[0]
            self.assertIs(pages[0], first)
            self.assertEqual(build_page.call_count, 1)
            self.assertEqual(sum(len(row.artifacts) for row in first.rows), 20)
            self.assertTrue(all(row.hypothetical for row in first.rows))

            second = pages[1]
            self.assertIsNot(first, second)
            self.assertEqual(build_page.call_count, 2)
            pages.refresh_display()
            self.assertIsNot(pages[0], first)
            self.assertEqual(build_page.call_count, 3)

    def test_navigation_reaches_the_last_alias_without_optimizer_engine_or_inventory_calls(self) -> None:
        pages = TheoryResultPages(output_snapshot())
        with (
            patch("ui.gcsim_browser.theory_result.build_theory_page", wraps=build_theory_page) as build_page,
            patch("ui.app_shell.build_optimizer_result_pages") as ordinary_pages,
            patch("ui.app_shell.list_all_artifacts") as inventory,
            patch("ui.gcsim_browser.run_worker.GcsimBrowserSelectedOptimizerWorker.run") as worker_run,
            patch("run_workspace.gcsim.optimizer_go_theory_session.GcsimOptimizerGoTheorySession.run") as session_run,
        ):
            widget = self._widget(pages)
            self.assertEqual(build_page.call_count, 1)
            for _ in range(1, len(pages)):
                widget.next_button.click()
                current = pages[widget.current_page_index]
                self.assertEqual(sum(len(row.artifacts) for row in current.rows), 20)
                self.assertTrue(all(row.hypothetical and not row.can_save for row in current.rows))

            self.assertEqual(widget.current_page_index, len(pages) - 1)
            self.assertFalse(widget.next_button.isEnabled())
            self.assertEqual(build_page.call_count, len(pages))
            ordinary_pages.assert_not_called()
            inventory.assert_not_called()
            worker_run.assert_not_called()
            session_run.assert_not_called()

    def test_fixed_reference_and_raw_percent_boundaries_keep_honest_styles(self) -> None:
        score_rows = (
            ("leader", 1000.0),
            ("edge-97", 970.0),
            ("under-97", 969.9999),
            ("edge-95", 950.0),
            ("under-95", 949.9999),
            ("tiny-deficit", 999.9999),
        )
        rows = [
            family_row(key, score, 100.0 - score / 10.0)
            for key, score in score_rows
        ]
        snapshot = snapshot_with_rows(rows)
        pages = TheoryResultPages(snapshot)
        snapshot["reference_score"] = 5000.0
        self.assertEqual(pages.index.reference, 1000.0)

        widget = self._widget(pages)
        expected_bands = ("green", "green", "orange", "orange", "red", "green")
        expected_colors = {
            "green": UI_STATE_SUCCESS,
            "orange": UI_STATE_CAUTION,
            "red": UI_STATE_DANGER,
        }
        for family_index, ((_, score), expected_band) in enumerate(zip(score_rows, expected_bands)):
            target_page = family_index
            while widget.current_page_index < target_page:
                widget.next_button.click()
            context = pages[target_page].theory_context
            display = theory_score_display(score, 1000.0)
            self.assertEqual(context.reference, 1000.0)
            self.assertEqual(display.color_band, expected_band)
            self.assertIn(f"color:{expected_colors[expected_band]}", widget.title_label.text())
            self.assertIn(display.percent_text + "%", widget.title_label.text())

            if score == 1000.0:
                self.assertEqual(display.deficit_text, "0")
                self.assertNotIn("−", widget.title_label.text())
            elif score == 969.9999:
                self.assertLess(float(display.percent_text), 97.0)
                self.assertGreater(float(display.percent_text), 95.0)
            elif score == 949.9999:
                self.assertLess(float(display.percent_text), 95.0)
            elif score == 999.9999:
                self.assertTrue(display.nonzero_deficit)
                self.assertEqual(display.deficit_text, "<0.1")
                self.assertIn("−<0.1%", widget.title_label.text())
                self.assertIn(f"color:{UI_STATE_DANGER}", widget.title_label.text())

    def test_all_zero_verified_measurements_show_no_percentage_or_leader_claim(self) -> None:
        row = family_row("zero", 0.0, 0.0, iterations=1)
        pages = TheoryResultPages(snapshot_with_rows([row]))
        self.assertEqual(pages.index.reference, 0.0)
        self.assertIsNone(theory_score_display(pages.index[0].score, pages.index.reference))
        widget = self._widget(pages)
        self.assertEqual(
            widget.title_label.text(),
            tr("gcsim.optimizer.theory_display.header_no_reference").format(dps="0"),
        )
        self.assertNotIn("100%", widget.title_label.text())
        self.assertEqual(widget.basis_label.text(), tr("gcsim.optimizer.theory_display.reference_zero"))

    def test_full45_cards_keep_the_saved_witness_and_noncrit_counts_only_upgrades(self) -> None:
        pages = TheoryResultPages(output_snapshot())
        page = pages[0]
        row = page.rows[0]
        witness = pages.index[0].row["witness45"]

        self.assertEqual(len(row.artifacts), 5)
        self.assertTrue(row.hypothetical)
        self.assertFalse(row.can_save)
        self.assertEqual(row.slots, ())
        self.assertEqual(sum(len(slot_lines) for slot_lines in witness["Lines"][0]), 20)
        self.assertEqual(sum(sum(slot) for slot in witness["Upgrades"][0]), 25)
        for slot_index, artifact in enumerate(row.artifacts):
            self.assertEqual((artifact.rarity, artifact.level), (5, 20))
            self.assertEqual(len(artifact.substats), 4)
            self.assertEqual(
                artifact.main_property_name,
                theory_stat_label(witness["Mains"][0][slot_index]),
            )
            self.assertEqual(sum(row.theory_piece_upgrades[slot_index]), 5)

        expected_noncrit = 0.0
        for slot_lines, slot_upgrades in zip(witness["Lines"][0], witness["Upgrades"][0]):
            for coordinate, units in zip(slot_lines, slot_upgrades):
                if THEORY_STAT_KEYS[coordinate] not in {"crit_rate", "crit_damage"}:
                    expected_noncrit += units
        displayed_noncrit = sum(units for _, units in row.noncrit_upgrade_units)
        self.assertAlmostEqual(displayed_noncrit, expected_noncrit)
        self.assertLess(displayed_noncrit, 25)
        self.assertNotIn("crit_rate", dict(row.noncrit_upgrade_units))
        self.assertNotIn("crit_damage", dict(row.noncrit_upgrade_units))
        self.assertEqual(noncrit_upgrades(pages.index[0].row, 0), row.noncrit_upgrade_units)

        widget = self._widget(pages)
        cards = widget.findChildren(CompactOptimizerArtifactCard)
        self.assertEqual(len(cards), 20)
        for card in cards:
            ordinary = CompactOptimizerArtifactCard(card.artifact)
            self.addCleanup(ordinary.deleteLater)
            self.assertEqual(card.minimumSize(), ordinary.minimumSize())
            self.assertEqual(card.maximumSize(), ordinary.maximumSize())
            self.assertEqual(card.sizePolicy(), ordinary.sizePolicy())

    def test_theory_replaces_save_with_noncrit_while_normal_builds_keep_save(self) -> None:
        theory_pages = TheoryResultPages(output_snapshot())
        theory_widget = self._widget(theory_pages)
        theory_row = theory_widget._rows["wearer-a"]
        self.assertTrue(theory_row.hypothetical)
        self.assertFalse(theory_row.can_save)
        self.assertEqual(theory_widget._save_buttons, {})
        self.assertIn("wearer-a", theory_widget._theory_noncrit_labels)
        units = sum(value for _, value in theory_row.noncrit_upgrade_units)
        self.assertEqual(
            theory_widget._theory_noncrit_labels["wearer-a"].text(),
            tr("gcsim.optimizer.theory_display.noncrit").format(units=f"{units:g}"),
        )

        regular_artifacts = tuple(
            replace(item, id=index + 1)
            for index, item in enumerate(theory_row.artifacts)
        )
        regular_row = replace(
            theory_row,
            hypothetical=False,
            character_id=123,
            artifacts=regular_artifacts,
            slots=tuple((item.pos, item.id) for item in regular_artifacts),
            theory_piece_upgrades=(),
        )
        regular_page = replace(
            theory_pages[0], rows=(regular_row,), theory_context=None,
        )
        regular_widget = self._widget((regular_page,))
        save_button = regular_widget._save_buttons["wearer-a"]
        self.assertTrue(save_button.isEnabled())
        self.assertEqual(save_button.text(), tr("artifact.build.save"))
        saved = []
        regular_widget.save_requested.connect(saved.append)
        self.assertTrue(regular_widget.request_save("wearer-a", "Fixture build"))
        self.assertEqual(saved[0]["name"], "Fixture build")
        self.assertEqual(saved[0]["targets"][0]["character_id"], 123)

    def test_context_header_and_hypothetical_labels_use_all_three_locales(self) -> None:
        previous_language = get_language()
        self.addCleanup(set_language, previous_language, persist=False)
        for language in ("en", "pt-br", "ru"):
            with self.subTest(language=language):
                self.assertIn(language, available_languages())
                set_language(language, persist=False)
                pages = TheoryResultPages(output_snapshot())
                widget = self._widget(pages)

                context = pages[0].theory_context
                phase = tr("gcsim.optimizer.theory_session.phase." + context.phase)
                self.assertEqual(
                    widget.context_label.text(),
                    tr("gcsim.optimizer.theory_display.page_context").format(
                        number=1, total=len(pages), phase=phase,
                        depth=context.refinement_level,
                    ),
                )
                display = theory_score_display(context.score, context.reference)
                self.assertEqual(
                    widget.title_label.text(),
                    tr("gcsim.optimizer.theory_display.header").format(
                        percent=(
                            f'<span style="color:{UI_STATE_SUCCESS}">'
                            f"{display.percent_text}%</span>"
                        ),
                        dps=display.dps_text,
                        deficit=f'<span style="color:{UI_STATE_DANGER}">−{display.deficit_text}%</span>',
                    ),
                )
                self.assertNotIn("Top-1", widget.title_label.text())
                self.assertEqual(
                    widget._rows["wearer-a"].artifacts[0].name,
                    tr("gcsim.optimizer.theory_display.hypothetical"),
                )
                label = widget._theory_noncrit_labels["wearer-a"]
                units = sum(value for _, value in widget._rows["wearer-a"].noncrit_upgrade_units)
                self.assertEqual(
                    label.text(),
                    tr("gcsim.optimizer.theory_display.noncrit").format(units=f"{units:g}"),
                )

    def test_same_package_main_replacement_switches_the_full_scored_joint_witness(self) -> None:
        snapshot = self._joint_variant_snapshot()
        baseline, alternative = snapshot["co_leaders"]
        self.assertEqual(baseline["aliases"][0]["packages"], alternative["aliases"][0]["packages"])
        self.assertEqual(baseline["witness45"]["Lines"], alternative["witness45"]["Lines"])

        pages = TheoryResultPages(snapshot)
        self.assertEqual(pages.index.replacement_indices(0), (1,))
        widget = self._widget(pages)
        options = widget._theory_main_options
        self.assertIsNotNone(options)
        self.assertEqual(options.count(), 0)
        toggle = widget.grid.itemAtPosition(9, 1).widget()
        self.assertIsNotNone(toggle)
        toggle.click()
        self.assertEqual(options.count(), 2)
        self.assertEqual(options.itemData(1), 1)
        self.assertIn(tr("gcsim.optimizer.slot.sands"), options.itemText(1))
        self.assertIn(tr("gcsim.optimizer.slot.goblet"), options.itemText(1))
        options.setCurrentIndex(1)

        self.assertEqual(widget.current_page_index, 1)
        current = pages[1]
        self.assertEqual(float(current.measured_dps), 980.0)
        self.assertEqual(float(current.formula_dps), 1500.0)
        self.assertEqual(current.theory_context.score, 980.0)
        self.assertEqual(len(widget._rows), 4)
        self.assertEqual(
            widget._rows["wearer-a"].artifacts[2].main_property_name,
            theory_stat_label("def_percent"),
        )
        self.assertEqual(
            widget._rows["wearer-b"].artifacts[3].main_property_name,
            theory_stat_label("geo_damage_bonus"),
        )
        self.assertEqual(current.rows[0].theory_piece_upgrades, tuple(tuple(slot) for slot in alternative["witness45"]["Upgrades"][0]))

    def test_loaded_set_bonus_text_appears_on_two_and_four_piece_cards_only(self) -> None:
        four_row = family_row("bonus-four", 1000.0, 0.0)
        four_uid = four_row["aliases"][0]["packages"][0]["sets"][0]["set_uid"]
        four_choice = SimpleNamespace(
            set_uid=four_uid, gcsim_key=four_uid, display_name="Four piece",
            icon_path="", two_piece_description="<p>Two &amp; <b>power</b></p>",
            four_piece_description="<p>Four<br>power</p>",
        )
        four_pages = TheoryResultPages(snapshot_with_rows([four_row]), set_choices=(four_choice,))
        four_description = four_pages[0].rows[0].theory_set_bonus_descriptions[0]
        self.assertIn("Two &amp; power", four_description)
        self.assertIn("Four<br>power", four_description)
        self.assertNotIn("<b>", four_description)

        four_widget = self._widget(four_pages)
        first_card = four_widget.findChildren(CompactOptimizerArtifactCard)[0]
        tooltip = first_card.findChild(CustomTooltipController)
        self.assertIsNotNone(tooltip)
        self.assertIn(four_description, tooltip.text())

        two_row = family_row("bonus-two", 1000.0, 0.0, alias_variant=1)
        two_choices = []
        for set_row in two_row["aliases"][0]["packages"][0]["sets"]:
            uid = set_row["set_uid"]
            two_choices.append(SimpleNamespace(
                set_uid=uid, gcsim_key=uid, display_name=uid, icon_path="",
                two_piece_description="Two-piece text", four_piece_description="Four-piece text",
            ))
        two_pages = TheoryResultPages(snapshot_with_rows([two_row]), set_choices=two_choices)
        two_description = two_pages[0].rows[0].theory_set_bonus_descriptions[0]
        self.assertIn("Two-piece text", two_description)
        self.assertNotIn("Four-piece text", two_description)

        flexible_row = family_row("bonus-flexible", 1000.0, 0.0, alias_variant=2)
        flexible_pages = TheoryResultPages(snapshot_with_rows([flexible_row]), set_choices=two_choices)
        self.assertEqual(flexible_pages[0].rows[3].theory_set_bonus_descriptions, ("", "", "", "", ""))

    def test_main_replacements_require_same_package_with_distinct_joint_witnesses(self) -> None:
        snapshot = self._joint_variant_snapshot()
        alternative = snapshot["co_leaders"][1]
        for alias in alternative["aliases"]:
            for package in alias["packages"]:
                for set_row in package["sets"]:
                    set_row["set_uid"] += "-different-package"
        refresh_measurement_identity(alternative)
        different_package_pages = TheoryResultPages(snapshot)
        self.assertEqual(different_package_pages.index.replacement_indices(0), ())

        real_shape_pages = TheoryResultPages(output_snapshot())
        self.assertTrue(all(
            not real_shape_pages.index.replacement_indices(index)
            for index in range(len(real_shape_pages))
        ))


if __name__ == "__main__":
    unittest.main()
