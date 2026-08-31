from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from hoyolab_export.paths import PROJECT_ROOT
from localization import tr
from ui.artifact_browser.card_delegate import cached_scaled_pixmap
from ui.artifact_browser.models import ArtifactItem
from ui.artifact_browser.stat_types import (
    ANEMO_DAMAGE,
    CRYO_DAMAGE,
    DENDRO_DAMAGE,
    ELECTRO_DAMAGE,
    GEO_DAMAGE,
    HYDRO_DAMAGE,
    PYRO_DAMAGE,
    stat_badge,
)
from ui.utils.hidpi_pixmap import load_hidpi_pixmap
from ui.utils.tooltips import CustomTooltipController, install_custom_tooltip
from ui.utils.ui_palette import (
    UI_BG_BUTTON_CHECKED,
    UI_BG_PANEL,
    UI_BORDER_DEFAULT,
    UI_STATE_DANGER,
    UI_STATE_SUCCESS,
    UI_TEXT_MUTED,
    UI_TEXT_PRIMARY,
    UI_TEXT_SECONDARY,
)


OPTIMIZER_SLOT_ORDER = ("flower", "plume", "sands", "goblet", "circlet")
OPTIMIZER_SLOT_POSITIONS = {
    "flower": 1,
    "plume": 2,
    "sands": 3,
    "goblet": 4,
    "circlet": 5,
}
ELEMENT_MAIN_STAT_ICONS = {
    PYRO_DAMAGE: PROJECT_ROOT / "assets" / "filters" / "element_pyro.png",
    HYDRO_DAMAGE: PROJECT_ROOT / "assets" / "filters" / "element_hydro.png",
    ELECTRO_DAMAGE: PROJECT_ROOT / "assets" / "filters" / "element_electro.png",
    CRYO_DAMAGE: PROJECT_ROOT / "assets" / "filters" / "element_cryo.png",
    ANEMO_DAMAGE: PROJECT_ROOT / "assets" / "filters" / "element_anemo.png",
    GEO_DAMAGE: PROJECT_ROOT / "assets" / "filters" / "element_geo.png",
    DENDRO_DAMAGE: PROJECT_ROOT / "assets" / "filters" / "element_dendro.png",
}


@dataclass(frozen=True, slots=True)
class OptimizerResultBuildRow:
    wearer_key: str
    character_id: int | str | None
    character_name: str
    character_icon_path: Path | None
    artifacts: tuple[ArtifactItem, ...]
    slots: tuple[tuple[int, int], ...]
    missing_artifact_ids: tuple[int, ...] = ()

    @property
    def can_save(self) -> bool:
        return len(self.artifacts) == 5 and not self.missing_artifact_ids

    def save_request(self, name: str) -> dict[str, Any]:
        targets: list[dict[str, Any]] = []
        if self.character_id is not None:
            targets.append(
                {
                    "target_type": "character",
                    "character_id": self.character_id,
                    "character_name": self.character_name,
                }
            )
        return {
            "wearer_key": self.wearer_key,
            "name": str(name).strip(),
            "slots": dict(self.slots),
            "targets": targets,
        }


@dataclass(frozen=True, slots=True)
class OptimizerResultPage:
    rank: int
    measured_dps: str
    rows: tuple[OptimizerResultBuildRow, ...]


def build_optimizer_result_pages(
    payload: Mapping[str, Any],
    selected_team: Mapping[str, Any] | None,
    artifacts: Sequence[ArtifactItem],
) -> tuple[OptimizerResultPage, ...]:
    if str(payload.get("status") or "") != "success":
        return ()
    result = _mapping(payload.get("result")) or _mapping(payload)
    raw_candidates = result.get("candidates")
    candidates = (
        list(raw_candidates)
        if isinstance(raw_candidates, Sequence)
        and not isinstance(raw_candidates, (str, bytes))
        else []
    )
    if not candidates:
        candidates = [
            {
                "rank": 1,
                "artifacts": result.get("winner") or [],
                "measured": result.get("measured") or {},
            }
        ]

    pages: list[OptimizerResultPage] = []
    for fallback_rank, raw_candidate in enumerate(candidates, start=1):
        candidate = _mapping(raw_candidate)
        rank = _optional_int(candidate.get("rank")) or fallback_rank
        measured = _mapping(candidate.get("measured"))
        candidate_payload = {
            "status": "success",
            "result": {"winner": candidate.get("artifacts") or []},
        }
        rows = build_optimizer_result_rows(
            candidate_payload,
            selected_team,
            artifacts,
        )
        if not rows:
            continue
        pages.append(
            OptimizerResultPage(
                rank=rank,
                measured_dps=str(measured.get("dps") or "").strip(),
                rows=rows,
            )
        )
    return tuple(sorted(pages, key=lambda page: page.rank))


