"""Controls for temporary property values; the source tree owns the document."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from localization import tr
from run_workspace.gcsim.rotation_editor.conditions import Condition
from run_workspace.gcsim.rotation_editor.semantics import ScheduleChoice
from run_workspace.gcsim.rotation_editor.variants import VariantChoice


def combo(rows, value=None):
    widget = QComboBox()
    for label, data in rows:
        widget.addItem(label, data)
    index = widget.findData(value)
    if index >= 0:
        widget.setCurrentIndex(index)
    return widget


class ConditionControl(QWidget):
    """Recursive all/any/not without flattening imported grouping."""

    KINDS = ("energy_full", "energy", "hp_percent", "action_ready", "on_field",
             "effect", "constellations", "mode", "constant", "all", "any", "not")

    def __init__(self, names, value=None, parent=None, *, depth=0):
        super().__init__(parent)
        self.names, self.depth = names, depth
        self.children_controls = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        kinds = self.KINDS if depth < 8 else self.KINDS[:-3]
        # Deeper imported predicates are displayed rather than silently changed.
        if value and value.kind not in kinds:
            kinds += (value.kind,)
        self.kind = combo([(tr("rotation.editor.choose_condition"), "")] + [
            (tr("rotation.editor.condition." + key), key) for key in kinds], value.kind if value else "")
        layout.addWidget(self.kind)
        self.simple = QWidget()
        form = QFormLayout(self.simple)
        form.setContentsMargins(0, 0, 0, 0)
        self.actor = combo([(tr("rotation.editor.global"), "")] + [(label, key) for key, label in names.items()], value.actor if value else "")
        self.operator = combo([(tr("rotation.condition.compare." + label), op) for op, label in
            (("==", "eq"), ("!=", "ne"), ("<", "lt"), ("<=", "le"), (">", "gt"), (">=", "ge"))], value.operator if value else ">=")
        self.amount = QLineEdit(value.value if value else "")
        self.subject = QLineEdit(value.subject if value else "")
        self.ready = combo([(tr("rotation.action.skill"), "skill"), (tr("rotation.action.burst"), "burst")], value.subject if value else "skill")
        self.mode = combo([(tr("rotation.editor.nightsoul"), "nightsoul"), (tr("rotation.editor.ousia"), "ousia")], value.subject if value else "nightsoul")
        self.constant = combo([(tr("rotation.condition.always"), "true"), (tr("rotation.condition.never"), "false")], value.value if value else "true")
        self.negative = QCheckBox(tr("rotation.editor.negate"))
        for label, widget in (("actor", self.actor), ("comparison", self.operator), ("value", self.amount),
                              ("effect_key", self.subject), ("action", self.ready), ("mode", self.mode), ("value", self.constant)):
            form.addRow(tr("rotation.editor." + label), widget)
        self.form = form
        layout.addWidget(self.simple)
        layout.addWidget(self.negative)
        self.group = QWidget()
        self.group_layout = QVBoxLayout(self.group)
        self.group_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.group)
        self.add = QPushButton(tr("rotation.editor.add_condition"))
        layout.addWidget(self.add)
        self.add.clicked.connect(lambda: self.add_child())
        self.kind.currentIndexChanged.connect(self.refresh_kind)
        if value and value.kind in {"all", "any", "not"}:
            for child in value.children:
                self.add_child(child)
        self.refresh_kind()

    def add_child(self, value=None):
        if len(self.children_controls) >= 16:
            return
        child = ConditionControl(self.names, value, self.group, depth=self.depth + 1)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(child, 1)
        remove = QPushButton("×")
        remove.setFixedWidth(28)
        row_layout.addWidget(remove)
        self.children_controls.append((child, row))
        self.group_layout.addWidget(row)
        def discard():
            self.children_controls.remove((child, row))
            row.hide()
            row.deleteLater()
        remove.clicked.connect(discard)

    def refresh_kind(self):
        kind = self.kind.currentData()
        grouped = kind in {"all", "any", "not"}
        self.simple.setVisible(bool(kind) and not grouped)
        self.group.setVisible(grouped)
        self.add.setVisible(kind in {"all", "any"})
        self.negative.setVisible(bool(kind) and not grouped)
        if grouped and not self.children_controls:
            self.add_child()
        visible = {
            self.actor: kind not in {"constant", ""},
            self.operator: kind in {"energy", "hp_percent", "constellations"},
            self.amount: kind in {"energy", "hp_percent", "constellations"},
            self.subject: kind == "effect", self.ready: kind == "action_ready",
            self.mode: kind == "mode", self.constant: kind == "constant",
        }
        for widget, show in visible.items():
            self.form.setRowVisible(widget, show)

    def value(self):
        kind = self.kind.currentData()
        if not kind:
            raise ValueError(tr("rotation.editor.choose_condition"))
        if kind in {"all", "any", "not"}:
            children = tuple(child.value() for child, _ in self.children_controls)
            if not children or kind == "not" and len(children) != 1:
                raise ValueError(tr("rotation.editor.incomplete_condition"))
            return Condition(kind, children=children)
        subject = self.subject.text() if kind == "effect" else self.ready.currentData() if kind == "action_ready" else self.mode.currentData() if kind == "mode" else ""
        result = Condition(kind, self.actor.currentData() if kind != "constant" else "", subject,
                           self.operator.currentData(), self.constant.currentData() if kind == "constant" else self.amount.text())
        return Condition("not", children=(result,)) if self.negative.isChecked() else result


class ScheduleControl(QWidget):
    def __init__(self, value=None, parent=None):
        super().__init__(parent)
        value = value or ScheduleChoice(every=2, first=2)
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.mode = combo([(tr("rotation.editor.every_nth"), "every"), (tr("rotation.editor.selected_rotations"), "selected")], value.mode)
        self.every, self.first = QLineEdit(), QLineEdit()
        for widget, amount in ((self.every, value.every), (self.first, value.first)):
            widget.setText(str(amount))
        self.positions = QLineEdit(", ".join(map(str, value.positions)))
        for key, widget in (("schedule_mode", self.mode), ("every", self.every), ("first", self.first), ("positions", self.positions)):
            layout.addRow(tr("rotation.editor." + key), widget)
        def refresh():
            selected = self.mode.currentData() == "selected"
            layout.setRowVisible(self.every, not selected)
            layout.setRowVisible(self.first, not selected)
            layout.setRowVisible(self.positions, selected)
        self.mode.currentIndexChanged.connect(refresh)
        refresh()

    def value(self):
        return ScheduleChoice(mode=self.mode.currentData(), every=int(self.every.text()), first=int(self.first.text()),
            positions=tuple(int(item.strip()) for item in self.positions.text().split(",") if item.strip()))


class VariantControl(QWidget):
    def __init__(self, choices, parent=None):
        super().__init__(parent)
        self.choices = choices
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.choice = combo([(tr(item.label_key), item.key) for item in choices])
        self.amount = QComboBox()
        self.policy = combo([(tr("rotation.editor.ensure"), "ensure"), (tr("rotation.editor.guard"), "guard")])
        layout.addRow(self.choice)
        layout.addRow(tr("rotation.editor.value"), self.amount)
        layout.addRow(tr("rotation.editor.preparation"), self.policy)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addRow(self.note)
        self.choice.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        variant = self.choices[self.choice.currentIndex()]
        self.amount.clear()
        for value in variant.values:
            label = tr("rotation.bennett.hold." + str(value)) if variant.actor == "bennett" else str(value)
            self.amount.addItem(label, value)
        index = self.amount.findData(variant.default)
        self.amount.setCurrentIndex(max(0, index))
        self.layout().setRowVisible(self.amount, bool(variant.values))
        self.layout().setRowVisible(self.policy, variant.actor != "bennett")
        self.note.setText("\n".join(tr(key) for key in variant.requirement_keys))

    def value(self):
        return VariantChoice(self.choice.currentData(), self.amount.currentData(), self.policy.currentData())
