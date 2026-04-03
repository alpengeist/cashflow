from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QTableWidget, QWidget


class LoadingOverlay(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.setInterval(30)
        
        self.hide()

    def set_message(self, message: str) -> None:
        pass

    def show_with_message(self, message: str) -> None:
        if self.parentWidget():
            self.resize(self.parentWidget().size())
        self.show()
        self._timer.start()

    def hide_overlay(self) -> None:
        self._timer.stop()
        self.hide()

    def _rotate(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw background dimming
        painter.fillRect(self.rect(), QColor(0, 0, 0, 30))

        # Draw spinner
        rect = self.rect()
        side = min(rect.width(), rect.height())
        spinner_size = 50

        painter.translate(rect.center())

        # Draw static background circle
        pen = QPen(QColor(200, 200, 200, 100))
        pen.setWidth(5)
        painter.setPen(pen)
        painter.drawEllipse(-spinner_size // 2, -spinner_size // 2, spinner_size, spinner_size)

        # Draw animated blue arc
        pen = QPen(QColor(0, 120, 215)) # Standard Windows blue
        pen.setWidth(5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        # QPainter.drawArc uses 1/16th of a degree
        # Start angle is at 3 o'clock, positive is counter-clockwise
        # We want it to start from top and go clockwise
        start_angle = (90 - self._angle) * 16
        span_angle = -90 * 16 # 90 degrees clockwise
        
        painter.drawArc(
            -spinner_size // 2, 
            -spinner_size // 2, 
            spinner_size, 
            spinner_size, 
            start_angle, 
            span_angle
        )

    def resizeEvent(self, event) -> None:
        if self.parentWidget():
            self.resize(self.parentWidget().size())
        super().resizeEvent(event)


COMPACT_COMBO_BOX_STYLESHEET = """
QComboBox {
    padding-left: 8px;
    padding-right: 26px;
}
QComboBox QAbstractItemView::item {
    padding: 6px 10px;
    min-height: 24px;
}
"""


def configure_compact_combo_box(
    combo_box: QComboBox,
    *,
    minimum_contents_length: int = 0,
) -> None:
    combo_box.setStyleSheet(COMPACT_COMBO_BOX_STYLESHEET)
    combo_box.setMinimumContentsLength(minimum_contents_length)
    combo_box.setSizeAdjustPolicy(
        QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    )


def ensure_table_header_width(
    table: QTableWidget,
    column: int,
    label: str,
    *,
    extra_padding: int = 36,
) -> None:
    header = table.horizontalHeader()
    required_width = header.fontMetrics().horizontalAdvance(label) + extra_padding
    if header.sectionSize(column) < required_width:
        header.resizeSection(column, required_width)
