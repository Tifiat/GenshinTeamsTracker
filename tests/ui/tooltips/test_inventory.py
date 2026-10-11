"""Registration gate for every tooltip binding and semantic payload family.

This does not replace content tests. A new binding must be classified and its
semantic regression added here; otherwise a new hover surface cannot silently
escape the tooltip suite. Identical action hints share a family.
"""
import ast
from collections import Counter
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]

# Family -> independent content test in this package. Shared widgets may host
# several families; registration is an explicit code-review checkpoint.
FAMILIES = {
    "Traveler element selector": ("test_presentation_contracts", "test_traveler_selector_hint_describes_element_choice_in_all_languages"),
    "set bonuses: 2p, 4p, localized fallback": ("test_catalog_tooltips", "test_each_known_witness_survives_parser_storage_and_both_renderers_in_all_languages"),
    "first present imported set": ("test_catalog_tooltips", "test_first_available_imported_set"),
    "account character": ("test_content_contracts", "test_account_character_summary_identifies_level_constellation_and_element"),
    "observed weapon": ("test_content_contracts", "test_observed_weapon_summary_distinguishes_stack_count_and_stats"),
    "weapon passive": ("test_content_contracts", "test_weapon_passive_uses_reference_title_and_body_not_flavor_copy"),
    "artifact slot": ("test_content_contracts", "test_artifact_build_slot_tooltip_refreshes_for_populated_empty_and_missing"),
    "resonance mechanics": ("test_content_contracts", "test_elemental_resonance_explains_distinct_rules"),
    "Hexerei member and equipment warnings": ("test_content_contracts", "test_hexerei_member_and_warning_text_preserve_meaning_and_newlines"),
    "weapon, artifact, resonance, Moonsign, Hexerei bonus chips": ("test_content_contracts", "test_bonus_source_kinds_attach_meaningful_custom_tooltips"),
    "Fact DPS enemies and calculation": ("test_content_contracts", "test_fact_dps_html_shows_enemy_calculation_and_escaped_names"),
    "GCSIM result and stale reasons": ("test_content_contracts", "test_gcsim_html_surfaces_stale_state_and_escapes_paths"),
    "Fact/GCSIM cell refresh": ("test_content_contracts", "test_chamber_cells_attach_and_refresh_fact_and_gcsim_tooltips"),
    "History character card": ("test_content_contracts", "test_history_compact_slot_hover_uses_saved_identity"),
    "History enemies": ("test_content_contracts", "test_history_enemy_hover_uses_saved_wave_count_and_hp"),
    "History bonuses and overflow": ("test_content_contracts", "test_history_bonus_hovers_show_source_and_overflow_content"),
    "PvP draft ownership": ("test_content_contracts", "test_pvp_draft_card_tooltip_shows_per_seat_ownership"),
    "PvP postdraft equipment": ("test_content_contracts", "test_pvp_postdraft_character_and_weapon_summaries"),
    "action help and all supported locales": ("test_presentation_contracts", "test_action_help_locales_have_explicit_meaningful_text"),
    "optimizer save state and replacement DPS": ("test_presentation_contracts", "test_optimizer_save_status_and_replacement_help_are_distinct"),
    "virtual editor sources and unavailable state": ("test_presentation_contracts", "test_virtual_editor_profile_and_status_hints_follow_current_state"),
    "PvP run admission and stale reason": ("test_presentation_contracts", "test_pvp_run_admission_hints_update_and_clear_without_changing_run_guards"),
    "account settings and import state": ("test_presentation_contracts", "test_account_help_and_busy_hint_use_custom_controllers"),
    "character filter choices": ("test_presentation_contracts", "test_filter_buttons_attach_localized_custom_hints"),
    "plain/rich popup lifecycle": ("test_presentation_contracts", "test_shared_popup_renders_plain_and_rich_text_and_hides_on_owner_events"),
    "grid hover identity": ("test_presentation_contracts", "test_grid_hover_uses_one_anchor_and_clears_stale_text"),
    "drag icon updates": ("test_presentation_contracts", "test_draggable_icon_routes_updates_through_custom_controller"),
    "profile delete action": ("test_presentation_contracts", "test_profile_menu_delete_hint_uses_custom_surface"),
    "compact run summary": ("test_presentation_contracts", "test_compact_summary_hint_includes_character_weapon_and_sets"),
    "legacy import busy/cleanup/ready": ("test_presentation_contracts", "test_legacy_import_hint_transitions_busy_cleanup_ready"),
}

