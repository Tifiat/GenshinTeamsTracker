import os

from PySide6.QtCore import Qt, QMimeData, QEvent, QTimer, QPoint
from PySide6.QtGui import QPixmap, QDrag
from PySide6.QtWidgets import QLabel, QMessageBox, QApplication

from localization import tr


class FloatingTooltip(QLabel):
	def __init__(self):
		super().__init__(None)

		self.setWindowFlags(
			Qt.ToolTip
			| Qt.FramelessWindowHint
			| Qt.WindowStaysOnTopHint
			| Qt.WindowTransparentForInput
			| Qt.WindowDoesNotAcceptFocus
		)
		self.setAttribute(Qt.WA_ShowWithoutActivating, True)

		self.setWordWrap(True)
		self.setMaximumWidth(280)
		self.setStyleSheet(
			"""
			QLabel {
				color: #f4ead8;
				background-color: rgba(24, 22, 20, 245);
				border: 1px solid rgba(226, 202, 148, 180);
				border-radius: 8px;
				padding: 7px 10px;
				font-size: 12px;
				font-weight: 600;
			}
			"""
		)

	def show_for(self, owner, text: str):
		if not text:
			self.hide()
			return

		self.setText(text)
		self.adjustSize()

		# Стабильная позиция: над иконкой по центру.
		global_top_center = owner.mapToGlobal(QPoint(owner.width() // 2, 0))
		x = global_top_center.x() - self.width() // 2
		y = global_top_center.y() - self.height() - 8

		screen = QApplication.screenAt(global_top_center)
		if screen is None:
			screen = QApplication.primaryScreen()

		if screen is not None:
			area = screen.availableGeometry()
			x = max(area.left() + 8, min(x, area.right() - self.width() - 8))
			y = max(area.top() + 8, min(y, area.bottom() - self.height() - 8))

		self.move(x, y)
		self.show()


class DraggableIcon(QLabel):
	def __init__(self, image_path, size):
		super().__init__()
		self.image_path = image_path
		self.base_size = size
		self._src_pixmap = QPixmap(image_path)

		self._custom_tooltip = ""
		self._tooltip_popup = FloatingTooltip()
		self._tooltip_timer = QTimer(self)
		self._tooltip_timer.setSingleShot(True)
		self._tooltip_timer.timeout.connect(self._show_custom_tooltip)

		self.setFixedSize(size, size)
		self.setCursor(Qt.OpenHandCursor)
		self._update_pixmap()
		QTimer.singleShot(0, self._update_pixmap)

	def setToolTip(self, text):
		"""Перехватываем системный tooltip Qt и используем свой стабильный popup."""
		self._custom_tooltip = text or ""
		super().setToolTip("")

	def _show_custom_tooltip(self):
		if not self._custom_tooltip:
			return
		if not self.isVisible():
			return
		self._tooltip_popup.show_for(self, self._custom_tooltip)

	def _hide_custom_tooltip(self):
		self._tooltip_timer.stop()
		self._tooltip_popup.hide()

	def enterEvent(self, event):
		if self._custom_tooltip:
			self._tooltip_timer.start(180)
		super().enterEvent(event)

	def leaveEvent(self, event):
		self._hide_custom_tooltip()
		super().leaveEvent(event)

	def hideEvent(self, event):
		self._hide_custom_tooltip()
		super().hideEvent(event)

	def _update_pixmap(self):
		"""Пересобрать pixmap с учетом текущего DPI экрана."""
		if self._src_pixmap.isNull():
			self.clear()
			return

		dpr = self.devicePixelRatioF()
		target_px = max(1, int(self.base_size * dpr))

		pixmap = self._src_pixmap.scaled(
			target_px,
			target_px,
			Qt.KeepAspectRatio,
			Qt.SmoothTransformation
		)
		pixmap.setDevicePixelRatio(dpr)
		self.setPixmap(pixmap)

	def event(self, event):
		"""Обновлять pixmap при смене экрана / DPI / размера."""
		if event.type() in (
			QEvent.Type.DevicePixelRatioChange,
			QEvent.Type.Resize,
			QEvent.Type.Show,
		):
			self._update_pixmap()
		return super().event(event)

	def mousePressEvent(self, event):
		self._hide_custom_tooltip()

		if event.button() == Qt.LeftButton:
			drag = QDrag(self)
			mime = QMimeData()
			mime.setText(self.image_path)
			drag.setMimeData(mime)
			if self.pixmap() is not None:
				drag.setPixmap(self.pixmap())
			drag.exec(Qt.CopyAction)

		elif event.button() == Qt.RightButton:
			self._handle_right_click(event)

	def _handle_right_click(self, event):
		"""Обработка правого клика - удаление файла"""
		if not self.image_path or not os.path.exists(self.image_path):
			return

		if not self._is_in_assets_folder(self.image_path):
			QMessageBox.warning(
				self,
				tr("common.error"),
				tr("drag.delete_outside_assets")
			)
			return

		ctrl_pressed = QApplication.keyboardModifiers() & Qt.ControlModifier

		if not ctrl_pressed:
			reply = QMessageBox.question(
				self,
				tr("drag.delete_file_title"),
				tr("drag.delete_file_confirm", filename=os.path.basename(self.image_path)),
				QMessageBox.Yes | QMessageBox.No,
				QMessageBox.No
			)
			if reply != QMessageBox.Yes:
				return

		try:
			os.remove(self.image_path)
			self.hide()
			self._notify_parent_to_update_grids()

		except Exception as e:
			QMessageBox.warning(
				self,
				tr("common.error"),
				tr("drag.delete_failed", error=e)
			)

	def _is_in_assets_folder(self, filepath):
		"""Проверяем, что файл находится в папке assets"""
		try:
			abs_path = os.path.abspath(filepath)
			assets_dirs = [
				os.path.abspath("assets/characters"),
				os.path.abspath("assets/weapons"),
				os.path.abspath("assets/hd/characters"),
				os.path.abspath("assets/hd/weapons"),
				os.path.abspath("assets/hoyolab/characters"),
				os.path.abspath("assets/hoyolab/weapons"),
			]

			for assets_dir in assets_dirs:
				if abs_path.startswith(assets_dir + os.sep):
					return True
			return False
		except Exception:
			return False

	def _notify_parent_to_update_grids(self):
		"""Найти главное окно App и вызвать безопасное обновление"""
		widget = self.parent()
		while widget:
			if hasattr(widget, "safe_update_grids"):
				QTimer.singleShot(50, widget.safe_update_grids)
				break
			elif hasattr(widget, "update_grids"):
				QTimer.singleShot(50, widget.update_grids)
				break
			widget = widget.parent()
