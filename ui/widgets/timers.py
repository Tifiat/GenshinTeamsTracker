from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QSpinBox
from PySide6.QtCore import Qt

from localization import tr
from run_workspace import AbyssTimerState, calculate_abyss_chamber_result


class WheelSpinBox(QSpinBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setWrapping(True)

    def wheelEvent(self, event):
        super().wheelEvent(event)
        event.accept()


class SmartSecondSpinBox(WheelSpinBox):
    def __init__(self, parent_timer_cell, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent_timer_cell = parent_timer_cell  # AbyssTimerCell

    def wheelEvent(self, event):
        old_val = self.value()
        delta = event.angleDelta().y() // 120  # количество "щелчков" колеса

        # Вручную пересчитываем секунды
        new_seconds = old_val + delta
        minutes = self.parent_timer_cell.min_spin.value()

        # Прокрутка вниз через 0
        if new_seconds < 0:
            if minutes > 5:  # минимальные минуты
                minutes -= 1
                new_seconds = 59
            else:
                new_seconds = 0

        # Прокрутка вверх через 59
        elif new_seconds > 59:
            if minutes < 10:  # максимальные минуты
                minutes += 1
                new_seconds = 0
            else:
                new_seconds = 59

        # Обновляем значения
        self.parent_timer_cell.min_spin.setValue(minutes)
        self.setValue(new_seconds)

        event.accept()
        self.parent_timer_cell.on_changed()


class AbyssTimerCell(QWidget):
    MAX_SECONDS = 600

    def __init__(self, on_change=None):
        super().__init__()

        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_Hover)

        self.on_change = on_change

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        row = QHBoxLayout()
        row.setSpacing(4)

        self.min_spin = QSpinBox()
        self.min_spin.setRange(5, 10)
        self.min_spin.setValue(10)
        self.min_spin.setFixedWidth(48)
        self.min_spin.setAlignment(Qt.AlignCenter)
        self.min_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.min_spin.setFocusPolicy(Qt.StrongFocus)

        self.sec_spin = SmartSecondSpinBox(self)
        self.sec_spin.setRange(0, 59)
        self.sec_spin.setValue(0)
        self.sec_spin.setFixedWidth(48)
        self.sec_spin.setAlignment(Qt.AlignCenter)
        self.sec_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.sec_spin.setFocusPolicy(Qt.StrongFocus)

        style = """
        QSpinBox {
            color: white;
            background: #2b2b2b;
            border: 1px solid #555;
            font-size: 14px;
        }
        """
        self.min_spin.setStyleSheet(style)
        self.sec_spin.setStyleSheet(style)

        colon = QLabel(":")
        colon.setAlignment(Qt.AlignCenter)

        row.addWidget(self.min_spin)
        row.addWidget(colon)
        row.addWidget(self.sec_spin)

        self.result = QLabel("0")
        self.result.setAlignment(Qt.AlignCenter)

        layout.addLayout(row)
        layout.addWidget(self.result)

        self.min_spin.valueChanged.connect(self.on_changed)
        self.sec_spin.valueChanged.connect(self.on_changed)

        self.seconds_left = self.MAX_SECONDS

    def on_changed(self):
        seconds = self.min_spin.value() * 60 + self.sec_spin.value()

        # Ограничение сверху
        if seconds > self.MAX_SECONDS:
            seconds = self.MAX_SECONDS
            self.min_spin.setValue(self.MAX_SECONDS // 60)
            self.sec_spin.setValue(self.MAX_SECONDS % 60)

        # Ограничение снизу (минимальное 5:00)
        if seconds < 5 * 60:
            seconds = 5 * 60
            self.min_spin.setValue(5)
            self.sec_spin.setValue(0)

        self.seconds_left = seconds
        if self.on_change:
            self.on_change()


class AbyssFloorRow(QWidget):
    START_TIME = 600

    def __init__(self, hall_number, on_change):
        super().__init__()
        self.hall_number = hall_number
        layout = QHBoxLayout(self)
        layout.setSpacing(6)

        self.hall_label = QLabel(tr("timer.hall", number=hall_number))
        layout.addWidget(self.hall_label)

        self.t1 = AbyssTimerCell(on_change)
        self.t2 = AbyssTimerCell(on_change)

        self.total = QLabel("0")
        self.total.setFixedWidth(50)
        self.total.setAlignment(Qt.AlignCenter)

        self.team1_label = QLabel(tr("timer.team1"))
        layout.addWidget(self.team1_label)
        layout.addWidget(self.t1)
        self.team2_label = QLabel(tr("timer.team2"))
        layout.addWidget(self.team2_label)
        layout.addWidget(self.t2)
        self.sum_label = QLabel(tr("timer.sum"))
        layout.addWidget(self.sum_label)
        layout.addWidget(self.total)

    def retranslate_ui(self):
        self.hall_label.setText(tr("timer.hall", number=self.hall_number))
        self.team1_label.setText(tr("timer.team1"))
        self.team2_label.setText(tr("timer.team2"))
        self.sum_label.setText(tr("timer.sum"))

    def calculate(self):
        result = calculate_abyss_chamber_result(
            AbyssTimerState(
                team1_left_seconds=self.t1.seconds_left,
                team2_left_seconds=self.t2.seconds_left,
                start_seconds=self.START_TIME,
            ),
            chamber_index=self.hall_number,
        )

        self.t1.result.setText(str(result.team1_elapsed_seconds))
        self.t2.result.setText(str(result.team2_elapsed_seconds))
        self.total.setText(str(result.total_elapsed_seconds))
        return result.total_elapsed_seconds