REGISTERED_BINDINGS = {
    "ui/app_shell.py": {"AssetIconLabel.__init__", "AssetIconLabel.setToolTip"},
    "ui/artifact_browser/filter_popup.py": {"SetsFilterPopup._icon_button"},
    "ui/artifact_browser/window.py": {
        "ArtifactBrowserWindow._build_build_panel", "ArtifactBrowserWindow._build_build_target_selector",
        "ArtifactBrowserWindow._install_set_bonus_tooltip", "ArtifactBrowserWindow._make_build_preset_row",
        "ArtifactBrowserWindow._set_json_action_button", "ArtifactBrowserWindow.retranslate_ui",
        "ArtifactBrowserWindow.update_build_create_controls", "ArtifactBrowserWindow.update_build_slot_row",
    },
    "ui/character_browser/filter_bar.py": {"CharacterFilterBar._make_filter_button", "CharacterFilterBar._make_standard_filter_button"},
    "ui/character_browser/traveler_selector.py": {"TravelerVariantGrid.set_variant_groups", "TravelerVariantGrid.retranslate_ui"},
    "ui/gcsim_browser/optimizer_result.py": {"CompactOptimizerArtifactCard.__init__", "OptimizerResultBuildsWidget._render_current_page"},
    "ui/gcsim_browser/virtual_slot_editor.py": {"VirtualGcsimCardEditor.__init__"},
    "ui/gcsim_browser/window.py": {"GcsimBrowserWorkspace.set_run_admission"},
    "ui/history_browser/window.py": {"_enemy_icon"},
    "ui/main_window.py": {"App.build_left_panel", "App._reload_icon_grid"},
    "ui/pvp_browser/window.py": {"PvpDeckAssetIconLabel.__init__", "PvpDeckAssetIconLabel.setToolTip"},
    "ui/right_panel/common/metrics.py": {"_set_custom_tooltip_text"},
    "ui/right_panel/common/run_summary.py": {"CompactSlotSummaryWidget.__init__"},
    "ui/right_panel/common/slot_card.py": {"RightPanelSlotCardWidget.set_model"},
    "ui/right_panel/common/slot_parts.py": {"RightPanelArtifactMiniZoneWidget.set_state", "RightPanelPixmapMiniBoxLabel._render"},
    "ui/right_panel/live_run/panel.py": {"BonusSourceChipWidget.__init__", "ChamberTableBlockWidget._rebuild", "ChamberTableBlockWidget._update_rows", "SelectedCharacterDetailsWidget._set_weapon_summary"},
    "ui/right_panel/pvp/decks/panel.py": {"PvpDecksRightPanel._install_button_tooltip"},
    "ui/right_panel/settings/account_data.py": {"AccountDataPage._build_ui"},
    "ui/right_panel/settings/account_profiles.py": {"AccountProfilesWidget._populate_menu"},
    "ui/utils/pixel_icon_grid.py": {"PixelIconGrid.__init__"},
    "ui/utils/tooltips.py": {"CustomTooltipController.__init__", "CustomTooltipController.set_text"},
    "ui/widgets/drag.py": {"DraggableIcon.__init__", "DraggableIcon.setToolTip"},
}