def build_optimizer_result_rows(
    payload: Mapping[str, Any],
    selected_team: Mapping[str, Any] | None,
    artifacts: Sequence[ArtifactItem],
) -> tuple[OptimizerResultBuildRow, ...]:
    if str(payload.get("status") or "") != "success":
        return ()

    result = _mapping(payload.get("result")) or payload
    winner = result.get("winner")
    if not isinstance(winner, Sequence) or isinstance(winner, (str, bytes)):
        return ()

    winner_by_wearer: dict[str, dict[str, int]] = {}
    wearer_order: list[str] = []
    for raw_item in winner:
        item = _mapping(raw_item)
        wearer_key = _normalized_key(item.get("wearer_key"))
        slot = str(item.get("slot") or "").strip().casefold()
        artifact_id = _optional_int(item.get("artifact_id"))
        if not wearer_key or slot not in OPTIMIZER_SLOT_POSITIONS or artifact_id is None:
            continue
        if wearer_key not in winner_by_wearer:
            wearer_order.append(wearer_key)
        winner_by_wearer.setdefault(wearer_key, {})[slot] = artifact_id

    artifacts_by_id = {int(item.id): item for item in artifacts}
    team_slots = list((_mapping(selected_team).get("slots") or []))
    team_by_wearer: dict[str, dict[str, Any]] = {}
    team_order: list[str] = []
    for raw_slot in team_slots:
        slot = _mapping(raw_slot)
        character = _mapping(slot.get("character"))
        details = _mapping(slot.get("character_details_data"))
        account_character = _mapping(details.get("account_character")) or character
        wearer_key = _normalized_key(account_character.get("gcsim_character_key"))
        if not wearer_key:
            wearer_key = _normalized_key(character.get("name"))
        if not wearer_key:
            continue
        team_order.append(wearer_key)
        team_by_wearer[wearer_key] = {
            "character": character,
            "account_character": account_character,
        }

    ordered_wearers = [key for key in team_order if key in winner_by_wearer]
    ordered_wearers.extend(key for key in wearer_order if key not in ordered_wearers)

    rows: list[OptimizerResultBuildRow] = []
    for wearer_key in ordered_wearers:
        winner_slots = winner_by_wearer[wearer_key]
        team_item = team_by_wearer.get(wearer_key, {})
        character = _mapping(team_item.get("character"))
        account_character = _mapping(team_item.get("account_character"))
        character_name = str(
            account_character.get("name")
            or character.get("name")
            or wearer_key
        ).strip()
        character_id: int | str | None = (
            account_character.get("id")
            if account_character.get("id") not in (None, "")
            else character.get("id")
        )
        parsed_id = _optional_int(character_id)
        if parsed_id is not None:
            character_id = parsed_id
        icon_path = _existing_project_path(
            account_character.get("local_side_icon_path")
            or account_character.get("side_icon_path")
            or account_character.get("local_portrait_path")
            or account_character.get("portrait_path")
        )

        row_artifacts: list[ArtifactItem] = []
        row_slots: list[tuple[int, int]] = []
        missing: list[int] = []
        for slot_name in OPTIMIZER_SLOT_ORDER:
            artifact_id = winner_slots.get(slot_name)
            if artifact_id is None:
                continue
            row_slots.append((OPTIMIZER_SLOT_POSITIONS[slot_name], artifact_id))
            artifact = artifacts_by_id.get(artifact_id)
            if artifact is None:
                missing.append(artifact_id)
            else:
                row_artifacts.append(artifact)

        rows.append(
            OptimizerResultBuildRow(
                wearer_key=wearer_key,
                character_id=character_id,
                character_name=character_name,
                character_icon_path=icon_path,
                artifacts=tuple(row_artifacts),
                slots=tuple(row_slots),
                missing_artifact_ids=tuple(missing),
            )
        )
    return tuple(rows)


