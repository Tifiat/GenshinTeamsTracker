"""Source -> SQLite -> actual hover controller, plus first present local witness.

GTT_TOOLTIP_DB optionally selects a read-only catalog. By default only this
checkout's selected account is inspected, without creating/bootstraping one.
No account identifiers, inventory dumps or rendered text are written to disk.
"""
from contextlib import ExitStack, closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import warnings

from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtGui import QTextDocument

from hoyolab_export.artifact_set_catalog import bonus_descriptions_from_display_field
from hoyolab_export.artifact_db import connect_db, init_db
from run_workspace.account_profiles import active_profile, profile_root, PROJECT_ROOT
from run_workspace.right_panel_prototype_view_model import RightPanelBuildMiniSetViewModel
from ui.artifact_browser import queries
from ui.artifact_browser.store import ArtifactBrowserStore
from ui.artifact_browser.window import ArtifactBrowserWindow
from ui.right_panel.common import slot_parts
from tests.ui.tooltips.known_sets import (
    KNOWN_SETS, TooltipCoverageWarning, assert_bonus_tooltip, first_available_witness,
)


# Authored, abbreviated API-shaped examples; expected facts live separately.
SOURCE_EXAMPLES = {
    "EmblemOfSeveredFate": {
        "en-us": ("Energy Recharge +20%", "Elemental Burst damage: 25% of Energy Recharge; maximum 75%."),
        "ru-ru": ("Восстановление энергии +20%", "Урон взрыва стихий: 25% от восстановления энергии; максимум 75%."),
        "pt-pt": ("Recarga de Energia +20%", "Dano do Supremo: 25% da Recarga de Energia; máximo 75%."),
    },
    "DeepwoodMemories": {
        "en-us": ("Dendro damage +15%", "Elemental Skills or Bursts hit: Dendro RES -30% for 8s, even off-field."),
        "ru-ru": ("Дендро урон +15%", "Элементальным навыком или взрывом стихии: Дендро сопротивление -30%, 8 сек., даже не на поле боя."),
        "pt-pt": ("Dano Dendro +15%", "Habilidades Elementais ou Supremos: RES Dendro -30% por 8s, mesmo que não estiver em campo."),
    },
    "NoblesseOblige": {
        "en-us": ("Elemental Burst damage +20%", "Elemental Burst gives all party members ATK +20%, 12s; cannot stack."),
        "ru-ru": ("Урон взрыва стихии +20%", "Активация взрыва стихии повышает силу атаки всех членов отряда на 20%, 12 сек.; не складывается."),
        "pt-pt": ("Dano do Supremo +20%", "Supremo: ATQ de todos os membros da equipe +20%, 12s; não pode ser acumulado."),
    },
}
for _examples in SOURCE_EXAMPLES.values():
    _examples["pt-br"] = _examples["pt-pt"]


def _catalog_selection():
    explicit = os.environ.get("GTT_TOOLTIP_DB")
    if explicit:
        return Path(explicit).resolve()
    selected = active_profile(project_root=PROJECT_ROOT)
    root = profile_root(selected["id"], project_root=PROJECT_ROOT) if selected else PROJECT_ROOT
    return root / "data" / "artifacts.db"


def _owned_sets_and_languages(db: Path, preferred: str):
    if not db.exists():
        return set(), {}
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "artifacts" not in tables:
            return set(), {}
        available = {str(r[0]) for r in conn.execute("SELECT DISTINCT set_uid FROM artifacts WHERE set_uid IS NOT NULL")}
        languages = {}
        if "artifact_set_bonus_descriptions" in tables:
            for language in dict.fromkeys(("en-us", preferred)):
                for uid, pieces, description in conn.execute(
                    "SELECT set_uid, piece_count, description FROM artifact_set_bonus_descriptions "
                    "WHERE lang = ? AND TRIM(description) != ''", (language,),
                ):
                    document = QTextDocument()
                    document.setHtml(description)
                    if document.toPlainText().strip():
                        languages[(uid, pieces)] = language
        return available, languages


