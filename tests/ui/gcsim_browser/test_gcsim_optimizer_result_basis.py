from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from localization import tr
from ui.artifact_browser.models import ArtifactItem, ArtifactSubstat
from ui.gcsim_browser.optimizer_result import (
    OptimizerResultBuildsWidget,
    build_optimizer_result_pages,
)
from ui.utils.app_scaling import configure_startup_ui_scale

configure_startup_ui_scale(platform="linux")
_APP = QApplication.instance() or QApplication([])


class GcsimOptimizerResultBasisTests(unittest.TestCase):
    def test_replacement_expansion_stays_below_wearer_without_resizing_viewport(self) -> None:
        from PySide6.QtCore import QPoint
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QMainWindow
        from ui.gcsim_browser.window import GcsimBrowserWorkspace

        base = _assignments()
        artifacts = [
            _artifact(index, position)
            for position, index in enumerate(range(11, 16), 1)
        ]
        candidates = [
            {
                "rank": 1,
                "artifacts": base,
                "measured": {"dps": "1000"},
                "set_group_key": "same",
            }
        ]
        for slot in range(5):
            alternate = [dict(row) for row in base]
            artifact_id = 21 + slot
            alternate[slot]["artifact_id"] = artifact_id
            artifacts.append(_artifact(artifact_id, slot + 1))
            candidates.append(
                {
                    "rank": slot + 2,
                    "artifacts": alternate,
                    "measured": {"dps": str(990 - slot)},
                    "set_group_key": "same",
                }
            )
        pages = build_optimizer_result_pages(
            {
                "status": "success",
                "result": {
                    "ranking_basis": "gcsim",
                    "candidates": candidates,
                },
            },
            _selected_team(),
            artifacts,
        )

        window = QMainWindow()
        self.addCleanup(window.close)
        workspace = GcsimBrowserWorkspace()
        window.setCentralWidget(workspace)
        # AppShell keeps a 1408 logical-pixel minimum before its display scale.
        window.resize(1408, 740)
        window.show()
        workspace.workspace_tabs.setCurrentIndex(1)
        widget = workspace.optimizer_result_builds
        widget.set_pages(pages)
        QTest.qWait(30)
        _APP.processEvents()
        scroll = workspace.workspace_tabs.widget(1)
        scroll.verticalScrollBar().setValue(
            min(100, scroll.verticalScrollBar().maximum())
        )
        self.assertGreater(scroll.verticalScrollBar().value(), 0)

        header = widget.grid.itemAtPosition(0, 1).widget()
        wearer = widget.grid.itemAtPosition(1, 0).widget()
        container = widget._replacement_containers["furina"]

        def settled_state():
            QTest.qWait(20)
            _APP.processEvents()
            return (
                window.size(),
                scroll.viewport().size(),
                header.mapTo(scroll.viewport(), QPoint(0, 0)),
                wearer.mapTo(scroll.viewport(), QPoint(0, 0)),
                scroll.horizontalScrollBar().isVisible(),
                scroll.verticalScrollBar().value(),
                widget.minimumSizeHint().width(),
                widget.table.minimumSizeHint().width(),
                scroll.widget().minimumSizeHint().width(),
            )

        collapsed = settled_state()
        self.assertFalse(collapsed[4])
        widget._replacement_buttons["furina"].click()
        expanded = settled_state()
        self.assertFalse(expanded[4])
        self.assertFalse(container.isHidden())
        self.assertGreaterEqual(expanded[2].y(), 0)
        self.assertLess(expanded[2].y(), scroll.viewport().height())
        self.assertGreaterEqual(expanded[3].y(), 0)
        self.assertLess(expanded[3].y(), scroll.viewport().height())
        self.assertGreater(
            container.mapTo(widget.table, QPoint(0, 0)).y(),
            wearer.geometry().bottom(),
        )
        cards = [widget.grid.itemAtPosition(1, column).widget() for column in range(1, 6)]
        action = widget.grid.itemAtPosition(1, 6).widget()
        swap_grid = container.layout().itemAt(1).layout()
        swaps = [swap_grid.itemAtPosition(0, column).widget() for column in range(5)]
        self.assertTrue(all(card.width() > action.width() for card in cards))
        self.assertLessEqual(action.width(), 116)
        self.assertGreater(action.x(), cards[-1].geometry().right())
        self.assertEqual(
            [(card.x(), card.width()) for card in cards],
            [(swap.mapTo(widget.table, QPoint(0, 0)).x(), swap.width()) for swap in swaps],
        )
        widget._replacement_buttons["furina"].click()
        collapsed_again = settled_state()

        self.assertEqual(expanded, collapsed)
        self.assertEqual(collapsed_again, collapsed)

    def test_single_swaps_expand_below_wearer_and_never_attribute_multi_item_delta(self) -> None:
        from PySide6.QtWidgets import QLabel
        artifacts = [_artifact(index, position) for position, index in enumerate(range(11, 16), 1)]
        artifacts += [_artifact(21, 2), _artifact(22, 3)]
        base = _assignments()
        single = [dict(row) for row in base]
        single[1]["artifact_id"] = 21
        double = [dict(row) for row in single]
        double[2]["artifact_id"] = 22
        for basis in ("formula", "gcsim"):
            candidates = [dict(rank=i+1, artifacts=items, set_group_key="same", set_group_rank=1,
                               formula_dps=str(dps), measured={"dps":str(dps)})
                          for i,(items,dps) in enumerate(((base,1000),(single,990),(double,980)))]
            pages = build_optimizer_result_pages({"status":"success", "result":{
                "ranking_basis":basis,"candidates":candidates}}, _selected_team(), artifacts)
            self.assertEqual(len(pages), 1)
            swaps = pages[0].rows[0].replacements
            self.assertEqual(len(swaps), 1)
            self.assertEqual((swaps[0].original_id, swaps[0].artifact.id, swaps[0].dps_delta),(12,21,-10))
            widget = OptimizerResultBuildsWidget()
            self.addCleanup(widget.close)
            widget.set_pages(pages)
            container = widget._replacement_containers["furina"]
            self.assertTrue(container.isHidden())
            widget._replacement_buttons["furina"].click()
            self.assertFalse(container.isHidden())
            label = container.findChild(QLabel,"OptimizerReplacementDelta")
            self.assertIn("-10 DPS", label.text())
            self.assertEqual("≈" in label.text(), basis == "formula")

    def test_formula_pages_are_labeled_unverified_and_never_present_as_measured(self) -> None:
        row_count = 3001  # No hidden UI truncation at the historical 210/2500 rows.
        artifacts = [_artifact(index, position) for position, index in enumerate(range(11, 16), 1)]
        assignments = _assignments()
        candidates = [
            {
                "rank": rank,
                "artifacts": assignments,
                "formula_dps": str(200_000 - rank),
                "set_group_key": f"group-{(rank - 1) // 7 + 1}",
                "set_group_rank": (rank - 1) // 7 + 1,
                "alternative_rank": (rank - 1) % 7 + 1,
            }
            for rank in range(1, row_count + 1)
        ]

        pages = build_optimizer_result_pages(
            {
                "status": "success",
                "result": {
                    "ranking_basis": "formula",
                    "candidates": candidates,
                },
            },
            _selected_team(),
            artifacts,
        )
        widget = OptimizerResultBuildsWidget()
        self.addCleanup(widget.close)
        widget.set_pages(pages)

        self.assertEqual(len(pages), (row_count + 6) // 7)
        self.assertEqual(pages[-1].rank, ((row_count - 1) // 7) * 7 + 1)
        self.assertEqual(widget.grid.count(), 12)
        self.assertEqual(pages[0].measured_dps, "")
        self.assertEqual(pages[0].formula_dps, "199999")
        self.assertEqual(widget.basis_label.text(), tr("gcsim.optimizer.formula_unverified"))
        self.assertIn(tr("gcsim.optimizer.set_group_label").format(rank=1), widget.context_label.text())
        self.assertNotIn(tr("gcsim.optimizer.alternative_label").format(rank=1), widget.context_label.text())
        self.assertIn("199 999", widget.title_label.text())
        self.assertNotIn("Top-", widget.title_label.text())

        widget.next_button.click()

        self.assertEqual(widget.current_page_index, 1)
        self.assertIn(tr("gcsim.optimizer.set_group_label").format(rank=2), widget.context_label.text())
        self.assertEqual(widget.basis_label.text(), tr("gcsim.optimizer.formula_unverified"))

    def test_early_finish_notice_is_visible_in_optimizer_result_text(self) -> None:
        from ui.gcsim_browser.window import GcsimBrowserWorkspace

        workspace = GcsimBrowserWorkspace()
        self.addCleanup(workspace.close)
        notice = tr("gcsim.optimizer.search_finished_by_user")

        workspace.set_optimizer_result_text(
            "Selected Sets complete\n"
            + notice
            + "\nFinal DPS: 12345"
        )

        self.assertIn(notice, workspace.optimizer_result.toPlainText())

    def test_measured_and_legacy_payloads_keep_gcsim_dps_titles(self) -> None:
        artifacts = [_artifact(index, position) for position, index in enumerate(range(11, 16), 1)]
        candidate = {
            "rank": 1,
            "artifacts": _assignments(),
            "measured": {"dps": "1234.5"},
            "set_group_rank": 2,
            "alternative_rank": 3,
        }
        pages = build_optimizer_result_pages(
            {
                "status": "success",
                "result": {
                    "ranking_basis": "gcsim",
                    "candidates": [candidate],
                },
            },
            _selected_team(),
            artifacts,
        )
        widget = OptimizerResultBuildsWidget()
        self.addCleanup(widget.close)
        widget.set_pages(pages)

        self.assertEqual(pages[0].measured_dps, "1234.5")
        self.assertEqual(widget.basis_label.text(), tr("gcsim.optimizer.gcsim_measured"))
        self.assertEqual(
            widget.title_label.text(),
            tr("gcsim.optimizer.grouped_result_title").format(dps="1 234"),
        )
        self.assertIn(tr("gcsim.optimizer.set_group_label").format(rank=2), widget.context_label.text())
        self.assertNotIn(tr("gcsim.optimizer.alternative_label").format(rank=3), widget.context_label.text())

        legacy_pages = build_optimizer_result_pages(
            {
                "status": "success",
                "result": {
                    "winner": _assignments(),
                    "measured": {"dps": "900"},
                },
            },
            _selected_team(),
            artifacts,
        )
        self.assertEqual(legacy_pages[0].ranking_basis, "gcsim")
        self.assertEqual(legacy_pages[0].measured_dps, "900")
        legacy_widget = OptimizerResultBuildsWidget()
        self.addCleanup(legacy_widget.close)
        legacy_widget.set_pages(legacy_pages)
        self.assertEqual(
            legacy_widget.title_label.text(),
            tr("gcsim.optimizer.rank_title").format(rank=1, dps="900"),
        )


def _assignments() -> list[dict[str, object]]:
    return [
        {"wearer_key": "furina", "slot": slot, "artifact_id": artifact_id}
        for slot, artifact_id in zip(
            ("flower", "plume", "sands", "goblet", "circlet"),
            range(11, 16),
            strict=True,
        )
    ]


def _selected_team() -> dict[str, object]:
    return {
        "slots": [
            {
                "character": {"id": 10000089, "name": "Furina"},
                "character_details_data": {
                    "account_character": {
                        "id": 10000089,
                        "name": "Furina",
                        "gcsim_character_key": "furina",
                    }
                },
            }
        ]
    }


def _artifact(artifact_id: int, position: int) -> ArtifactItem:
    return ArtifactItem(
        id=artifact_id,
        name=f"Artifact {artifact_id}",
        set_id=1,
        set_uid="test-set",
        set_name="Test Set",
        pos=position,
        pos_name=str(position),
        rarity=5,
        level=20,
        main_property_type=3,
        main_property_name="HP%",
        main_property_value="46.6%",
        substats=[
            ArtifactSubstat(1, 20, "CRIT Rate", "3.9%", 1),
            ArtifactSubstat(2, 22, "CRIT DMG", "21.8%", 1),
            ArtifactSubstat(3, 5, "ATK", "478", 1),
            ArtifactSubstat(4, 9, "DEF%", "11.7%", 1),
        ],
    )


if __name__ == "__main__":
    unittest.main()
