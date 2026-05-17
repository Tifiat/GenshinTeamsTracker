from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from run_workspace.team_card_view_model import (
    TeamCardArtifactSummaryViewModel,
    TeamCardSlotViewModel,
    TeamCardViewModel,
)


class TeamCardPrototypeWidget(QFrame):
    """Read-only prototype for future TeamCard data density.

    This widget is intentionally isolated from the legacy right panel and has
    no drag/drop behavior. Feed it a TeamCardViewModel prepared from
    TeamBuilderState / CharacterDetailsData.
    """

    def __init__(self, model: TeamCardViewModel, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("TeamCardPrototypeWidget")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setSpacing(8)

        self._title = QLabel()
        self._title.setObjectName("TeamCardPrototypeTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._layout.addWidget(self._title)

        self._warnings = QLabel()
        self._warnings.setObjectName("TeamCardPrototypeWarnings")
        self._warnings.setWordWrap(True)
        self._layout.addWidget(self._warnings)

        self._slot_container = QWidget()
        self._slot_layout = QGridLayout(self._slot_container)
        self._slot_layout.setContentsMargins(0, 0, 0, 0)
        self._slot_layout.setHorizontalSpacing(8)
        self._slot_layout.setVerticalSpacing(8)
        self._layout.addWidget(self._slot_container)

        self._slot_widgets: list[CharacterTilePrototypeWidget] = []
        self.set_model(model)

    def set_model(self, model: TeamCardViewModel) -> None:
        self._model = model
        self._title.setText(model.title)
        self._warnings.setText(_compact_warnings(model.warnings))
        self._warnings.setVisible(bool(model.warnings))

        while self._slot_widgets:
            widget = self._slot_widgets.pop()
            self._slot_layout.removeWidget(widget)
            widget.deleteLater()

        for index, slot in enumerate(model.slots):
            widget = CharacterTilePrototypeWidget(slot)
            self._slot_widgets.append(widget)
            self._slot_layout.addWidget(widget, index // 4, index % 4)


class CharacterTilePrototypeWidget(QFrame):
    def __init__(self, model: TeamCardSlotViewModel, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("CharacterTilePrototypeWidget")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(4)

        self._character = QLabel()
        self._character.setObjectName("CharacterTilePrototypeCharacter")
        self._character.setWordWrap(True)
        self._layout.addWidget(self._character)

        self._character_meta = QLabel()
        self._character_meta.setObjectName("CharacterTilePrototypeMeta")
        self._character_meta.setWordWrap(True)
        self._layout.addWidget(self._character_meta)

        self._weapon = QLabel()
        self._weapon.setObjectName("CharacterTilePrototypeWeapon")
        self._weapon.setWordWrap(True)
        self._layout.addWidget(self._weapon)

        self._build = QLabel()
        self._build.setObjectName("CharacterTilePrototypeBuild")
        self._build.setWordWrap(True)
        self._layout.addWidget(self._build)

        self._artifact = QLabel()
        self._artifact.setObjectName("CharacterTilePrototypeArtifact")
        self._artifact.setWordWrap(True)
        self._layout.addWidget(self._artifact)

        self._warnings = QLabel()
        self._warnings.setObjectName("CharacterTilePrototypeWarnings")
        self._warnings.setWordWrap(True)
        self._layout.addWidget(self._warnings)

        self.set_model(model)

    def set_model(self, model: TeamCardSlotViewModel) -> None:
        self._model = model
        self._character.setText(model.character_title)
        self._character_meta.setText(model.character_meta)
        self._character_meta.setVisible(bool(model.character_meta))
        self._weapon.setText(model.weapon_label)
        self._weapon.setVisible(bool(model.weapon_label))
        self._build.setText(model.build_label)
        self._build.setVisible(bool(model.build_label))
        self._artifact.setText(_artifact_text(model.artifact_summary))
        self._artifact.setVisible(model.artifact_summary is not None)
        self._warnings.setText(_compact_warnings(model.warnings))
        self._warnings.setVisible(bool(model.warnings))


def _artifact_text(model: TeamCardArtifactSummaryViewModel | None) -> str:
    if model is None:
        return ""
    lines: list[str] = []
    if model.active_sets:
        lines.append("Sets: " + "; ".join(model.active_sets))
    if model.crit_value is not None:
        lines.append(f"CV: {model.crit_value:g}")
    if model.proc_count is not None:
        lines.append(f"Proc: {model.proc_count}")
    if model.missing_positions:
        lines.append(
            "Missing: "
            + ", ".join(str(position) for position in model.missing_positions)
        )
    return "\n".join(lines)


def _compact_warnings(warnings: tuple[str, ...]) -> str:
    if not warnings:
        return ""
    return "Warnings: " + ", ".join(warnings)
