from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QEvent, QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QWidget


CUSTOM_TOOLTIP_DELAY_MS = 180
CUSTOM_TOOLTIP_MAX_WIDTH = 420
CUSTOM_TOOLTIP_LONG_TEXT_MIN_WIDTH = 360
CUSTOM_TOOLTIP_OFFSET = 8
CUSTOM_TOOLTIP_SCREEN_MARGIN = 8

CUSTOM_TOOLTIP_STYLE = """
QLabel {
	color: #f4ead8;
	background-color: rgba(24, 22, 20, 245);
	border: 1px solid rgba(226, 202, 148, 180);
	border-radius: 8px;
	padding: 7px 10px;
	font-size: 13px;
	font-weight: 600;
}
"""

TooltipTextProvider = str | Callable[[], str]


class CustomTooltipPopup(QLabel):
	def __init__(self, parent: QWidget | None = None):
		super().__init__(parent)
		self.setObjectName("CustomTooltipPopup")

		self.setWindowFlags(
			Qt.ToolTip
			| Qt.FramelessWindowHint
			| Qt.WindowStaysOnTopHint
			| Qt.WindowTransparentForInput
			| Qt.WindowDoesNotAcceptFocus
		)
		self.setAttribute(Qt.WA_ShowWithoutActivating, True)

		self.setWordWrap(True)
		self.setMaximumWidth(CUSTOM_TOOLTIP_MAX_WIDTH)
		self.setStyleSheet(CUSTOM_TOOLTIP_STYLE)

	def _content_size(self) -> QSize:
		self.ensurePolished()
		minimum_width = (
			CUSTOM_TOOLTIP_LONG_TEXT_MIN_WIDTH
			if len(self.text()) > 220 or "\n\n" in self.text()
			else 0
		)
		self.setMinimumWidth(minimum_width)
		self.setMaximumWidth(CUSTOM_TOOLTIP_MAX_WIDTH)
		self.adjustSize()

		hint = self.sizeHint()
		width = min(max(hint.width(), self.minimumSizeHint().width()), CUSTOM_TOOLTIP_MAX_WIDTH)

		if self.hasHeightForWidth():
			height = self.heightForWidth(width)
		else:
			height = hint.height()

		if height <= 0:
			height = hint.height()

		return QSize(width, height).expandedTo(self.minimumSizeHint())

	@staticmethod
	def _clamp_rect(rect: QRect, area: QRect) -> QRect:
		if rect.width() > area.width():
			rect.setWidth(area.width())
		if rect.height() > area.height():
			rect.setHeight(area.height())

		if rect.left() < area.left():
			rect.moveLeft(area.left())
		if rect.right() > area.right():
			rect.moveRight(area.right())
		if rect.top() < area.top():
			rect.moveTop(area.top())
		if rect.bottom() > area.bottom():
			rect.moveBottom(area.bottom())

		return rect

	def show_for(self, owner: QWidget, text: str) -> None:
		if not text:
			self.hide()
			return

		self.setText(text)
		global_top_center = owner.mapToGlobal(QPoint(owner.width() // 2, 0))
		global_bottom_center = owner.mapToGlobal(QPoint(owner.width() // 2, owner.height()))

		screen = QApplication.screenAt(global_top_center)
		if screen is None:
			screen = QApplication.primaryScreen()

		size = self._content_size()
		self.resize(size)

		x = global_top_center.x() - size.width() // 2
		y = global_top_center.y() - size.height() - CUSTOM_TOOLTIP_OFFSET
		rect = QRect(x, y, size.width(), size.height())

		if screen is not None:
			area = screen.availableGeometry().adjusted(
				CUSTOM_TOOLTIP_SCREEN_MARGIN,
				CUSTOM_TOOLTIP_SCREEN_MARGIN,
				-CUSTOM_TOOLTIP_SCREEN_MARGIN,
				-CUSTOM_TOOLTIP_SCREEN_MARGIN,
			)

			if rect.top() < area.top():
				below_y = global_bottom_center.y() + CUSTOM_TOOLTIP_OFFSET
				if below_y + size.height() <= area.bottom():
					rect.moveTop(below_y)

			rect = self._clamp_rect(rect, area)

		self.setFixedSize(rect.size())
		self.move(rect.topLeft())
		self.show()


class CustomTooltipController(QObject):
	def __init__(
		self,
		owner: QWidget,
		text: TooltipTextProvider = "",
		*,
		delay_ms: int = CUSTOM_TOOLTIP_DELAY_MS,
	):
		super().__init__(owner)
		self.owner = owner
		self._text_provider: TooltipTextProvider = text
		self._popup = CustomTooltipPopup()
		self._timer = QTimer(self)
		self._timer.setSingleShot(True)
		self._timer.timeout.connect(self.show)
		self._delay_ms = int(delay_ms)

		self.owner.installEventFilter(self)
		self.owner.destroyed.connect(self._popup.deleteLater)
		QWidget.setToolTip(self.owner, "")

	def set_text(self, text: TooltipTextProvider) -> None:
		self._text_provider = text
		QWidget.setToolTip(self.owner, "")
		if not self.text():
			self.hide()

	def text(self) -> str:
		provider = self._text_provider
		if callable(provider):
			provider = provider()
		return str(provider or "")

	def show_later(self) -> None:
		if self.text():
			self._timer.start(self._delay_ms)

	def show(self) -> None:
		text = self.text()
		if not text or not self.owner.isVisible():
			return
		self._popup.show_for(self.owner, text)

	def hide(self) -> None:
		self._timer.stop()
		self._popup.hide()

	def eventFilter(self, watched, event) -> bool:
		if watched is self.owner:
			event_type = event.type()
			if event_type == QEvent.Type.Enter:
				self.show_later()
			elif event_type in (
				QEvent.Type.Leave,
				QEvent.Type.Hide,
				QEvent.Type.MouseButtonPress,
			):
				self.hide()
			elif event_type == QEvent.Type.ToolTip:
				return True
		return super().eventFilter(watched, event)


def install_custom_tooltip(
	owner: QWidget,
	text: TooltipTextProvider = "",
	*,
	delay_ms: int = CUSTOM_TOOLTIP_DELAY_MS,
) -> CustomTooltipController:
	return CustomTooltipController(owner, text, delay_ms=delay_ms)