# Default is one call per registered method. Tracking multiplicity also catches
# a new tooltip added inside an already registered UI-construction method.
MULTIPLE_BINDINGS = {
    ("ui/artifact_browser/window.py", "ArtifactBrowserWindow._build_build_panel"): 2,
    ("ui/artifact_browser/window.py", "ArtifactBrowserWindow.retranslate_ui"): 2,
    ("ui/artifact_browser/window.py", "ArtifactBrowserWindow._make_build_preset_row"): 6,
    ("ui/artifact_browser/window.py", "ArtifactBrowserWindow.update_build_slot_row"): 3,
    ("ui/gcsim_browser/optimizer_result.py", "CompactOptimizerArtifactCard.__init__"): 2,
    ("ui/gcsim_browser/virtual_slot_editor.py", "VirtualGcsimCardEditor.__init__"): 4,
    ("ui/gcsim_browser/window.py", "GcsimBrowserWorkspace.set_run_admission"): 2,
    ("ui/right_panel/common/metrics.py", "_set_custom_tooltip_text"): 2,
    ("ui/right_panel/common/slot_card.py", "RightPanelSlotCardWidget.set_model"): 2,
    ("ui/right_panel/live_run/panel.py", "ChamberTableBlockWidget._rebuild"): 2,
    ("ui/right_panel/live_run/panel.py", "ChamberTableBlockWidget._update_rows"): 4,
    ("ui/right_panel/live_run/panel.py", "SelectedCharacterDetailsWidget._set_weapon_summary"): 3,
    ("ui/right_panel/live_run/panel.py", "BonusSourceChipWidget.__init__"): 3,
    ("ui/right_panel/pvp/decks/panel.py", "PvpDecksRightPanel._install_button_tooltip"): 2,
    ("ui/right_panel/settings/account_data.py", "AccountDataPage._build_ui"): 4,
}


class _Bindings(ast.NodeVisitor):
    def __init__(self):
        self.scope = []
        self.found = set()
        self.counts = Counter()

    def visit_ClassDef(self, node):
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_FunctionDef = visit_ClassDef
    visit_AsyncFunctionDef = visit_ClassDef

    def visit_Call(self, node):
        name = node.func.id if isinstance(node.func, ast.Name) else (
            node.func.attr if isinstance(node.func, ast.Attribute) else ""
        )
        if name in {"install_custom_tooltip", "setToolTip", "_set_custom_tooltip_text"}:
            self.found.add(".".join(self.scope))
            self.counts[".".join(self.scope)] += 1
        self.generic_visit(node)


class TooltipInventoryTest(unittest.TestCase):
    def test_new_tooltip_binding_requires_a_registered_semantic_contract(self):
        actual = {}
        counts = {}
        for path in (ROOT / "ui").rglob("*.py"):
            if path.name.endswith("_smoke.py"):
                continue
            visitor = _Bindings()
            visitor.visit(ast.parse(path.read_text(encoding="utf-8-sig")))
            if visitor.found:
                source = path.relative_to(ROOT).as_posix()
                actual[source] = visitor.found
                counts.update({(source, method): count for method, count in visitor.counts.items()})
        self.assertEqual(actual, REGISTERED_BINDINGS,
                         "Tooltip bindings changed: add/update the semantic regression and family registration.")
        expected_counts = {(source, method): MULTIPLE_BINDINGS.get((source, method), 1)
                           for source, methods in REGISTERED_BINDINGS.items() for method in methods}
        self.assertEqual(counts, expected_counts,
                         "Tooltip calls changed inside a registered method: review its content contract.")

    def test_guard_detects_an_extra_tooltip_inside_an_existing_method(self):
        before, after = _Bindings(), _Bindings()
        before.visit(ast.parse("def existing():\n install_custom_tooltip(a, 'first')"))
        after.visit(ast.parse("def existing():\n install_custom_tooltip(a, 'first')\n install_custom_tooltip(b, 'new kind')"))
        self.assertEqual(before.found, after.found)
        self.assertNotEqual(before.counts, after.counts)

    def test_every_registered_family_has_an_existing_regression(self):
        for kind, (module, method) in FAMILIES.items():
            with self.subTest(kind=kind):
                tree = ast.parse((Path(__file__).parent / f"{module}.py").read_text(encoding="utf-8"))
                names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
                self.assertIn(method, names)


if __name__ == "__main__":
    unittest.main()