class OptimizerResultBuildsWidget(QFrame):
    save_requested = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setVisible(False)
        self._rows: dict[str, OptimizerResultBuildRow] = {}
        self._save_buttons: dict[str, QPushButton] = {}
        self._save_tooltips: dict[str, CustomTooltipController] = {}
        self._status_labels: dict[str, QLabel] = {}
        self._pages: tuple[OptimizerResultPage, ...] = ()
        self._page_index = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
        navigation = QHBoxLayout()
        navigation.setContentsMargins(0, 0, 0, 0)
        navigation.setSpacing(6)
        self.previous_button = QPushButton("←")
        self.previous_button.setFixedWidth(36)
        self.previous_button.clicked.connect(lambda: self._change_page(-1))
        navigation.addWidget(self.previous_button)
        self.title_label = QLabel()
        self.title_label.setObjectName("GcsimBrowserSectionTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        navigation.addWidget(self.title_label, 1)
        self.next_button = QPushButton("→")
        self.next_button.setFixedWidth(36)
        self.next_button.clicked.connect(lambda: self._change_page(1))
        navigation.addWidget(self.next_button)
        root.addLayout(navigation)

        self.table = QWidget()
        self.grid = QGridLayout(self.table)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(5)
        self.grid.setVerticalSpacing(5)
        root.addWidget(self.table)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self._update_navigation()
        for wearer_key, button in self._save_buttons.items():
            button.setText(_translated("artifact.build.save", "Save"))
            row = self._rows.get(wearer_key)
            if row is not None:
                controller = self._save_tooltips.get(wearer_key)
                if controller is not None:
                    controller.set_text(
                        _translated(
                            "gcsim.optimizer.save_tooltip",
                            "Save this build in Artifact Browser",
                        )
                    )

    def set_rows(self, rows: Sequence[OptimizerResultBuildRow]) -> None:
        self.set_pages(
            (OptimizerResultPage(rank=1, measured_dps="", rows=tuple(rows)),)
            if rows
            else ()
        )

    def set_pages(self, pages: Sequence[OptimizerResultPage]) -> None:
        self.clear()
        self._pages = tuple(pages)
        if not self._pages:
            return
        self._page_index = 0
        self._render_current_page()
        self.setVisible(True)

    @property
    def current_page_index(self) -> int:
        return self._page_index

    def _render_current_page(self) -> None:
        self._clear_grid()
        if not self._pages:
            self._update_navigation()
            return
        rows = self._pages[self._page_index].rows
        self._rows = {row.wearer_key: row for row in rows}
        headers = (
            _translated("gcsim.optimizer.slot.flower", "Flower"),
            _translated("gcsim.optimizer.slot.plume", "Plume"),
            _translated("gcsim.optimizer.slot.sands", "Sands"),
            _translated("gcsim.optimizer.slot.goblet", "Goblet"),
            _translated("gcsim.optimizer.slot.circlet", "Circlet"),
        )
        for column, text in enumerate(headers, start=1):
            label = QLabel(text)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(f"color: {UI_TEXT_MUTED}; font-size: 9px;")
            self.grid.addWidget(label, 0, column)

        for row_index, row in enumerate(rows, start=1):
            self.grid.addWidget(_CharacterBadge(row), row_index, 0)
            artifacts_by_pos = {int(item.pos): item for item in row.artifacts}
            for column, position in enumerate(range(1, 6), start=1):
                artifact = artifacts_by_pos.get(position)
                if artifact is None:
                    missing = QLabel("—")
                    missing.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    missing.setMinimumSize(104, 88)
                    self.grid.addWidget(missing, row_index, column)
                else:
                    self.grid.addWidget(
                        CompactOptimizerArtifactCard(artifact),
                        row_index,
                        column,
                    )

            action = QWidget()
            action_layout = QVBoxLayout(action)
            action_layout.setContentsMargins(2, 0, 0, 0)
            action_layout.setSpacing(4)
            button = QPushButton(_translated("artifact.build.save", "Save"))
            button.setEnabled(row.can_save and row.character_id is not None)
            tooltip = install_custom_tooltip(
                button,
                _translated(
                    "gcsim.optimizer.save_tooltip",
                    "Save this build in Artifact Browser",
                )
            )
            button.clicked.connect(
                lambda _checked=False, key=row.wearer_key: self._emit_save(key)
            )
            status = QLabel()
            status.setWordWrap(True)
            status.setMaximumWidth(78)
            status.setStyleSheet(f"color: {UI_TEXT_MUTED}; font-size: 9px;")
            if not row.can_save:
                status.setText(
                    _translated(
                        "gcsim.optimizer.artifact_missing",
                        "Some artifacts are missing from the account database.",
                    )
                )
            elif row.character_id is None:
                status.setText(
                    _translated(
                        "gcsim.optimizer.character_missing",
                        "Character target is unavailable.",
                    )
                )
            action_layout.addWidget(button)
            action_layout.addWidget(status)
            action_layout.addStretch(1)
            self.grid.addWidget(action, row_index, 6)
            self._save_buttons[row.wearer_key] = button
            self._save_tooltips[row.wearer_key] = tooltip
            self._status_labels[row.wearer_key] = status

        self._update_navigation()

    def request_save(self, wearer_key: str, name: str) -> bool:
        row = self._rows.get(str(wearer_key).casefold())
        normalized_name = str(name).strip()
        if row is None or not row.can_save or row.character_id is None or not normalized_name:
            return False
        self.save_requested.emit(row.save_request(normalized_name))
        return True

    def set_save_result(self, wearer_key: str, *, success: bool, message: str) -> None:
        status = self._status_labels.get(str(wearer_key).casefold())
        if status is None:
            return
        status.setText(str(message))
        status.setStyleSheet(
            f"color: {UI_STATE_SUCCESS}; font-size: 10px;"
            if success
            else f"color: {UI_STATE_DANGER}; font-size: 10px;"
        )

    def clear(self) -> None:
        self._clear_grid()
        self._pages = ()
        self._page_index = 0
        self._update_navigation()
        self.setVisible(False)

    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._rows = {}
        self._save_buttons = {}
        self._save_tooltips = {}
        self._status_labels = {}

    def _change_page(self, delta: int) -> None:
        if not self._pages:
            return
        next_index = max(0, min(len(self._pages) - 1, self._page_index + int(delta)))
        if next_index == self._page_index:
            return
        self._page_index = next_index
        self._render_current_page()

    def _update_navigation(self) -> None:
        has_pages = bool(self._pages)
        self.previous_button.setEnabled(has_pages and self._page_index > 0)
        self.next_button.setEnabled(
            has_pages and self._page_index + 1 < len(self._pages)
        )
        if not has_pages:
            self.title_label.setText(
                _translated("gcsim.optimizer.result_builds", "Found builds")
            )
            return
        page = self._pages[self._page_index]
        title = _translated(
            "gcsim.optimizer.rank_title",
            "Top-{rank} {dps} DPS",
        )
        self.title_label.setText(
            title.format(rank=page.rank, dps=_format_title_dps(page.measured_dps))
        )

    def _emit_save(self, wearer_key: str) -> None:
        row = self._rows.get(wearer_key)
        if row is None:
            return
        from PySide6.QtWidgets import QInputDialog

        default_name = _translated(
            "gcsim.optimizer.default_build_name",
            "Selected Sets — {name}",
        ).format(name=row.character_name)
        name, accepted = QInputDialog.getText(
            self,
            _translated("gcsim.optimizer.save_title", "Save artifact build"),
            _translated("artifact.build.name", "Name"),
            text=default_name,
        )
        if accepted:
            self.request_save(wearer_key, name)


class CompactOptimizerArtifactCard(QFrame):
    def __init__(self, artifact: ArtifactItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.artifact = artifact
        self.setObjectName("OptimizerCompactArtifactCard")
        self.setFixedSize(104, 88)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            "QFrame#OptimizerCompactArtifactCard {"
            f"background: {UI_BG_PANEL}; border: 1px solid {UI_BORDER_DEFAULT}; "
            "border-radius: 7px;"
            "}"
        )
        install_custom_tooltip(
            self,
            f"{artifact.set_name} · {artifact.pos_name}\n"
            f"{artifact.main_property_name} {artifact.main_property_value}\n"
            f"ID {artifact.id}",
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 3)
        root.setSpacing(2)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(3)
        icon = QLabel()
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(38, 52)
        if artifact.icon_path is not None:
            pixmap = cached_scaled_pixmap(
                artifact.icon_path, QSize(38, 48),
                dpr=self.devicePixelRatioF(),
            )
            if pixmap is not None:
                icon.setPixmap(pixmap)
        top.addWidget(icon)

        stats = QVBoxLayout()
        stats.setContentsMargins(0, 0, 0, 0)
        stats.setSpacing(1)
        for substat in artifact.substats[:4]:
            stats.addWidget(
                _stat_row(
                    stat_badge(substat.property_type),
                    substat.value,
                    substat.times,
                )
            )
        stats.addStretch(1)
        top.addLayout(stats, 1)
        root.addLayout(top)
        root.addWidget(_MainStatWidget(artifact))


class _MainStatWidget(QWidget):
    def __init__(self, artifact: ArtifactItem) -> None:
        super().__init__()
        self.setFixedHeight(19)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        element_icon = ELEMENT_MAIN_STAT_ICONS.get(artifact.main_property_type)
        if element_icon is not None and element_icon.exists():
            icon = QLabel()
            icon.setFixedSize(17, 17)
            result = load_hidpi_pixmap(
                element_icon,
                QSize(16, 16),
                dpr=self.devicePixelRatioF(),
                surface="optimizer_result_element",
            )
            if not result.pixmap.isNull():
                icon.setPixmap(result.pixmap)
            layout.addWidget(icon)
        else:
            layout.addWidget(_badge_label(stat_badge(artifact.main_property_type)))
        value = QLabel(artifact.main_property_value)
        value.setStyleSheet(f"color: {UI_TEXT_PRIMARY}; font-size: 9px;")
        layout.addWidget(value)
        layout.addStretch(1)


class _CharacterBadge(QWidget):
    def __init__(self, row: OptimizerResultBuildRow) -> None:
        super().__init__()
        self.setFixedWidth(52)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 3, 0)
        layout.setSpacing(2)
        icon = QLabel()
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(42, 42)
        if row.character_icon_path is not None:
            result = load_hidpi_pixmap(
                row.character_icon_path,
                QSize(40, 40),
                dpr=self.devicePixelRatioF(),
                surface="optimizer_result_character",
            )
            if not result.pixmap.isNull():
                icon.setPixmap(result.pixmap)
        name = QLabel(row.character_name)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setWordWrap(True)
        name.setStyleSheet("font-size: 9px;")
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(name)


def _stat_row(badge: str, value: str, times: int | None) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(3)
    layout.addWidget(_badge_label(badge))
    value_label = QLabel(str(value))
    value_label.setStyleSheet(f"color: {UI_TEXT_SECONDARY}; font-size: 8px;")
    layout.addWidget(value_label, 1)
    return row


def _badge_label(text: str) -> QLabel:
    label = QLabel(str(text))
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet(
        f"QLabel {{ background: {UI_BG_BUTTON_CHECKED}; color: {UI_TEXT_SECONDARY}; "
        f"border: 1px solid {UI_BORDER_DEFAULT}; "
        "border-radius: 6px; padding: 0 2px; font-size: 8px; font-weight: 600; }"
    )
    return label


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _normalized_key(value: Any) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def _optional_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_title_dps(value: Any) -> str:
    try:
        return f"{float(str(value)):,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def _existing_project_path(value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path if path.exists() and path.is_file() else None


def _translated(key: str, fallback: str) -> str:
    value = tr(key)
    return fallback if value == key else value
