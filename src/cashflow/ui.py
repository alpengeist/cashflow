from __future__ import annotations

from PySide6.QtWidgets import QComboBox


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