def check_catalog(db: Path) -> str | None:
    """Read existing owned-set data and test the two production hover surfaces."""
    app = QApplication.instance() or QApplication([])
    with ExitStack() as stack:
        data_dir = db.parent / "hoyolab"
        stack.enter_context(patch.object(slot_parts, "ARTIFACT_DB_PATH", db))
        stack.enter_context(patch.object(slot_parts, "HOYOLAB_DATA_DIR", data_dir))
        stack.enter_context(patch.object(queries, "HOYOLAB_DATA_DIR", data_dir))
        slot_parts._cached_set_bonus_descriptions.cache_clear()
        stack.callback(slot_parts._cached_set_bonus_descriptions.cache_clear)
        preferred = queries.current_hoyolab_content_language()
        available, languages = _owned_sets_and_languages(db, preferred)

        def check(candidate):
            descriptions = queries.list_set_bonus_description_map(db_path=db)
            store = ArtifactBrowserStore(database_exists=True, artifacts=[], set_bonus_descriptions=descriptions)
            # Use production handlers on a minimal owner, so no unrelated UI
            # initialization/preset migration writes to an inspected database.
            owner = SimpleNamespace(store=store)
            owner._clean_set_bonus_description = ArtifactBrowserWindow._clean_set_bonus_description
            owner._set_bonus_tooltip_html = lambda rows: ArtifactBrowserWindow._set_bonus_tooltip_html(owner, rows)
            effective_languages = {p: languages.get((candidate.uid, p), preferred) for p in (2, 4)}
            for pieces in (2, 4):
                widget = slot_parts.RightPanelArtifactMiniZoneWidget()
                stack.callback(widget.close)
                widget.set_state(slot_parts.RightPanelArtifactMiniZoneState(mini_sets=(
                    RightPanelBuildMiniSetViewModel(candidate.uid, candidate.name, pieces, pieces),
                )))
                assert_bonus_tooltip(widget._tooltip_controller.text(), candidate, effective_languages, pieces=pieces)
                rows = ArtifactBrowserWindow._set_bonus_tooltip_rows(owner, {"set_uid": candidate.uid, "count": pieces})
                label = QLabel()
                stack.callback(label.close)
                ArtifactBrowserWindow._install_set_bonus_tooltip(owner, label, rows)
                assert_bonus_tooltip(label._custom_tooltip_controller.text(), candidate, effective_languages, pieces=pieces)
                assert widget.toolTip() == label.toolTip() == ""

        return first_available_witness(available, check)


class ConditionalWitnessTest(unittest.TestCase):
    def test_absent_candidate_advances_and_first_present_stops(self):
        check = Mock()
        self.assertEqual(first_available_witness([KNOWN_SETS[1].uid, KNOWN_SETS[2].uid], check), KNOWN_SETS[1].uid)
        check.assert_called_once_with(KNOWN_SETS[1])

    def test_present_mismatch_fails_instead_of_trying_next_set(self):
        check = Mock(side_effect=AssertionError("lost bonus"))
        with self.assertRaisesRegex(AssertionError, "lost bonus"):
            first_available_witness([c.uid for c in KNOWN_SETS], check)
        check.assert_called_once_with(KNOWN_SETS[0])

    def test_no_known_set_warns_without_failure(self):
        check = Mock()
        with self.assertWarnsRegex(TooltipCoverageWarning, "дописать автотест"):
            self.assertIsNone(first_available_witness(["UncoveredNewSet"], check))
        check.assert_not_called()


class CatalogTooltipTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "data" / "artifacts.db"
        self.db.parent.mkdir()
        self.language_dir = self.db.parent / "hoyolab"
        self.language_dir.mkdir()
        with closing(sqlite3.connect(self.db)) as conn:
            conn.executescript("""
                CREATE TABLE artifacts (id INTEGER PRIMARY KEY, set_uid TEXT);
                CREATE TABLE artifact_set_bonus_descriptions (
                    set_uid TEXT, lang TEXT, piece_count INTEGER, description TEXT,
                    source TEXT, updated_at TEXT, PRIMARY KEY(set_uid,lang,piece_count));
            """)

    def _import(self, uid, *, language="en-us", descriptions=None):
        two, four = descriptions or SOURCE_EXAMPLES[uid][language]
        source = {"two_set_effect": f"<p>{two}</p>", "four_set_effect": f"<p><span>{four}</span></p>"}
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("INSERT INTO artifacts(set_uid) VALUES (?)", (uid,))
            conn.executemany("INSERT OR REPLACE INTO artifact_set_bonus_descriptions VALUES (?,?,?,?,?,?)", (
                (uid, language, p, text, "controlled_hoyowiki_example", "2026-10-04")
                for p, text in bonus_descriptions_from_display_field(source).items()
            ))
            conn.commit()
        (self.language_dir / "account_language.json").write_text(json.dumps({"contentLanguage": language}), encoding="utf-8")

    def test_each_known_witness_survives_parser_storage_and_both_renderers_in_all_languages(self):
        for candidate in KNOWN_SETS:
            for language in candidate.facts:
                with self.subTest(set=candidate.uid, language=language):
                    with closing(sqlite3.connect(self.db)) as conn:
                        conn.execute("DELETE FROM artifacts")
                        conn.execute("DELETE FROM artifact_set_bonus_descriptions")
                        conn.commit()
                    self._import(candidate.uid, language=language)
                    before = self.db.read_bytes()
                    self.assertEqual(check_catalog(self.db), candidate.uid)
                    self.assertEqual(self.db.read_bytes(), before)

    def test_first_owned_set_missing_four_piece_description_fails(self):
        self._import(KNOWN_SETS[0].uid, descriptions=("Energy Recharge +20%", ""))
        self._import(KNOWN_SETS[1].uid)
        with self.assertRaisesRegex(AssertionError, "bonus rows"):
            check_catalog(self.db)

    def test_existing_set_with_wrong_percentage_fails(self):
        self._import(KNOWN_SETS[0].uid, descriptions=("Energy Recharge +200%", SOURCE_EXAMPLES[KNOWN_SETS[0].uid]["en-us"][1]))
        with self.assertRaisesRegex(AssertionError, "expected percentages"):
            check_catalog(self.db)

    def test_portuguese_tagged_english_source_is_not_accepted_by_numbers_alone(self):
        self._import(KNOWN_SETS[0].uid, language="pt-br",
                     descriptions=SOURCE_EXAMPLES[KNOWN_SETS[0].uid]["en-us"])
        with self.assertRaisesRegex(AssertionError, "missing fact"):
            check_catalog(self.db)

    def test_description_moved_to_wrong_piece_row_fails(self):
        self._import(KNOWN_SETS[0].uid, descriptions=SOURCE_EXAMPLES[KNOWN_SETS[0].uid]["en-us"][::-1])
        with self.assertRaisesRegex(AssertionError, "expected percentages"):
            check_catalog(self.db)

    def test_missing_localized_four_piece_uses_english_facts_for_that_row(self):
        self._import(KNOWN_SETS[0].uid)
        self._import(KNOWN_SETS[0].uid, language="ru-ru", descriptions=(SOURCE_EXAMPLES[KNOWN_SETS[0].uid]["ru-ru"][0], ""))
        self.assertEqual(check_catalog(self.db), KNOWN_SETS[0].uid)

    def test_absent_database_is_not_created(self):
        missing = self.db.parent / "never-created.db"
        with self.assertWarns(TooltipCoverageWarning):
            self.assertIsNone(check_catalog(missing))
        self.assertFalse(missing.exists())

    def test_unowned_seed_catalog_does_not_count_as_an_imported_witness(self):
        self._import(KNOWN_SETS[0].uid)
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("DELETE FROM artifacts")
            conn.commit()
        with self.assertWarns(TooltipCoverageWarning):
            self.assertIsNone(check_catalog(self.db))

    def test_artifact_browser_store_loader_keeps_english_when_translation_is_empty_html(self):
        # Exercise the Browser's own DB loader as well as the mini-zone reader.
        database = self.db.with_name("full-store.db")
        uid = KNOWN_SETS[0].uid
        with closing(connect_db(database)) as conn:
            init_db(conn)
            conn.execute(
                "INSERT INTO artifact_sets(set_uid,hoyowiki_entry_id,fallback_name,source,updated_at) VALUES (?,?,?,?,?)",
                (uid, "2090", "Emblem of Severed Fate", "fixture", "2026-10-04"),
            )
            conn.executemany("INSERT INTO artifact_set_bonus_descriptions VALUES (?,?,?,?,?,?)", (
                (uid, "en-us", 2, SOURCE_EXAMPLES[uid]["en-us"][0], "fixture", "1"),
                (uid, "en-us", 4, SOURCE_EXAMPLES[uid]["en-us"][1], "fixture", "1"),
                (uid, "ru-ru", 4, "<p><br>&nbsp;</p>", "fixture", "1"),
            ))
            conn.commit()
        with patch.object(queries, "current_hoyolab_content_language", return_value="ru-ru"):
            store = ArtifactBrowserStore.load_from_db(database)
        self.assertEqual(store.set_bonus_description(uid, 4), SOURCE_EXAMPLES[uid]["en-us"][1])

    def test_empty_update_clears_old_set_tooltip(self):
        owner = SimpleNamespace()
        owner._set_bonus_tooltip_html = lambda rows: ArtifactBrowserWindow._set_bonus_tooltip_html(owner, rows)
        label = QLabel()
        self.addCleanup(label.close)
        ArtifactBrowserWindow._install_set_bonus_tooltip(owner, label, [(2, "Old bonus")])
        controller = label._custom_tooltip_controller
        ArtifactBrowserWindow._install_set_bonus_tooltip(owner, label, [])
        self.assertIs(label._custom_tooltip_controller, controller)
        self.assertEqual(controller.text(), "")


class ImportedCatalogTooltipTest(unittest.TestCase):
    def test_first_available_imported_set(self):
        # No skip on mismatch. A clean/uncovered account emits the requested
        # coverage warning, separate from deterministic fixture acceptance.
        with warnings.catch_warnings():
            warnings.simplefilter("always", TooltipCoverageWarning)
            witness = check_catalog(_catalog_selection())
            if witness:
                print(f"[tooltip catalog] {witness}: 2p/4p descriptions verified on both hover surfaces")


if __name__ == "__main__":
    unittest.main()
