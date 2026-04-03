from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QTableWidget


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
