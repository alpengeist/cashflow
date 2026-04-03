from __future__ import annotations

from PySide6.QtWidgets import QTableWidgetItem


class NumericTableWidgetItem(QTableWidgetItem):
    def __init__(self, text: str, numeric_value: int) -> None:
        super().__init__(text)
        self._numeric_value = numeric_value

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, NumericTableWidgetItem):
            return self._numeric_value < other._numeric_value
        return super().__lt__(other)
